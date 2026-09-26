from cheapos.verification import evidence_identity
import http.client
from html.parser import HTMLParser
import io
import json
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from contextlib import ExitStack

from cheapos.engine import Engine, Runtime
from cheapos.providers import ChatProvider, ProviderError
from cheapos.providers import http_failure
from urllib.error import HTTPError
from cheapos.gateways import OmniRouteGateway
from cheapos.startup import GREETING
from cheapos.server import LocalHandler, LocalServer
from cheapos.workspace import Workspace


class CooldownErrorTests(unittest.TestCase):
    def error(self,status=404,retry='120',body=None):
        return HTTPError('http://localhost/v1/chat/completions',status,'error',{'Retry-After':retry},
                         io.BytesIO(json.dumps(body or {'error':{'message':'secret upstream text'}}).encode()))

    def test_gateway_cached_404_and_model_cooldown_are_distinguished(self):
        error=http_failure(self.error(),{'gateway':'omniroute'})
        self.assertEqual((error.code,error.scope,error.retry_after),('gateway_cooldown','model',120))
        self.assertNotIn('secret',str(error))
        error=http_failure(self.error(429,body={'error':{'code':'model_cooldown'}}),{'gateway':'omniroute'})
        self.assertEqual(error.scope,'model')
        error=http_failure(self.error(429,body={'error':{'code':'provider_cooldown'}}),{'gateway':'omniroute'})
        self.assertEqual(error.scope,'provider')

    def test_auth_direct_and_invalid_retry_metadata_keep_original_failure(self):
        for status in (401,402,403):
            self.assertEqual(http_failure(self.error(status),{'gateway':'omniroute'}).code,f'http_{status}')
        self.assertEqual(http_failure(self.error(),{'gateway':'openai'}).code,'http_404')
        for retry in ('','NaN','-2','invalid'):
            self.assertEqual(http_failure(self.error(retry=retry),{'gateway':'omniroute'}).code,'http_404')


class HTTPConnectionQueueTests(unittest.TestCase):
    def test_polling_burst_can_queue_before_handlers_accept_connections(self):
        # Two tabs can each issue six concurrent requests. Hold off accepting
        # until the burst is queued, without scheduler timing or real waits.
        with LocalServer(('127.0.0.1', 0), Path('.'), object()) as server, ExitStack() as stack:
            server.socket.settimeout(1)
            clients = []
            for _ in range(12):
                client = stack.enter_context(socket.create_connection(server.server_address, timeout=1))
                client.sendall((f'GET /api/connection HTTP/1.0\r\n'
                                f'Host: 127.0.0.1:{server.server_port}\r\n\r\n').encode())
                clients.append(client)
            for client in clients:
                connection, address = server.get_request()
                with connection:
                    server.finish_request(connection, address)
                response = http.client.HTTPResponse(client)
                response.begin()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read())['app'], 'CheapOS')
                response.close()


class JSONDisconnectTests(unittest.TestCase):
    """Exercise real response writes without sockets, tasks or background threads."""

    def request(self, method='GET', fail_at=None, error=None, token='fixture-token', engine_error=None):
        engine = SimpleNamespace(projects=Mock(return_value=[], side_effect=engine_error),
                                 save_preferences=Mock(return_value={'saved': True}))
        path = '/api/projects' if method == 'GET' else '/api/preferences'
        request = (f'{method} {path} HTTP/1.0\r\nHost: 127.0.0.1:5173\r\n'
                   f'X-CheapOS-Token: {token}\r\nContent-Type: application/json\r\n'
                   'Content-Length: 2\r\n\r\n{}').encode()
        connection = SimpleNamespace(makefile=Mock(return_value=io.BytesIO(request)), sendall=Mock())
        if fail_at is not None:
            connection.sendall.side_effect = [None] * fail_at + [error]
        server = SimpleNamespace(directory=Path(__file__).resolve().parent.parent / 'dist',
                                 server_port=5173, token='fixture-token', engine=engine)
        stderr = io.StringIO()
        with patch('sys.stderr', stderr):
            handler = LocalHandler(connection, ('127.0.0.1', 1234), server)
        return engine, connection.sendall, handler, stderr.getvalue()

    def test_get_disconnect_during_headers_or_body_does_not_send_a_second_response(self):
        for error in (BrokenPipeError, ConnectionResetError):
            for fail_at in (0, 1):
                with self.subTest(error=error, fail_at=fail_at):
                    engine, writes, handler, stderr = self.request(fail_at=fail_at, error=error())
                    engine.projects.assert_called_once_with()
                    self.assertEqual(writes.call_count, fail_at + 1)
                    self.assertIn(b' 200 OK\r\n', writes.call_args_list[0].args[0])
                    self.assertTrue(handler.close_connection)
                    self.assertEqual(stderr, '')

    def test_post_disconnect_preserves_the_completed_action_without_error_response(self):
        for error in (BrokenPipeError, ConnectionResetError):
            for fail_at in (0, 1):
                with self.subTest(error=error, fail_at=fail_at):
                    engine, writes, handler, stderr = self.request('POST', fail_at, error())
                    engine.save_preferences.assert_called_once_with({})
                    self.assertEqual(writes.call_count, fail_at + 1)
                    self.assertIn(b' 200 OK\r\n', writes.call_args_list[0].args[0])
                    self.assertTrue(handler.close_connection)
                    self.assertEqual(stderr, '')

    def test_disconnected_rejection_still_prevents_unauthorized_mutation(self):
        engine, writes, handler, stderr = self.request('POST', 0, BrokenPipeError(), token='expired')
        engine.save_preferences.assert_not_called()
        self.assertEqual(writes.call_count, 1)
        self.assertIn(b' 403 Forbidden\r\n', writes.call_args.args[0])
        self.assertTrue(handler.close_connection)
        self.assertEqual(stderr, '')

    def test_application_failure_still_logs_and_returns_500(self):
        # An upstream connection failure is not a browser disconnect.
        for error in (RuntimeError, ConnectionResetError):
            with self.subTest(error=error):
                engine, writes, _, stderr = self.request(engine_error=error('backend failed'))
                engine.projects.assert_called_once_with()
                self.assertEqual(writes.call_count, 2)
                self.assertIn(b' 500 Internal Server Error\r\n', writes.call_args_list[0].args[0])
                self.assertIn('error', json.loads(writes.call_args_list[1].args[0]))
                self.assertIn(f'{error.__name__}: backend failed', stderr)

    def test_reply_does_not_hide_unrelated_io_or_serialization_failures(self):
        handler = LocalHandler.__new__(LocalHandler)
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = SimpleNamespace(write=Mock(side_effect=OSError('unexpected write failure')))
        with self.assertRaisesRegex(OSError, 'unexpected write failure'):
            handler.reply({'ok': True})
        handler.send_response.reset_mock()
        with self.assertRaises(ValueError):
            handler.reply({'invalid': float('nan')})
        handler.send_response.assert_not_called()


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = Engine(Path(self.temp.name) / 'state', fixture_delay=0)
        self.server = LocalServer(('127.0.0.1', 0), Path(__file__).resolve().parent.parent / 'dist', self.engine)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval":0.01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.engine.shutdown()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request(method, path, json.dumps(body) if body is not None else None, headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def post(self, path, body):
        return self.request('POST', path, body, {'Content-Type':'application/json', 'X-CheapOS-Token': self.server.token})

    def test_merged_followup_requires_local_request_authority(self):
        with patch('cheapos.pr_followup.create', return_value={'id':'new','status':'awaiting_reply'}) as create:
            path = '/api/tasks/old/pull-request-follow-up'
            self.assertEqual(self.request('POST', path, {})[0], 403)
            self.assertEqual(self.request('POST', path, {}, {'X-CheapOS-Token':self.server.token,'Origin':'https://evil.test'})[0], 403)
            create.assert_not_called()
            status, _, body = self.post(path, {})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['id'], 'new')
            create.assert_called_once_with(self.engine, 'old', {})

    def test_schedule_mutations_require_local_operator_authority(self):
        with patch.object(self.engine.schedules, 'create', return_value={'schedules': []}) as create:
            self.assertEqual(self.request('POST', '/api/schedules', {})[0], 403)
            self.assertEqual(self.request('POST', '/api/schedules', {}, {'X-CheapOS-Token':self.server.token,'Origin':'https://evil.test'})[0], 403)
            create.assert_not_called()
            self.assertEqual(self.post('/api/schedules', {})[0], 200)
            create.assert_called_once_with({})

    def test_integration_preparation_routes_keep_read_and_write_authority_separate(self):
        self.engine.store.save({'id':'saved'})
        with patch('cheapos.integration_preparation.readiness', return_value={'code':'target_advanced'}) as inspect, patch('cheapos.integration_preparation.start', return_value={'id':'saved','status':'paused'}) as start:
            status, _, body = self.request('GET','/api/tasks/saved/integration-readiness')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['code'], 'target_advanced')
            self.assertEqual(self.request('POST','/api/tasks/saved/integration-prepare', {'approved':True})[0],403)
            self.assertFalse(start.called)
            status, _, body = self.post('/api/tasks/saved/integration-prepare', {'approved':True,'operation_id':'one'})
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body)['id'],'saved')
            start.assert_called_once_with(self.engine,'saved',{'approved':True,'operation_id':'one'})
            inspect.assert_called_once_with(self.engine,'saved')
        response={'updated':False,'state':'already_current','operation_id':'one',
                  'task':{'id':'saved','messages':[{'content':'private source'}]}}
        self.engine.store.save(response['task'])
        with patch('cheapos.branch_completion.update_branch',return_value=response) as update:
            self.assertEqual(self.request('POST','/api/tasks/saved/branch-update',{'approved':True,'update_token':'one'})[0],403)
            update.assert_not_called()
            status,_,body=self.post('/api/tasks/saved/branch-update',{'approved':True,'update_token':'one'})
            self.assertEqual(status,200,body)
            result=json.loads(body)
            self.assertFalse(result['updated']);self.assertEqual(result['state'],'already_current')
            self.assertNotIn('messages',result['task'])
            self.assertNotIn('private source',body.decode())


    def test_scoped_settings_http_revisions_and_idempotency(self):
        status, _, body = self.request('GET', '/api/settings/defaults')
        self.assertEqual(status, 200)
        initial = json.loads(body)
        request = {'patch': {'execution.coordinator_assistance': True},
                   'expected_revision': initial['revision'], 'operation_id': 'settings-once'}
        self.assertEqual(self.request('POST', '/api/settings/defaults', request)[0], 403)
        status, _, body = self.post('/api/settings/defaults', request)
        self.assertEqual(status, 200)
        saved = json.loads(body)
        self.assertTrue(saved['values']['execution']['coordinator_assistance'])
        status, _, body = self.post('/api/settings/defaults', request)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), saved)
        status, _, body = self.post('/api/settings/defaults', {**request, 'operation_id': 'stale'})
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)['current']['revision'], saved['revision'])
        self.assertEqual(self.post('/api/projects/settings', {**request, 'project': '/not/registered'})[0], 400)
        self.assertEqual(self.request('GET', '/settings.js')[0], 200)
        self.assertEqual(self.request('GET', '/connection_setup.js')[0], 200)
        self.assertEqual(self.request('GET', '/storage.js')[0], 200)
        self.assertEqual(self.request('GET', '/settings.css')[0], 200)

    def test_project_sync_uses_registered_project_settings_and_requires_token(self):
        from contextlib import nullcontext
        source = str(Path(self.temp.name).resolve())
        request = {'repository': source}
        snapshot = {'values': {'git': {'workflow': 'pull_request', 'remote': 'upstream'}}}
        with patch.object(self.engine, 'projects', return_value=[{'path':source}]), patch.object(self.engine.settings_store, 'view', return_value=snapshot), patch.object(self.engine.admission, 'repository', return_value=nullcontext()), patch('cheapos.git_sync.synchronize', return_value={'state':'current','retryable':False,'message':'Already current.'}) as sync:
            self.assertEqual(self.request('POST','/api/projects/git-sync',request)[0],403)
            self.assertEqual(self.request('POST','/api/projects/git-sync',request,{'X-CheapOS-Token':self.server.token,'Origin':'https://evil.test'})[0],403)
            sync.assert_not_called()
            status, _, body = self.post('/api/projects/git-sync',request)
            self.assertEqual(status,200,body)
            self.assertEqual(json.loads(body)['state'],'current')
            sync.assert_called_once_with(source,'upstream',None)
            sync.reset_mock()
            for invalid in ({}, {'repository':''}, {'repository':'/not/registered'}, {**request,'remote':'other'}, {**request,'ref':'main'}):
                self.assertEqual(self.post('/api/projects/git-sync',invalid)[0],400)
            snapshot['values']['git']['workflow']='local'
            status, _, body = self.post('/api/projects/git-sync',request)
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body)['state'],'disabled')
            sync.assert_not_called()

    def test_carto_settings_require_token_and_registered_project(self):
        source = str(Path(self.temp.name).resolve())
        with patch('cheapos.workspace.Workspace.project_root', return_value=Path(source)), patch.object(self.engine, 'projects', return_value=[{'path':source}]), patch.object(self.engine.carto, 'context', return_value={'status':'indexing'}):
            self.assertEqual(self.request('POST','/api/projects/carto',{'repository':source,'enabled':True})[0],403)
            status, _, body = self.post('/api/projects/carto',{'repository':source,'enabled':True})
            self.assertEqual(status,200)
            self.assertTrue(json.loads(body)['enabled'])
            self.assertEqual(json.loads(body)['index']['status'],'indexing')
            self.assertEqual(self.request('GET','/carto.js')[0],200)
        with patch('cheapos.workspace.Workspace.project_root', return_value=Path(source)), patch.object(self.engine, 'projects', return_value=[]):
            self.assertEqual(self.post('/api/projects/carto',{'repository':source})[0],400)

    def test_raw_check_route_only_resolves_known_task_and_run(self):
        from cheapos import check_output
        task=self.engine.create_demo();run='a'*32;data=b'exact failure\n\x1b[31mred\x1b[0m\n'
        meta=check_output.retain(self.engine.store.root,task['id'],run,data,False)
        task['checks']=[{'run_id':run,'raw_output':meta}];self.engine.store.save(task)
        url='/api/tasks/'+task['id']+'/checks/'+run+'/raw'
        status,headers,body=self.request('GET',url)
        self.assertEqual(status,200);self.assertEqual(body,data);self.assertIn('text/plain',headers['Content-Type'])
        self.assertNotEqual(self.request('GET',url.replace(run,'b'*32))[0],200)
        self.assertEqual(self.request('GET',url,headers={'Origin':'https://foreign.invalid'})[0],403)

    def test_readiness_contract_does_not_start_work(self):
        with patch.object(self.engine.readiness,'inspect',return_value={'schema_version':1,'status':'gateway_absent','next_step':'install_gateway'}) as inspect:
            status, _, body = self.request('GET','/api/readiness?refresh=1')
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body)['schema_version'],1)
            self.engine.readiness.thread.join(2)
            status, _, body = self.request('GET','/api/readiness')
            self.assertEqual(json.loads(body)['next_step'],'install_gateway')
            self.assertEqual(inspect.call_count,1)
            self.assertEqual(self.engine.store.list(),[])

    def test_real_sample_is_isolated_and_does_not_start_without_run_action(self):
        self.engine.save_preferences({'execution':{'mode':'local','local_model':'fixture'}})
        status, _, body=self.post('/api/sample',{})
        result=json.loads(body)
        self.assertEqual(status,200)
        self.assertTrue(result['sample'])
        self.assertFalse(result['demo'])
        self.assertEqual(result['status'],'ready')
        self.assertTrue(Path(result['source']).is_relative_to(self.engine.store.root/'examples'))
        self.assertEqual(self.engine.runtimes,{})

    def test_environment_recheck_is_read_only_and_task_scoped(self):
        task=self.engine.create_demo()
        task['check_command']=['.venv/bin/python','-m','unittest']
        self.engine.store.save(task)
        status, _, body=self.post('/api/tasks/'+task['id']+'/environment-recheck',{})
        self.assertEqual(status,200)
        result=json.loads(body)
        self.assertEqual(result['environment_setup']['missing'],'selected_environment')
        self.assertEqual(result['environment_setup']['workspace'],task['workspace'])
        self.assertFalse((Path(task['workspace'])/'.venv').exists())
        self.assertEqual(self.engine.runtimes,{})

    def test_bootstrap_and_static_files_without_signin(self):
        status, headers, body = self.request('GET', '/api/bootstrap')
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(data['app'], 'CheapOS')
        self.assertEqual(data['token'], self.server.token)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        class Assets(HTMLParser):
            def __init__(self):
                super().__init__();self.paths=[]
            def handle_starttag(self, tag, attributes):
                attrs=dict(attributes)
                path=attrs.get('src') if tag=='script' else attrs.get('href') if tag=='link' else None
                if path and path.startswith('./'):self.paths.append('/'+path[2:])
        status,_,page=self.request('GET','/')
        self.assertEqual(status,200)
        assets=Assets();assets.feed(page.decode())
        self.assertIn('/lifetime_usage.js',assets.paths)
        self.assertIn('/lifetime_usage.css',assets.paths)
        for path in assets.paths:
            with self.subTest(asset=path):
                status,headers,body=self.request('GET',path)
                self.assertEqual(status,200)
                self.assertTrue(body)
                self.assertNotIn('text/html',{key.lower():value for key,value in headers.items()}['content-type'])
        for path in ('/lifetime_usage.js','/lifetime_usage.css'):
            self.assertEqual(self.request('HEAD',path)[0],200)

    def test_cross_site_and_dns_rebinding_blocked(self):
        for headers in [{'Host': 'evil.example'}, {'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}]:
            self.assertEqual(self.request('GET', '/api/bootstrap', headers=headers)[0], 403)
        self.assertEqual(self.request('POST', '/api/demo', {}, {'Content-Type': 'application/json'})[0], 403)
        self.assertEqual(self.engine.store.list(), [])

    def test_session_permission_api_requires_current_approval_and_only_allows_revocation(self):
        task = self.engine.create_demo()
        runtime = Runtime(task)
        task['pending_approval'] = {'id': 'current', 'command': ['python3', '-m', 'unittest'], 'directory': task['workspace']}
        self.engine.runtimes[task['id']] = runtime
        path = '/api/tasks/' + task['id']
        for body in [{'approved': True, 'remember': 'yes'}, {'approved': True, 'remember': True}, {'approved': True, 'remember': True, 'approval_id': 'old'}]:
            self.assertEqual(self.post(path + '/approval', body)[0], 400)
        self.assertEqual(self.post(path + '/approval', {'approved': True, 'remember': True, 'approval_id': 'current'})[0], 200)
        result = json.loads(self.request('GET', path + '/permissions')[2])
        self.assertEqual(result['commands'], [['python3', '-m', 'unittest']])
        self.assertEqual(result['expires'], 'server_restart')
        self.assertEqual(self.post(path + '/approval', {'approved': True, 'remember': True, 'approval_id': 'current'})[0], 400)
        self.assertEqual(self.post(path + '/permissions', {'command': ['anything']})[0], 400)
        self.assertEqual(self.post(path + '/permissions', {'clear': True})[0], 200)
        self.assertEqual(json.loads(self.request('GET', path + '/permissions')[2])['commands'], [])
        choice = {'enabled': True, 'directory': task['workspace']}
        self.assertEqual(self.request('POST', path + '/task-commands', choice, {'Content-Type': 'application/json'})[0], 403)
        self.assertEqual(self.post(path + '/task-commands', {**choice, 'enabled': 'true'})[0], 400)
        self.assertEqual(self.post(path + '/task-commands', {**choice, 'directory': task['source']})[0], 400)
        self.assertEqual(self.post(path + '/task-commands', choice)[0], 200)
        self.assertTrue(json.loads(self.request('GET', path + '/permissions')[2])['task_commands'])
        self.assertEqual(self.post(path + '/task-commands', {**choice, 'enabled': False})[0], 200)
        self.assertFalse(json.loads(self.request('GET', path + '/permissions')[2])['task_commands'])

    def test_metadata_routes_share_titles_and_filter_history(self):
        task = self.engine.create_demo()
        path = '/api/tasks/' + task['id']
        values = {'custom_title': 'Useful task', 'pinned': True}
        self.assertEqual(self.request('POST', path + '/metadata', values, {'Content-Type': 'application/json'})[0], 403)
        self.assertEqual(self.post(path + '/metadata', values)[0], 200)
        for route in [path, '/api/tasks', '/api/bootstrap']:
            result = json.loads(self.request('GET', route)[2])
            if route == '/api/bootstrap':
                result = result['tasks']
            if isinstance(result, list):
                result = result[0]
            self.assertEqual(result['title'], 'Useful task')
            self.assertTrue(result['pinned'])
        self.assertEqual(self.post(path + '/metadata', {'archived': True})[0], 200)
        self.assertEqual(json.loads(self.request('GET', '/api/tasks')[2]), [])
        self.assertEqual(json.loads(self.request('GET', '/api/bootstrap')[2])['tasks'], [])
        self.assertEqual(len(json.loads(self.request('GET', '/api/tasks?view=archived')[2])), 1)
        self.assertEqual(self.request('GET', path)[0], 200)
        self.assertEqual(self.post(path + '/start', {})[0], 400)
        self.assertEqual(self.post(path + '/metadata', {'archived': False})[0], 200)
        self.assertEqual(self.post(path + '/metadata', {'custom_title': ''})[0], 400)
        self.assertEqual(self.post('/api/tasks/missing/metadata', values)[0], 400)
        self.assertEqual(self.post(path + '/metadata', {'status': 'running'})[0], 400)

    def test_restart_endpoint(self):
        status, _, _ = self.request('POST', '/api/restart', {})
        self.assertEqual(status, 403)
        with patch.object(self.server, 'server_close'), patch('os.execv') as mock_exec:
            status, _, body = self.post('/api/restart', {})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), {"status": "restarting"})
            import time
            time.sleep(0.5)
            mock_exec.assert_called_once_with(sys.executable, [sys.executable] + sys.argv)

    def test_role_mappings_http_endpoints(self):
        # Unauthenticated mutation rejected
        self.assertEqual(self.request('POST', '/api/role-mappings', {'defaults': {}})[0], 403)

        # GET role-mappings and effective
        status, _, body = self.request('GET', '/api/role-mappings')
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn('defaults', data)

        status, _, body = self.request('GET', '/api/role-mappings/effective')
        self.assertEqual(status, 200)
        eff = json.loads(body)
        self.assertIn('mapping', eff)

        # POST saving role mappings
        status, _, body = self.post('/api/role-mappings', {'defaults': {'planner': 'planner-x', 'worker': 'worker-y'}})
        self.assertEqual(status, 200)
        saved = json.loads(body)
        self.assertEqual(saved['defaults']['planner'], 'planner-x')

        # Defensive handling of /api/api/ prefix
        status, _, body = self.request('GET', '/api/api/role-mappings')
        self.assertEqual(status, 200)
        status, _, body = self.post('/api/api/role-mappings', {'defaults': {'planner': 'planner-z', 'worker': 'worker-y'}})
        self.assertEqual(status, 200)
        status, _, body = self.request('GET', '/api/api/role-mappings/effective')
        self.assertEqual(status, 200)
    def test_trash_routes_require_token_preserve_inspection_and_block_execution(self):
        task=self.engine.create_demo();path='/api/tasks/'+task['id']
        self.assertEqual(self.request('POST',path+'/trash',{}, {'Content-Type':'application/json'})[0],403)
        self.assertEqual(self.post(path+'/trash',{})[0],200)
        self.assertEqual(len(json.loads(self.request('GET','/api/tasks?view=trash')[2])),1)
        self.assertEqual(json.loads(self.request('GET','/api/tasks')[2]),[])
        self.assertEqual(self.request('GET',path)[0],200)
        for action,values in [('start',{}),('approval',{'approved':True}),('reconcile',{}),('commit-preview',{}),('rollback',{'checkpoint':1})]:
            self.assertEqual(self.post(path+'/'+action,values)[0],400)
        self.assertEqual(self.post(path+'/restore',{})[0],200)
        self.assertEqual(json.loads(self.request('GET',path)[2])['status'],'ready')
        self.assertEqual(self.post('/api/tasks/missing/trash',{})[0],400)
        self.assertEqual(self.request('GET','/api/storage')[0],200)
        values={'reclaim_merged':False,'trash_days':None}
        self.assertEqual(self.request('POST','/api/storage/settings',values,{'Content-Type':'application/json'})[0],403)
        self.assertEqual(self.post('/api/storage/settings',values)[0],200)
        self.assertEqual(self.post('/api/storage/settings',{'trash_days':0})[0],400)
        self.assertEqual(self.request('POST','/api/storage/cleanup',{}, {'Content-Type':'application/json'})[0],403)
        self.assertEqual(self.post('/api/storage/cleanup',{})[0],200)
        self.assertEqual(json.loads(self.request('GET','/api/storage')[2])['settings'],values)

    def test_project_hide_and_reopen_are_token_protected_and_nondestructive(self):
        task=self.engine.create_demo();task['demo']=False;self.engine.store.save(task)
        values={'repository':task['source']}
        self.assertEqual(self.request('POST','/api/projects/hide',values,{'Content-Type':'application/json'})[0],403)
        self.assertEqual(self.post('/api/projects/hide',values)[0],200)
        self.assertEqual(json.loads(self.request('GET','/api/projects')[2]),[])
        self.assertEqual(len(json.loads(self.request('GET','/api/projects/hidden')[2])),1)
        self.assertEqual(self.post('/api/projects',values)[0],200)
        self.assertEqual(len(json.loads(self.request('GET','/api/projects')[2])),1)
        self.assertEqual(len(self.engine.store.list()),1)

    def test_project_test_grant_scope_and_revocation_api(self):
        task=self.engine.create_demo();runtime=Runtime(task)
        argv=task['check_command'];profile=self.engine.project_test_grants.proposal(task,argv)
        task['pending_approval']={'id':'proposal','command':argv,'directory':task['workspace'],'profile':profile}
        self.engine.runtimes[task['id']]=runtime
        path='/api/tasks/'+task['id']
        self.assertEqual(self.post(path+'/approval',{'approved':True,'scope':'project_tests_session'})[0],400)
        self.assertEqual(self.post(path+'/approval',{'approved':True,'scope':'project_tests_session','approval_id':'proposal'})[0],200)
        grants=json.loads(self.request('GET',path+'/permissions')[2])['project_grants']
        self.assertEqual(len(grants),1)
        self.assertEqual(self.post(path+'/permissions',{'revoke_project_grant':grants[0]['id']})[0],200)
        self.assertEqual(json.loads(self.request('GET',path+'/permissions')[2])['project_grants'],[])

    def test_private_paths_are_not_served(self):
        for path in ['/README.md', '/.git/config', '/.cheapos/config.json', '/../run.py', '/%2e%2e/run.py', '/api/tasks/../../config']:
            self.assertEqual(self.request('GET', path)[0], 404, path)

    def test_task_creation_and_keys_redacted(self):
        self.engine.command_backend_default = 'bubblewrap'
        status, _, body = self.post('/api/demo', {})
        self.assertEqual(status, 200)
        task = json.loads(body)
        self.assertEqual(task['status'], 'ready')
        self.assertEqual(task['command_backend'], 'bubblewrap')
        self.engine.command_backend_default = 'host'
        stored = json.loads(self.request('GET', '/api/tasks/'+task['id'])[2])
        self.assertEqual(stored['command_backend'], 'bubblewrap')
        self.assertNotIn('messages', task)
        self.assertEqual(self.request('GET', '/api/tasks/'+task['id'])[0], 200)
        status, headers, body = self.request('GET', '/api/tasks/'+task['id']+'/patch')
        self.assertEqual(status, 200)
        self.assertIn('attachment', headers['Content-Disposition'])
        self.engine.gateway.configure({'api_key':'private-test-value'})
        config = {role: {'base_url': self.engine.gateway.settings['base_url'], 'gateway':'omniroute', 'model':'fixture-'+role, 'input_rate':0, 'output_rate':0} for role in ['worker', 'reviewer']}
        status, _, body = self.post('/api/config', config)
        self.assertEqual(status, 200)
        self.assertNotIn(b'private-test-value', body)
        self.assertNotIn(b'private-test-value', self.request('GET', '/api/bootstrap')[2])
        self.assertNotIn('private-test-value', (self.engine.store.root / 'settings.json').read_text())
        for gateway in ('openai','omniroute'):
            direct={**config['worker'],'gateway':gateway,'base_url':'https://openrouter.ai/api/v1'}
            with patch('cheapos.server.gateway_for') as connect:
                self.assertEqual(self.post('/api/models',{'role':'worker','config':direct})[0],400)
                self.assertEqual(self.post('/api/config',{'worker':direct})[0],400)
                connect.assert_not_called()

    def test_invalid_json_shape_is_rejected(self):
        self.assertEqual(self.post('/api/config', [1, 2])[0], 400)
        self.assertEqual(self.post('/api/tasks', {})[0], 400)
        self.assertEqual(self.post('/api/tasks/missing/approval', {'approved':'yes'})[0], 400)

    def test_commit_api_requires_preview_and_explicit_same_origin_approval(self):
        from cheapos.workspace import git
        task = self.engine.create_demo()
        git(task['source'], 'config', 'user.name', 'Test Operator')
        git(task['source'], 'config', 'user.email', 'operator@example.invalid')
        self.engine.start(task['id'])
        self.engine.runtimes[task['id']].thread.join(10)
        self.assertEqual(self.engine.store.get(task['id'])['status'], 'approved')
        path = '/api/tasks/' + task['id']
        from cheapos import git_workflow
        for action, method in [('preview','preview'),('publish','publish'),('status','status')]:
            publication = {'id':'publication-not-task-id', 'title':'Reviewed PR title', 'description':'Reviewed changes'}
            with patch.object(git_workflow,method,return_value=publication) as handler:
                route=path+'/pull-request-'+action
                self.assertEqual(self.request('POST',route,{})[0],403)
                handler.assert_not_called()
                response = self.post(route,{})
                self.assertEqual(response[0],200)
                self.assertEqual(json.loads(response[2]),publication)
                self.assertEqual(handler.call_count,1)
        self.assertEqual(self.request('POST', path + '/commit-preview', {}, {'Content-Type': 'application/json'})[0], 403)
        status, _, body = self.post(path + '/commit-preview', {})
        self.assertEqual(status, 200)
        preview = json.loads(body)
        data = {'approved': True, 'approval_id': preview['approval_id'], 'message': 'Fix clamp boundaries'}
        digest = json.loads(self.request('GET', path)[2])['patch_digest']
        choice = {'decision':'defer','patch_digest':digest}
        self.assertEqual(self.request('POST', path + '/commit-decision', choice, {'Content-Type':'application/json'})[0], 403)
        self.assertEqual(self.post(path + '/commit-decision', {**choice,'decision':'approve'})[0], 400)
        self.assertEqual(self.post(path + '/commit-decision', choice)[0], 200)
        self.assertEqual(self.post(path + '/commit', data)[0], 400)
        self.assertEqual(self.post(path + '/commit-decision', {**choice,'decision':'review'})[0], 200)
        self.assertEqual(self.request('POST', path + '/commit', data, {'Content-Type': 'application/json'})[0], 403)
        self.assertEqual(self.post(path + '/commit', {**data, 'approved': 'true'})[0], 400)
        status, _, body = self.post(path + '/commit', data)
        self.assertEqual(status, 200, body)
        committed = json.loads(body)
        self.assertEqual(git(task['source'], 'rev-parse', 'HEAD').strip(), committed['commit'])
        self.assertEqual(self.post(path + '/commit', data)[0], 200)
        self.assertEqual(git(task['source'], 'rev-list', '--count', 'HEAD').strip(), '2')
        self.assertEqual(json.loads(self.request('GET', path)[2])['patch'], '')

    def test_conflict_response_offers_same_chat_reconciliation_with_csrf_and_patch_guard(self):
        import hashlib
        from cheapos.workspace import git
        task = self.engine.create_demo()
        source = Path(task['source'])
        git(source, 'config', 'user.name', 'Test Operator')
        git(source, 'config', 'user.email', 'operator@example.invalid')
        Workspace(task['workspace']).write_file('new.txt', 'saved task\n')
        self.engine.refresh_changes(task)
        digest = hashlib.sha256(task['patch'].encode()).hexdigest()
        task.update(status='approved', checks=[{'passed': True, 'digest': digest, 'verification_identity': evidence_identity(task)}],
                    checkpoints=[{'decision': 'APPROVE', 'diff': task['patch'], 'verification_identity': evidence_identity(task)}])
        self.engine.store.save(task)
        (source / 'new.txt').write_text('current project\n')
        git(source, 'add', 'new.txt')
        git(source, 'commit', '-qm', 'Existing project file')
        path = '/api/tasks/' + task['id']
        status, _, body = self.post(path + '/commit-preview', {})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)['code'], 'project_conflict')
        self.assertEqual(json.loads(body)['files'], ['new.txt'])
        values = {'patch_digest': digest}
        self.assertEqual(self.request('POST', path + '/reconcile', values, {'Content-Type': 'application/json'})[0], 403)
        self.assertEqual(self.post(path + '/reconcile', {'patch_digest': 'stale'})[0], 400)
        with patch.object(self.engine, 'request', side_effect=AssertionError('Reconcile does not infer')):
            status, _, body = self.post(path + '/reconcile', values)
        self.assertEqual(status, 200, body)
        result = json.loads(body)
        self.assertEqual(result['id'], task['id'])
        self.assertEqual(result['status'], 'paused')
        self.assertEqual(result['workspace_generation'], 1)
        self.assertEqual((source / 'new.txt').read_text(), 'current project\n')
        self.assertEqual(self.post(path + '/commit-preview', {})[0], 400)

    def test_startup_status_is_read_only_and_preferences_do_not_dispatch(self):
        with patch.object(self.engine.startup, 'start') as start:
            self.assertEqual(self.request('GET', '/api/startup')[0], 200)
            self.assertEqual(self.request('GET', '/api/bootstrap')[0], 200)
            self.assertEqual(self.post('/api/startup/config', {'enabled':False})[0], 200)
            start.assert_not_called()
            self.assertEqual(self.request('POST', '/api/startup/start', {}, {'Content-Type':'application/json'})[0],403)
            start.assert_not_called()
        self.assertEqual(self.post('/api/startup/config', {'allow_cloud':'yes'})[0],400)

    def test_project_chat_and_followup_api(self):
        source = self.engine.create_demo()['source']
        status, _, body = self.post('/api/projects', {'repository':source})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['path'],source)
        config = {role:{'base_url':'http://127.0.0.1:11434/v1','model':'fixture-'+role,'input_rate':0,'output_rate':0} for role in ['worker','reviewer']}
        self.assertEqual(self.post('/api/preferences', {'execution': {'mode': 'manual'}})[0], 200)
        self.assertEqual(self.post('/api/config', config)[0],200)
        status, _, body = self.post('/api/tasks', {'repository':source,'prompt':'Hi','conversational':True})
        self.assertEqual(status,200)
        task = json.loads(body)
        self.assertEqual(task['status'],'ready')
        self.assertEqual(task['check_command'],[])
        provider = Mock()
        provider.complete.return_value = ({'role':'assistant','content':'Hello. What would you like to explore?'},{'prompt_tokens':5,'completion_tokens':5,'cost':0})
        self.engine.provider_factory = lambda role, config:provider
        self.assertEqual(self.post('/api/tasks/'+task['id']+'/start',{})[0],200)
        self.engine.runtimes[task['id']].thread.join(5)
        self.assertEqual(self.post('/api/tasks/'+task['id']+'/message',{'message':'Tell me about this project.'})[0],200)
        self.engine.runtimes[task['id']].thread.join(5)
        result = json.loads(self.request('GET','/api/tasks/'+task['id'])[2])
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertEqual(result['requests'],['Hi','Tell me about this project.'])
        self.assertEqual(result['usage']['worker']['tokens'],20)
        self.assertNotIn('messages',result)
        with patch.object(self.engine, 'start', return_value=self.engine.store.get(task['id'])) as start:
            route='/api/tasks/'+task['id']+'/start'
            self.assertEqual(self.request('POST',route,{'finish_review':True},{'Content-Type':'application/json'})[0],403)
            start.assert_not_called()
            self.assertEqual(self.post(route,{'finish_review':True})[0],200)
            start.assert_called_once_with(task['id'],{'finish_review':True})
        for value in [None, '', False]:
            self.assertEqual(self.post('/api/tasks/'+task['id']+'/message',{'message':value})[0],400)

    def test_preferences_and_limits_save_without_dispatch(self):
        status, _, body = self.post('/api/preferences', {'limits':{'dollars':0,'output_tokens':4096}})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['limits']['output_tokens'],4096)
        bootstrap = json.loads(self.request('GET','/api/bootstrap')[2])
        self.assertEqual(bootstrap['preferences']['limits']['dollars'],0)
        task=self.engine.create_demo()
        status, _, body = self.post('/api/tasks/'+task['id']+'/limits', {'limits':{'dollars':0}})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['status'],'ready')
        self.assertEqual(self.engine.runtimes,{})
        self.assertEqual(self.post('/api/projects',{'repository':''})[0],400)

    def test_gateway_api_is_read_only_until_authorized_and_redacts_key(self):
        with patch.object(self.engine.gateway, 'refresh') as refresh:
            for path in ['/api/gateway', '/api/gateway/models']:
                self.assertEqual(self.request('GET', path)[0], 200)
            self.assertEqual(self.request('POST', '/api/gateway/start', {}, {'Content-Type': 'application/json'})[0], 403)
            refresh.assert_not_called()
        status, _, body = self.post('/api/gateway/config', {'api_key': 'fixture-client-secret', 'auto_start': False})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['key_configured'])
        self.assertNotIn(b'fixture-client-secret', body)
        self.assertNotIn(b'fixture-client-secret', self.request('GET', '/api/bootstrap')[2])
        self.assertNotIn('fixture-client-secret', self.engine.gateway.path.read_text())
        self.assertEqual(self.post('/api/gateway/stop', {})[0], 400)
        self.assertEqual(self.post('/api/gateway/config', {'base_url': 'https://example.com/v1'})[0], 400)

    def test_gateway_changes_are_rejected_during_a_task(self):
        runtime = Mock()
        runtime.task = {'status': 'running'}
        runtime.thread.is_alive.return_value = True
        self.engine.runtimes['fixture'] = runtime
        for path in ['/api/gateway/config', '/api/gateway/stop']:
            status, _, body = self.post(path, {})
            self.assertEqual(status, 400)
            self.assertIn(b'Pause the active task', body)

    def test_rollback_endpoint(self):
        task = self.engine.create_demo()
        ws = Workspace(task['workspace'])
        ws.write_file('demo_file.py', 'print("hello")\n')
        self.engine.refresh_changes(task)
        task['checkpoints'].append({
            'number': 1,
            'diff': task['patch'],
            'worker_summary': 'Added demo_file.py',
            'decision': 'APPROVE',
            'feedback': 'Good'
        })
        self.engine.store.save(task)

        # Modify file
        ws.write_file('extra.txt', 'extra\n')

        # Call rollback endpoint
        status, _, body = self.post(f'/api/tasks/{task["id"]}/rollback', {'checkpoint': 1})
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result['patch'], task['checkpoints'][0]['diff'])
        self.assertFalse(ws.path('extra.txt').exists())

        # Invalid requests
        self.assertEqual(self.post(f'/api/tasks/{task["id"]}/rollback', {'checkpoint': 'invalid'})[0], 400)
        self.assertEqual(self.post(f'/api/tasks/{task["id"]}/rollback', {})[0], 400)

    def test_steer_and_headroom_endpoints(self):
        task = self.engine.create_demo()
        task['demo'] = False
        self.engine.store.save(task)

        # Steer endpoint
        status, _, body = self.post(f'/api/tasks/{task["id"]}/steer', {'message': 'Steer guidance from test'})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data['steered'])
        self.assertEqual(data['task']['steer_guidance'], 'Steer guidance from test')

        # Steer validation
        self.assertEqual(self.post(f'/api/tasks/{task["id"]}/steer', {'message': ''})[0], 400)
        self.assertEqual(self.post(f'/api/tasks/{task["id"]}/steer', {})[0], 400)

        # Headroom endpoint
        status, _, body = self.post(f'/api/tasks/{task["id"]}/headroom', {'reviewer_tokens': 50000, 'worker_turns': 5})
        self.assertEqual(status, 200)
        headroom_task = json.loads(body)
        self.assertGreaterEqual(headroom_task['limits']['reviewer_tokens'], 250000)

    def test_list_directories(self):
        base_path = Path(self.temp.name)
        (base_path / 'project1').mkdir(exist_ok=True)
        (base_path / 'project2').mkdir(exist_ok=True)
        (base_path / 'dir1').mkdir(exist_ok=True)
        (base_path / 'dir1/file1.txt').touch()

        # Listing base directory
        status, _, body = self.request('GET', '/api/list-directories?path=' + str(base_path))
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data['current_path'], str(base_path.resolve()))
        items = data['items']
        names = [item['name'] for item in items]
        self.assertIn('project1', names)

        # Listing subdirectory
        status, _, body = self.request('GET', '/api/list-directories?path=' + str(base_path / 'dir1'))
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data['current_path'], str((base_path / 'dir1').resolve()))
        items = data['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['name'], 'file1.txt')

        # Security: root and system access rejected
        status, _, _ = self.request('GET', '/api/list-directories?path=/')
        self.assertEqual(status, 403)
        status, _, _ = self.request('GET', '/api/list-directories?path=/var')
        self.assertEqual(status, 403)
        status, _, _ = self.request('GET', '/api/list-directories?path=/etc')
        self.assertEqual(status, 403)
        status, _, _ = self.request('GET', '/api/list-directories?path=/bin')
        self.assertEqual(status, 403)

        # An unreadable directory must not look like a successfully empty folder.
        with patch.object(Path, 'iterdir', side_effect=PermissionError):
            status, _, body = self.request('GET', '/api/list-directories?path=' + str(base_path))
        self.assertEqual(status, 403)
        self.assertIn('Permission denied', json.loads(body)['error'])
        status, _, _ = self.request('GET', '/api/list-directories?path=' + str(base_path / 'missing'))
        self.assertEqual(status, 404)

    def test_create_project_endpoint(self):
        base_path = Path(self.temp.name)
        status, _, body = self.post('/api/projects/create', {
            'name': 'new-sample-proj',
            'parent': str(base_path),
            'init_git': True
        })
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue((base_path / 'new-sample-proj/.git').is_dir())
        self.assertEqual(data['name'], 'new-sample-proj')

        # Project creation with init_git: false (finding 8)
        status_nogit, _, body_nogit = self.post('/api/projects/create', {
            'name': 'folder-only-proj',
            'parent': str(base_path),
            'init_git': False
        })
        self.assertEqual(status_nogit, 200)
        data_nogit = json.loads(body_nogit)
        self.assertEqual(data_nogit['name'], 'folder-only-proj')
        self.assertFalse(data_nogit['git'])
        self.assertTrue((base_path / 'folder-only-proj').is_dir())
        self.assertFalse((base_path / 'folder-only-proj/.git').exists())

        # Reject traversal names rather than silently sanitizing them into another name.
        for name in ('.', '..', ' .. ', 'subdir/name', 'subdir\\name', 'bad\0name'):
            with self.subTest(name=name):
                status, _, _ = self.post('/api/projects/create', {
                    'name': name, 'parent': str(base_path), 'init_git': False})
                self.assertEqual(status, 400)
        self.assertEqual(sorted(p.name for p in base_path.iterdir()),
                         ['folder-only-proj', 'new-sample-proj', 'state'])

        # System parent directory rejected (finding 10)
        status_blocked, _, _ = self.post('/api/projects/create', {
            'name': 'bad-proj',
            'parent': '/var',
            'init_git': False
        })
        self.assertEqual(status_blocked, 400)


class FakeModelHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header('x-omniroute-route-class', 'CLIENT_API')
        self.end_headers()
        self.wfile.write(b'{"data":[{"id":"worker"},{"id":"reviewer"}]}')

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append((self.path, dict(self.headers), body))
        if self.server.mode == 'redirect':
            self.send_response(302)
            self.send_header('Location', 'http://127.0.0.1:1/leak')
            self.end_headers()
            return
        if self.server.mode == 'limit':
            self.send_response(429)
            self.end_headers()
            return
        if self.server.mode == 'stream':
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.end_headers()
            for data in [
                {'choices':[{'index':0,'delta':{'reasoning':'Checking the files.'}}]},
                {'choices':[{'index':0,'delta':{'content':'Ready.'},'finish_reason':'stop'}]},
                {'choices':[],'usage':{'prompt_tokens':12,'completion_tokens':7}}
            ]:
                self.wfile.write(('data: '+json.dumps(data)+'\n\n').encode())
                self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n')
            return
        message = self.server.responder(body) if hasattr(self.server, 'responder') else {'role':'assistant','content':None,'tool_calls':[{'id':'abc','type':'function','function':{'name':'list_files','arguments':'{}'}}]}
        data = {'choices':[{'message':message}], 'usage':{'prompt_tokens':12,'completion_tokens':7,'cost':.00001}}
        encoded = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeModelHandler)
        self.server.requests = []
        self.server.mode = 'normal'
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval":0.01}, daemon=True)
        self.thread.start()
        self.provider = ChatProvider({'base_url':f'http://127.0.0.1:{self.server.server_port}/v1','model':'fixture','key_env':'CHEAPOS_TEST_KEY'}, 'fixture-secret')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_chat_adapter_sends_tools_and_parses_usage(self):
        message, usage = self.provider.complete([{'role':'user','content':'Hello'}], [{'type':'function'}], 256)
        path, headers, body = self.server.requests[0]
        self.assertEqual(path, '/v1/chat/completions')
        self.assertEqual(headers['Authorization'], 'Bearer fixture-secret')
        self.assertEqual(body['max_tokens'], 256)
        self.assertFalse(body['parallel_tool_calls'])
        self.assertEqual(message['tool_calls'][0]['id'], 'abc')
        self.assertEqual(usage['prompt_tokens'], 12)

    def test_streaming_adapter_delivers_thinking_and_answer(self):
        self.server.mode='stream'
        seen=[]
        message,usage=self.provider.complete_with_progress([{'role':'user','content':'Hi'}],[],128,lambda kind,text:seen.append((kind,text)),lambda:False)
        body=self.server.requests[-1][2]
        self.assertTrue(body['stream'])
        self.assertEqual(body['stream_options'],{'include_usage':True})
        self.assertEqual(seen,[('thinking','Checking the files.'),('answer','Ready.')])
        self.assertEqual(message['content'],'Ready.')
        self.assertEqual(usage['completion_tokens'],7)

    def test_omniroute_greeting_streams_without_tools_or_repository_context(self):
        self.server.mode='stream'
        provider=OmniRouteGateway({**self.provider.config,'gateway':'omniroute'},'gateway-client-key')
        self.assertTrue(provider.streams_output)
        seen=[]
        message,usage=provider.greet(GREETING,lambda kind,text:seen.append((kind,text)),lambda:False)
        _,headers,body=self.server.requests[-1]
        self.assertEqual(headers['Authorization'],'Bearer gateway-client-key')
        self.assertEqual(body['messages'],GREETING)
        self.assertNotIn('tools',body)
        self.assertTrue(body['stream'])
        self.assertEqual(body['max_tokens'],512)
        self.assertEqual(message['content'],'Ready.')
        self.assertEqual(seen[0][0],'thinking')
        self.assertEqual(usage['completion_tokens'],7)

    def test_local_greeting_is_brief_without_disabling_normal_task_thinking(self):
        self.server.mode='stream'
        with patch('cheapos.providers.is_local_ollama',return_value=True):
            self.provider.greet(GREETING,lambda *args:None,lambda:False)
        body=self.server.requests[-1][2]
        self.assertEqual(body['max_tokens'],128)
        self.assertEqual(body['reasoning_effort'],'none')
        self.server.mode='normal'
        self.provider.complete([{'role':'user','content':'A normal task'}],[],256)
        self.assertNotIn('reasoning_effort',self.server.requests[-1][2])

    def test_redirect_is_not_followed(self):
        self.server.mode = 'redirect'
        with self.assertRaisesRegex(ProviderError, 'HTTP 302'):
            self.provider.complete([], [], 256)
        self.assertEqual(len(self.server.requests), 1)

    def test_rate_limit_is_not_retried(self):
        self.server.mode = 'limit'
        with self.assertRaisesRegex(ProviderError, 'rate limit'):
            self.provider.complete([], [], 256)
        self.assertEqual(len(self.server.requests), 1)

    def test_full_workflow_through_keyless_gateway_http(self):
        self.run_full_workflow()

    def test_full_workflow_through_omniroute_gateway_http(self):
        self.run_full_workflow(managed=True)

    def run_full_workflow(self, managed=False):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory, fixture_delay=0)
            task = engine.create_demo()
            script = dict(task)
            reviews = []
            def respond(body):
                role = body['model']
                if role == 'reviewer':
                    reviews.append(body)
                    script['checkpoints'] = [None] * len(reviews)
                return engine.fixture_response(script, role)
            self.server.responder = respond
            task['demo'] = False
            task['providers'] = {role: {'base_url':self.provider.config['base_url'], 'model':role, 'key_env':'CHEAPOS_TEST_KEY', 'input_rate':1, 'output_rate':2} for role in ['worker', 'reviewer']}
            engine.gateway.configure({'base_url': self.provider.config['base_url'], 'api_key': 'fixture-client-secret' if managed else ''})
            engine.gateway.startup()
            engine.gateway.thread.join(5)
            for provider in task['providers'].values():
                provider['gateway'] = 'omniroute'
            engine.store.save(task)
            engine.start(task['id'])
            engine.runtimes[task['id']].thread.join(20)
            result = engine.store.get(task['id'])
            engine.shutdown()
            self.assertEqual(result['status'], 'approved', result['error'])
            self.assertEqual(len(self.server.requests), 9)
            if managed:
                self.assertTrue(all(headers.get('Authorization') == 'Bearer fixture-client-secret' for _, headers, _ in self.server.requests))
                self.assertTrue(all(body['stream'] for _, _, body in self.server.requests))
            else:
                self.assertTrue(all(not headers.get('Authorization') for _, headers, _ in self.server.requests))
            self.assertEqual(len(reviews), 2)
            self.assertEqual(result['usage']['worker']['tokens'], 7 * 19)
            self.assertEqual(result['usage']['reviewer']['tokens'], 2 * 19)
            self.assertAlmostEqual(result['usage']['cost'], .00009)
            first_checkpoint = json.loads(reviews[0]['messages'][1]['content'])
            self.assertEqual(first_checkpoint['original_task'], task['prompt'])
            self.assertTrue(first_checkpoint['checks']['passed'])
            self.assertIn('return max(lower', first_checkpoint['diff'])
            # Full worker conversations are not forwarded into checkpoint reviews.
            self.assertEqual(len(reviews[0]['messages']), 2)


if __name__ == '__main__':
    unittest.main()
