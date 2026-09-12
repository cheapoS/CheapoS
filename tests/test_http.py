import http.client
import json
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cheapos.engine import Engine
from cheapos.providers import ChatProvider, ProviderError
from cheapos.server import LocalServer


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = Engine(Path(self.temp.name) / 'state')
        self.server = LocalServer(('127.0.0.1', 0), Path(__file__).resolve().parent.parent / 'dist', self.engine)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
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

    def test_bootstrap_and_static_files_without_signin(self):
        status, headers, body = self.request('GET', '/api/bootstrap')
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(data['app'], 'CheapOS')
        self.assertEqual(data['token'], self.server.token)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        for path in ['/', '/styles.css', '/guidance.js', '/app.js']:
            self.assertEqual(self.request('GET', path)[0], 200)

    def test_cross_site_and_dns_rebinding_blocked(self):
        for headers in [{'Host': 'evil.example'}, {'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}]:
            self.assertEqual(self.request('GET', '/api/bootstrap', headers=headers)[0], 403)
        self.assertEqual(self.request('POST', '/api/demo', {}, {'Content-Type': 'application/json'})[0], 403)
        self.assertEqual(self.engine.store.list(), [])

    def test_private_paths_are_not_served(self):
        for path in ['/README.md', '/.git/config', '/.cheapos/config.json', '/../run.py', '/%2e%2e/run.py', '/api/tasks/../../config']:
            self.assertEqual(self.request('GET', path)[0], 404, path)

    def test_task_creation_and_keys_redacted(self):
        status, _, body = self.post('/api/demo', {})
        self.assertEqual(status, 200)
        task = json.loads(body)
        self.assertEqual(task['status'], 'ready')
        self.assertNotIn('messages', task)
        self.assertEqual(self.request('GET', '/api/tasks/'+task['id'])[0], 200)
        status, headers, body = self.request('GET', '/api/tasks/'+task['id']+'/patch')
        self.assertEqual(status, 200)
        self.assertIn('attachment', headers['Content-Disposition'])
        config = {role: {'base_url': 'https://example.invalid/v1', 'model':'fixture', 'input_rate':0, 'output_rate':0, 'api_key':'private-test-value'} for role in ['worker', 'reviewer']}
        status, _, body = self.post('/api/config', config)
        self.assertEqual(status, 200)
        self.assertNotIn(b'private-test-value', body)
        self.assertNotIn(b'private-test-value', self.request('GET', '/api/bootstrap')[2])
        self.assertNotIn('private-test-value', (self.engine.store.root / 'config.json').read_text())

    def test_invalid_json_shape_is_rejected(self):
        self.assertEqual(self.post('/api/config', [1, 2])[0], 400)
        self.assertEqual(self.post('/api/tasks', {})[0], 400)
        self.assertEqual(self.post('/api/tasks/missing/approval', {'approved':'yes'})[0], 400)

    def test_project_chat_and_followup_api(self):
        source = self.engine.create_demo()['source']
        status, _, body = self.post('/api/projects', {'repository':source})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['path'],source)
        config = {role:{'base_url':'http://127.0.0.1:1/v1','model':'fixture','input_rate':0,'output_rate':0} for role in ['worker','reviewer']}
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
        runtime.thread.is_alive.return_value = True
        self.engine.runtimes['fixture'] = runtime
        for path in ['/api/gateway/config', '/api/gateway/stop']:
            status, _, body = self.post(path, {})
            self.assertEqual(status, 400)
            self.assertIn(b'Pause the active task', body)


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
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
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

    def test_full_workflow_through_chat_completions_http(self):
        self.run_full_workflow()

    def test_full_workflow_through_omniroute_gateway_http(self):
        self.run_full_workflow(managed=True)

    def run_full_workflow(self, managed=False):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory)
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
            if managed:
                engine.gateway.configure({'base_url': self.provider.config['base_url'], 'api_key': 'fixture-client-secret'})
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
