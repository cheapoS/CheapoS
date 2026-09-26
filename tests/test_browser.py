"""Small file/in-memory browser lifecycle cases; no browser install, sleeps or Git runs."""
import copy
import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos.browser import Browsers, Driver, candidate, inputs
from cheapos.preview import config
from cheapos import tools, vision, review_assessment


class BrowserTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.task = {'id': 'task', 'source': str(self.root / 'project'),
                     'workspace': str(self.root / 'workspace'), 'prompt': 'Verify UI', 'tool_actions': 0}
        Path(self.task['workspace']).mkdir()
        (Path(self.task['workspace']) / 'app.html').write_text('<button>Click</button>')
        self.engine = SimpleNamespace(store=SimpleNamespace(root=self.root, get=lambda _: self.task, save=Mock()),
            runtimes={}, lock=threading.RLock(), event=Mock(), previews=SimpleNamespace(stop=Mock(), launch=Mock(), settings=Mock(return_value={})))
        self.manager = Browsers(self.engine)
        self.engine.browsers = self.manager
        self.runtime = SimpleNamespace(task=self.task, guard=Mock(), thread=Mock(is_alive=lambda: False))
        self.binding = {'task': 'task', 'workspace': 'registered'}
        self.cfg = config({'command': 'python3 app.py', 'url': 'http://127.0.0.1:5174'})
        for target, value in [('cheapos.browser.task_commands.binding', self.binding),
                              ('cheapos.browser.git', 'app.html\0')]:
            mocked = patch(target, return_value=value)
            mocked.start(); self.addCleanup(mocked.stop)

    def grant(self):
        self.manager.permission('task', {'enabled': True, 'directory': self.task['workspace'], 'config': self.cfg})

    def session(self):
        self.grant()
        run = {'status': 'running', 'logs': 'ready', 'root': str(self.root)}
        driver = Mock(call=Mock(return_value={'url': self.cfg['url'], 'text': 'Clicked', 'console': []}))
        session = {'id': 'session', 'candidate': candidate(self.task), 'config': self.cfg, 'run': run, 'driver': driver, 'inputs': inputs(self.task['workspace'])}
        self.manager.sessions['task'] = session
        return session

    def test_model_cannot_grant_and_changed_binding_denies(self):
        with self.assertRaises(ValueError):
            self.manager.action(self.task, {'action': 'start', 'enabled': True, 'config': self.cfg}, self.runtime)
        for value in ('yes', 1, None):
            with self.assertRaises(ValueError): self.manager.permission('task', {'enabled': value})
        self.grant()
        with patch('cheapos.browser.task_commands.binding', return_value={'task': 'other'}):
            with self.assertRaises(ValueError): self.manager.authorized(self.task)
        self.engine.previews.launch.assert_not_called()

    def test_grant_is_exact_and_revoke_stops_both_processes(self):
        session = self.session()
        self.assertEqual(self.task['browser_permission']['config'], self.cfg)
        self.manager.permission('task', {'enabled': False})
        session['driver'].close.assert_called_once()
        self.engine.previews.stop.assert_called_once_with(session['run'])
        self.assertNotIn('browser_permission', self.task)
        self.assertFalse(self.manager.sessions)

    def test_active_grant_requires_pause_but_revocation_remains_available(self):
        self.engine.runtimes['task'] = self.runtime
        self.runtime.thread.is_alive = lambda: True
        with self.assertRaisesRegex(ValueError, 'Pause'): self.grant()
        self.manager.permission('task', {'enabled': False})
        self.assertFalse(self.manager.permission('task', {})['enabled'])

    def test_start_freezes_uncommitted_candidate_and_uses_preview_launcher(self):
        self.grant()
        def snapshot(source, destination):
            self.assertEqual(source, self.task['workspace'])
            destination.mkdir(parents=True)
            (destination / 'app.html').write_bytes((Path(source) / 'app.html').read_bytes())
            return None, {'skipped': []}
        with patch('cheapos.browser.Workspace.snapshot', side_effect=snapshot) as freeze, \
             patch('cheapos.browser.socket.socket'), patch('cheapos.browser.threading.Thread') as thread, \
             patch('cheapos.browser.tempfile.mkdtemp', return_value=str(self.root / 'copy')):
            result = self.manager.action(self.task, {'action': 'start'}, self.runtime)
        self.assertEqual(result['status'], 'starting')
        self.assertEqual(result['candidate'], candidate(self.task))
        self.assertTrue(self.manager.sessions['task']['run']['prepared'])
        self.assertIs(thread.call_args.kwargs['target'], self.engine.previews.launch)
        thread.return_value.start.assert_called_once(); freeze.assert_called_once()
        self.assertEqual((Path(self.task['workspace']) / 'app.html').read_text(), '<button>Click</button>')

    def test_snapshot_changes_and_occupied_port_cannot_start(self):
        self.grant()
        with patch('cheapos.browser.socket.socket') as socket, patch('cheapos.browser.Workspace.snapshot') as freeze:
            socket.return_value.__enter__.return_value.bind.side_effect = OSError('busy')
            with self.assertRaisesRegex(ValueError, 'port is in use'): self.manager.start(self.task, self.cfg, self.runtime.guard)
            freeze.assert_not_called()
        with patch('cheapos.browser.socket.socket'), patch('cheapos.browser.Workspace.snapshot', return_value=(None, {'skipped': []})), \
             patch('cheapos.browser.candidate', side_effect=['before', 'after']), \
             patch('cheapos.browser.tempfile.mkdtemp', return_value=str(self.root / 'copy')):
            with self.assertRaisesRegex(ValueError, 'Candidate changed'): self.manager.start(self.task, self.cfg, self.runtime.guard)
        self.assertFalse(self.manager.sessions)

    def test_actions_are_bounded_and_origin_scoped(self):
        for args in ({'action': 'navigate', 'url': 'https://example.com'},
                     {'action': 'navigate', 'url': 'http://127.0.0.1:9999'},
                     {'action': 'navigate', 'url': 'http://user@127.0.0.1:5174'},
                     {'action': 'fill', 'selector': '#field', 'value': 'x' * 4001},
                     {'action': 'click', 'selector': 'x' * 501},
                     {'action': 'press', 'selector': '#field', 'value': 'Control+L'},
                     {'action': 'viewport', 'width': True, 'height': 600},
                     {'action': 'evaluate', 'value': 'fetch(...)'}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.manager.arguments(args['action'], args, self.cfg)
        self.assertEqual(self.manager.arguments('navigate', {'url': '/next'}, self.cfg)['url'], self.cfg['url'] + '/next')
        self.assertEqual(self.manager.arguments('viewport', {'width': 375, 'height': 800}, self.cfg)['width'], 375)

    def test_candidate_changes_reject_actions_and_retained_evidence(self):
        session = self.session()
        record = self.manager.action(self.task, {'action': 'observe'}, self.runtime)
        (Path(self.task['workspace']) / 'app.html').write_text('Changed')
        with self.assertRaisesRegex(ValueError, 'stale candidate'): self.manager.read(self.task, record['id'])
        with self.assertRaisesRegex(ValueError, 'candidate or consent changed'):
            self.manager.action(self.task, {'action': 'click', 'selector': 'button'}, self.runtime)
        self.assertEqual(session['driver'].call.call_count, 1)
        session['driver'].close.assert_called_once()
        self.assertFalse(self.manager.read(self.task)['records'][0]['current'])

    def test_screenshot_survives_restart_but_not_tampering_or_new_directions(self):
        session = self.session()
        data = b'\x89PNG\r\n\x1a\nfixture'
        def capture(args, guard):
            Path(args['path']).write_bytes(data)
            return {'url': self.cfg['url'], 'console': []}
        session['driver'].call.side_effect = capture
        record = self.manager.action(self.task, {'action': 'screenshot'}, self.runtime)
        self.assertFalse(record['approved'])
        self.assertEqual(record['image_digest'], hashlib.sha256(data).hexdigest())
        restarted = Browsers(self.engine)
        restored = json.loads(json.dumps(self.task))
        self.assertFalse(restarted.sessions)
        self.assertEqual(restarted.read(restored, record['id']), record)
        self.assertEqual(restarted.authorized(restored), self.cfg)
        image = restarted.image_path(restored, record['image'])
        image.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'screenshot changed'): restarted.read(restored, record['id'])
        image.write_bytes(data)
        restored['requests'] = ['New direction']
        with self.assertRaisesRegex(ValueError, 'stale candidate'): restarted.read(restored, record['id'])
        self.assertFalse(self.task.get('checks'))

    def test_cancellation_or_revocation_during_call_closes_session_without_receipt(self):
        for stop in ('cancel', 'revoke'):
            with self.subTest(stop=stop):
                self.runtime.guard.reset_mock(side_effect=True)
                session = self.session()
                def call(*args):
                    if stop == 'cancel': raise InterruptedError('paused')
                    self.manager.permission('task', {'enabled': False})
                    return {'text': 'must not retain'}
                session['driver'].call.side_effect = call
                with self.assertRaises(InterruptedError): self.manager.action(self.task, {'action': 'observe'}, self.runtime)
                self.assertFalse(self.manager.sessions)
                self.assertFalse(self.manager.read(self.task)['records'])

    def test_driver_open_failure_does_not_become_success_or_approval(self):
        session = self.session(); session.pop('driver')
        with patch('cheapos.browser.Driver') as driver:
            driver.return_value.call.return_value = {'error': 'runtime unavailable'}
            result = self.manager.action(self.task, {'action': 'open'}, self.runtime)
        self.assertIn('error', result)
        driver.return_value.close.assert_called_once()
        self.assertNotIn('driver', session)
        self.assertFalse(self.manager.read(self.task)['records'])

    def test_independent_image_inspection_uses_current_digest_and_metered_reviewer(self):
        session = self.session()
        def capture(args, guard):
            Path(args['path']).write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            return {'text': 'Button visible'}
        session['driver'].call.side_effect = capture
        record = self.manager.action(self.task, {'action': 'screenshot'}, self.runtime)
        self.task['providers'] = {'reviewer': {'model': 'independent'}}
        self.engine._request = Mock(return_value={'content': 'The button is visible.'})
        result = vision.inspect_image_tool(self.engine, self.task, {'path': record['image']}, self.runtime, role='reviewer')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(self.engine._request.call_args.kwargs, {'tools': [], 'role': 'reviewer', 'purpose': 'vision'})
        proof = review_assessment.prepare('candidate', {'diff': 'source'}, ['Button visible'])
        observed = review_assessment.observation(proof, 'inspect_image', {'path': record['image']}, result)
        self.assertEqual(proof['sources'][observed['evidence_id']]['kind'], 'image')
        self.task['workspace_generation'] = 2
        denied = vision.inspect_image_tool(self.engine, self.task, {'path': record['image']}, self.runtime, role='reviewer')
        self.assertIn('stale', denied['error'])
        self.assertEqual(self.engine._request.call_count, 1)

    def test_driver_guard_interrupts_without_waiting_or_replaying(self):
        driver = Driver.__new__(Driver)
        driver.process = Mock(); driver.replies = Mock(); driver.close = Mock()
        guard = Mock(side_effect=[None, InterruptedError('paused')])
        with self.assertRaises(InterruptedError): driver.call({'action': 'observe'}, guard)
        driver.close.assert_called_once(); driver.replies.get.assert_not_called()

    def test_read_only_request_cannot_execute_even_with_saved_grant(self):
        self.grant()
        from cheapos.work_policy import READ_ONLY_STARTERS
        self.task.update(conversational=True, prompt=READ_ONLY_STARTERS[0])
        with self.assertRaisesRegex(ValueError, 'task state'):
            self.manager.action(self.task, {'action': 'start'}, self.runtime)
        for available in (tools.WORKER_TOOLS, tools.CHAT_TOOLS, tools.UNATTENDED_TOOLS):
            self.assertIn('browser_preview', {t['function']['name'] for t in available})
        self.assertNotIn('browser_preview', {t['function']['name'] for t in tools.REVIEW_TOOLS})
        self.assertIn('read_browser_evidence', {t['function']['name'] for t in tools.REVIEW_TOOLS})

    def test_final_review_entry_reads_retained_image_then_independently_approves(self):
        from tests.test_review_units import ReviewWorkflowTests
        fixture = ReviewWorkflowTests()
        task, engine, runtime, manifest, packet = fixture.fixture(1)
        engine.browsers = SimpleNamespace(read=Mock(return_value={
            'id': 'a' * 32, 'candidate': 'current', 'image': 'browser:' + 'a' * 32,
            'result': {'text': 'Button visible'}, 'approved': False}))
        phases = []
        def respond(rt, messages, offered, role, **kwargs):
            names = {t['function']['name'] for t in offered}
            self.assertIn('read_browser_evidence', names)
            self.assertIn('inspect_image', names)
            self.assertNotIn('browser_preview', names)
            phases.append(copy.deepcopy(messages))
            if len(phases) == 1:
                return fixture.call('read_browser_evidence', {'evidence_id': 'a' * 32}, 'evidence')
            if len(phases) == 2:
                self.assertIn('browser:' + 'a' * 32, json.dumps(messages))
                return fixture.call('inspect_image', {'path': 'browser:' + 'a' * 32}, 'image')
            result = fixture.approve(rt, messages, offered, role, **kwargs)
            image = next(json.loads(row['content'])['evidence_handle'] for row in messages
                         if row.get('role') == 'tool' and row.get('tool_call_id') == 'image')
            args = json.loads(result['tool_calls'][0]['function']['arguments'])
            for claim in args['assessments']:
                if claim['target'] not in {'verification', 'limitations'}: claim['evidence'] = [image]
            result['tool_calls'][0]['function']['arguments'] = json.dumps(args)
            return result
        engine.request.side_effect = respond
        before = copy.deepcopy(task)
        with patch('cheapos.vision.inspect_image_tool', return_value={'status': 'success', 'analysis': 'The expected button is visible.', 'image_digest': 'digest'}) as inspect:
            result = fixture.run_workflow(engine, runtime, manifest, packet)
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(len(phases), 3)
        self.assertEqual(inspect.call_args.kwargs['role'], 'reviewer')
        self.assertEqual(engine.browsers.read.call_count, 1)
        self.assertEqual(fixture.run_workflow(engine, runtime, manifest, packet), result)
        self.assertEqual(len(phases), 3)
        for key in ('checks', 'usage', 'providers', 'limits'): self.assertEqual(task[key], before[key])
        engine.checks.assert_not_called()

    def test_changed_configuration_and_setup_mutation_invalidate_evidence(self):
        session = self.session()
        record = self.manager.action(self.task, {'action': 'observe'}, self.runtime)
        self.manager.permission('task', {'enabled': True, 'directory': self.task['workspace'], 'config': {**self.cfg, 'command': 'python3 different.py'}})
        with self.assertRaisesRegex(ValueError, 'different preview configuration'):
            self.manager.read(self.task, record['id'])
        session = self.session()
        session['inputs'] = [['app.html', 'different digest', False]]
        with self.assertRaisesRegex(ValueError, 'changed candidate source files'):
            self.manager.action(self.task, {'action': 'observe'}, self.runtime)
        session['driver'].call.assert_not_called()

    def test_permission_http_route_requires_local_token_and_passes_exact_body(self):
        import io
        from email.message import Message
        from cheapos.server import LocalHandler
        handler = LocalHandler.__new__(LocalHandler)
        handler.server = SimpleNamespace(engine=self.engine, token='local-token', server_address=('127.0.0.1', 5173), server_port=5173)
        handler.client_address = ('127.0.0.1', 2222)
        handler.path = '/api/tasks/task/browser-permission'
        handler.reply = Mock()
        body = json.dumps({'enabled': True, 'directory': self.task['workspace'], 'config': self.cfg}).encode()
        handler.headers = Message()
        handler.headers['Host'] = '127.0.0.1:5173'
        handler.headers['Content-Type'] = 'application/json'
        handler.headers['Content-Length'] = str(len(body))
        handler.rfile = io.BytesIO(body)
        handler.do_POST()
        self.assertEqual(handler.reply.call_args.args[1], 403)
        self.assertNotIn('browser_permission', self.task)
        handler.headers['X-CheapOS-Token'] = 'local-token'
        handler.do_POST()
        self.assertEqual(handler.reply.call_args.args[0], {'enabled': True})
        self.assertEqual(self.task['browser_permission']['config'], self.cfg)

    def test_stale_operator_dialog_and_missing_evidence_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'Task copy changed'):
            self.manager.permission('task', {'enabled': True, 'directory': '/old/workspace', 'config': self.cfg})
        with self.assertRaisesRegex(ValueError, 'missing or unavailable'):
            self.manager.read(self.task, 'a' * 32)
        self.assertNotIn('browser_permission', self.task)

    def test_revoke_during_browser_launch_closes_unregistered_driver(self):
        session = self.session(); session.pop('driver')
        driver = Mock()
        def launch():
            self.manager.permission('task', {'enabled': False})
            return driver
        with patch('cheapos.browser.Driver', side_effect=launch):
            with self.assertRaisesRegex(InterruptedError, 'stopped during launch'):
                self.manager.action(self.task, {'action': 'open'}, self.runtime)
        driver.close.assert_called_once()
        driver.call.assert_not_called()
        self.assertFalse(self.manager.sessions)

    def test_new_receipt_ids_do_not_reset_repeated_browser_observations(self):
        from cheapos.engine import observation_key
        record = {'id': 'first', 'created_at': 1, 'session': 'one', 'candidate': 'same',
                  'config_digest': 'config', 'result': {'text': 'Same page'}, 'image_digest': 'pixels'}
        another = {**record, 'id': 'second', 'created_at': 2, 'session': 'two'}
        args = {'action': 'observe'}
        self.assertEqual(observation_key('browser_preview', args, record), observation_key('browser_preview', args, another))
        another['result'] = {'text': 'Changed page'}
        self.assertNotEqual(observation_key('browser_preview', args, record), observation_key('browser_preview', args, another))
