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
from cheapos.server import LocalHandler
from cheapos.storage import Store, write_json


class RestartTests(unittest.TestCase):
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
