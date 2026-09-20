"""Restart persistence and acknowledgement with tiny records and deferred threads."""
import io
import json
import tempfile
import threading
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_runs
from cheapos import integration_preparation, task_settings
from cheapos.omniroute import OmniRouteManager
from cheapos.project_permissions import ProjectTestGrants
from cheapos.providers import ProviderError
from cheapos.server import LocalHandler
from cheapos.storage import Store, write_json


class UncopyableHistory(list):
    def __deepcopy__(self, memo):
        raise AssertionError('Restart traversed unrelated execution history')


class RestartTests(unittest.TestCase):
    def test_connection_probe_does_not_load_bootstrap_state(self):
        handler = LocalHandler.__new__(LocalHandler)
        # No configuration, task store or project discovery is available here.
        handler.server = SimpleNamespace(token='new-process', engine=object())
        handler.path = '/api/connection'
        handler.trusted = Mock(return_value=True)
        handler.reply = Mock()
        handler.do_GET()
        handler.reply.assert_called_once_with({'app': 'CheapOS', 'token': 'new-process'})
        handler.trusted.assert_called_once_with()
        handler.reply.reset_mock()
        handler.trusted.return_value = False
        handler.do_GET()
        handler.reply.assert_not_called()

    def test_startup_metadata_copies_are_detached_and_do_not_traverse_history(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            store.tasks['saved'] = {'id': 'saved', 'created_at': '2026-09-19',
                'snapshot': {'source': '/project'}, 'events': UncopyableHistory()}
            records = store.list(fields=('id', 'snapshot', 'missing'))
            self.assertEqual(records, [{'id': 'saved', 'snapshot': {'source': '/project'}}])
            records[0]['snapshot']['source'] = '/changed'
            self.assertEqual(store.tasks['saved']['snapshot']['source'], '/project')
            store.tasks['saved']['events'] = ['original']
            full = store.list()[0]
            self.assertEqual(full['events'], ['original'])
            full['events'].clear()
            self.assertEqual(store.tasks['saved']['events'], ['original'])

    def test_permission_registration_uses_metadata_and_does_not_restore_grants(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            source = store.root / 'project'
            source.mkdir()
            (source / '.git').mkdir()
            workspace = store.root / 'tasks/saved/workspace'
            workspace.mkdir(parents=True)
            (workspace / '.git').mkdir()
            store.tasks['saved'] = {'id': 'saved', 'created_at': '2026-09-19',
                'source': str(source), 'workspace': str(workspace),
                'snapshot': {'source': str(source)}, 'events': UncopyableHistory(),
                'command_grants': ['previous session']}
            permissions = ProjectTestGrants(store)
            self.assertIn('saved', permissions.workspaces)
            self.assertEqual(permissions.grants, {})
            store.tasks['saved']['snapshot']['source'] = '/different'
            self.assertEqual(ProjectTestGrants(store).workspaces, {})

    def test_restoration_dispatches_only_pending_saved_operations(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            base = {'created_at': '2026-09-19', 'usage': {'tokens': 123},
                'checks': [{'passed': True}], 'events': UncopyableHistory()}
            store.tasks = {
                'ordinary': {**base, 'id': 'ordinary'},
                'finished': {**base, 'id': 'finished',
                    'integration_preparation': {'authorized': True, 'status': 'failed'},
                    'settings_operations': {'done': {'stage': 'continuing'}}},
                'integration': {**base, 'id': 'integration',
                    'integration_preparation': {'authorized': True, 'status': 'waiting'}},
                'settings': {**base, 'id': 'settings', 'events': [],
                    'settings_operations': {'pending': {'stage': 'pending'},
                        'dispatching': {'stage': 'dispatching'}, 'done': {'stage': 'continuing'}}},
            }
            engine = SimpleNamespace(store=store, lock=threading.RLock(), runtimes={})
            with patch.object(integration_preparation, 'resume') as resume, \
                    patch.object(task_settings, 'continue_operation') as continuation:
                integration_preparation.restore(engine)
                task_settings.restore(engine)
            resume.assert_called_once_with(engine, 'integration')
            self.assertEqual([call.args[1:] for call in continuation.call_args_list],
                             [('settings', 'pending'), ('settings', 'dispatching')])
            saved = store.get('settings')
            self.assertEqual(saved['usage'], base['usage'])
            self.assertEqual(saved['checks'], base['checks'])

    def test_gateway_shutdown_does_not_wait_for_catalog_but_keeps_process_policy(self):
        with tempfile.TemporaryDirectory() as root:
            manager = OmniRouteManager(root)
            manager.thread = Mock()
            manager.process = Mock()
            with patch.object(manager, '_terminate') as terminate:
                manager.settings['keep_running'] = True
                manager.shutdown()
                terminate.assert_not_called()
                manager.settings['keep_running'] = False
                manager.shutdown()
                terminate.assert_called_once_with(manager.process)
            manager.thread.join.assert_not_called()
            self.assertTrue(manager.closed.is_set())

    def test_late_catalog_success_or_failure_cannot_reopen_a_closed_gateway(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as root:
                manager = OmniRouteManager(root)
                before = manager.snapshot()
                def probe():
                    manager.shutdown()
                    if fail:
                        raise ProviderError('offline')
                    return []
                with patch.object(manager, '_probe', side_effect=probe), \
                        patch.object(manager, '_port_open') as port, \
                        patch('cheapos.omniroute.subprocess.Popen') as spawn:
                    manager._connect(start=True)
                port.assert_not_called()
                spawn.assert_not_called()
                self.assertEqual(manager.snapshot(), before)

    def task(self, status='draft'):
        run = branch_runs.create_run({'items': [{'id': 'one', 'title': 'One',
            'instructions': 'One', 'dependencies': [], 'acceptance_criteria': ['Works'],
            'required_checks': []}], 'limits': {'cost': 0, 'working_seconds': 600}},
            original_request='One')
        run['status'] = status
        return {'id': 'saved', 'branch_run': run, 'status': branch_runs.task_status(run),
                'created_at': '2026-09-18', 'usage': {}, 'events': []}

    def test_unchanged_saved_runs_are_not_rewritten(self):
        for status in ('draft', 'paused', 'blocked', 'ready_for_merge', 'merged', 'left_on_branch'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as root:
                task = self.task(status)
                path = Path(root) / 'tasks/saved/task.json'
                write_json(path, task)
                original = path.read_bytes()
                with patch('cheapos.storage.write_json', wraps=write_json) as writes:
                    store = Store(root)
                writes.assert_not_called()
                self.assertEqual(store.get('saved'), task)
                self.assertEqual(path.read_bytes(), original)

    def test_interrupted_run_is_saved_once_and_stays_recovered_after_restart(self):
        with tempfile.TemporaryDirectory() as root:
            task = self.task('running')
            task.update(status='running', pending_approval={'id': 'expired'})
            path = Path(root) / 'tasks/saved/task.json'
            write_json(path, task)
            with patch('cheapos.storage.write_json', wraps=write_json) as writes:
                saved = Store(root).get('saved')
            writes.assert_called_once_with(path.resolve(), saved, compact=True)
            self.assertEqual(saved['branch_run']['pause_reason'], 'restart')
            self.assertIsNone(saved['pending_approval'])
            self.assertEqual(json.loads(path.read_text()), saved)
            with patch('cheapos.storage.write_json', wraps=write_json) as writes:
                self.assertEqual(Store(root).get('saved'), saved)
            writes.assert_not_called()

    def test_startup_interruption_and_unsupported_schema_are_persisted(self):
        for startup, schema in (({'status': 'running'}, 1), ({}, 999)):
            with self.subTest(schema=schema), tempfile.TemporaryDirectory() as root:
                task = self.task()
                task['branch_run'].update(startup=startup, schema_version=schema)
                path = Path(root) / 'tasks/saved/task.json'
                write_json(path, task)
                saved = Store(root).get('saved')
                self.assertEqual(json.loads(path.read_text()), saved)
                if schema == 1:
                    self.assertEqual(saved['branch_run']['startup']['status'], 'paused')
                else:
                    self.assertTrue(saved['error'])
                    self.assertEqual(saved['branch_run']['schema_version'], schema)

    def test_restart_acknowledges_before_shutdown_and_deduplicates_clicks(self):
        order, pending = [], []
        server = SimpleNamespace(restart_lock=threading.Lock(), restart_pending=False,
            engine=SimpleNamespace(shutdown=lambda: order.append('shutdown')),
            server_close=lambda: order.append('close'))
        handler = LocalHandler.__new__(LocalHandler)
        handler.server = server
        handler.path = '/api/restart'
        handler.headers = Message()
        handler.headers['Content-Length'] = '2'
        handler.headers['Content-Type'] = 'application/json'
        handler.trusted = Mock(return_value=True)
        handler.reply = lambda value, status=200: order.append(('reply', value, status))
        def deferred(**kwargs):
            return SimpleNamespace(start=lambda: pending.append(kwargs['target']))
        with patch('cheapos.server.threading.Thread', side_effect=deferred), \
                patch('cheapos.server.time.sleep'), patch('cheapos.server.os.execv') as execute:
            for _ in range(2):
                handler.rfile = io.BytesIO(b'{}')
                handler.do_POST()
            self.assertEqual(order, [('reply', {'status': 'restarting'}, 200)] * 2)
            self.assertEqual(len(pending), 1)
            pending[0]()
            self.assertEqual(order[-2:], ['shutdown', 'close'])
            execute.assert_called_once()
        self.assertEqual(handler.trusted.call_count, 2)
        handler.trusted.assert_called_with(mutation=True)

    def test_restart_closes_data_lock_and_survives_shutdown_error(self):
        order = []
        lock_closed = []
        def fail_shutdown():
            order.append('shutdown_fail')
            raise RuntimeError('error in subservice')
        data_lock = SimpleNamespace(close=lambda: lock_closed.append(True))
        server = SimpleNamespace(
            restart_lock=threading.Lock(),
            restart_pending=False,
            engine=SimpleNamespace(shutdown=fail_shutdown),
            server_close=lambda: order.append('close'),
            data_lock=data_lock,
        )
        handler = LocalHandler.__new__(LocalHandler)
        handler.server = server
        handler.path = '/api/restart'
        handler.headers = Message()
        handler.headers['Content-Length'] = '2'
        handler.headers['Content-Type'] = 'application/json'
        handler.trusted = Mock(return_value=True)
        handler.reply = lambda value, status=200: order.append(('reply', value, status))
        pending = []
        def deferred(**kwargs):
            return SimpleNamespace(start=lambda: pending.append(kwargs['target']))
        with patch('cheapos.server.threading.Thread', side_effect=deferred), \
                patch('cheapos.server.time.sleep'), patch('cheapos.server.os.execv') as execute:
            handler.rfile = io.BytesIO(b'{}')
            handler.do_POST()
            self.assertEqual(len(pending), 1)
            pending[0]()
            self.assertIn('shutdown_fail', order)
            self.assertIn('close', order)
            self.assertEqual(lock_closed, [True])
            execute.assert_called_once()
