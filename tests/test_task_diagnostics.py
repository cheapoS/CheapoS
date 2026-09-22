"""Small offline storage/HTTP cases; no models, sockets, Git workflows or waits."""
import copy
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import metrics, task_diagnostics, task_export
from cheapos.server import LocalHandler, public_task
from cheapos.storage import Store, write_json


class TaskDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store.__new__(Store)
        self.store.root = Path(temp.name)
        self.store.lock = threading.RLock()
        self.store.tasks = {}
        self.store._view_versions = {}
        self.store.lifetime = Mock()
        self.task = {'id': 'one', 'title': 'Fix parsing', 'prompt': 'Private task text', 'source': '/private/project',
                     'status': 'paused', 'created_at': '2026', 'updated_at': '2026', 'metrics_schema': 1,
                     'usage': {'planner': {'tokens': 10, 'cost': 0}, 'cost': 0},
                     'events': [{'id': 1, 'kind': 'user', 'title': 'Request', 'detail': 'Private task text'},
                                {'id': 2, 'kind': 'routing', 'title': 'Model check failed', 'detail': {'debug': 'DIAGNOSTIC'}},
                                {'id': 3, 'kind': 'tool', 'title': 'read file', 'detail': {'path': 'app.py'}}],
                     'messages': [{'role': 'user', 'content': 'Private conversation'}],
                     'pending_review': {'candidate': 'unchanged'}, 'route': {'rejected_probes': {'old': {'retry_at': 99}}},
                     'checks': [{'id': 'check', 'passed': True, 'output': 'CHECK OUTPUT'}],
                     'checkpoints': [{'number': 1, 'decision': 'PENDING'}],
                     'request_metrics': [{'id': 'request1', 'role': 'planner', 'purpose': 'probe', 'dispatched': True,
                                          'status': 'responded', 'input_tokens': 8, 'output_tokens': 2,
                                          'usage_reconciled': True, 'accounted_tokens': 10,
                                          'reservation': {'tokens': 10}, 'structural_telemetry': [
                                              {'boundary': 'request_wire', 'wire_bytes': 123, 'version': 1, 'upstream': 'unknown'}]}],
                     'routing_trace_sequence': 1,
                     'routing_traces': [{'id': '1', 'role': 'planner', 'selected_model': 'fixture/model',
                                         'candidates': [{'model': 'fixture/model', 'reason': 'selected'}],
                                         'attempts': [{'request_id': 'request1', 'status': 'responded'}]}]}
        self.path = self.store.root / 'tasks/one/task.json'

    def restart(self):
        with patch('cheapos.club.ClubManager'), patch('cheapos.lifetime_usage.LifetimeUsage'):
            return Store(self.store.root)

    def test_roundtrip_separates_only_debug_fields_and_preserves_accounting_and_resume(self):
        original = copy.deepcopy(self.task)
        expected_metrics = metrics.aggregate(original)
        self.store.save(self.task)
        disk = json.loads(self.path.read_text())
        self.assertNotIn('routing_traces', disk)
        self.assertNotIn('structural_telemetry', disk['request_metrics'][0])
        self.assertEqual(self.task, original)
        self.assertEqual(metrics.aggregate(disk), expected_metrics)
        for key in ('messages', 'checks', 'checkpoints', 'route', 'pending_review', 'usage'):
            self.assertEqual(disk[key], original[key])
        self.assertEqual(disk['request_metrics'][0], {k: v for k, v in original['request_metrics'][0].items() if k != 'structural_telemetry'})
        with patch('cheapos.task_diagnostics.read', side_effect=AssertionError('Startup loaded diagnostics')):
            restarted = self.restart()
        restored = restarted.get('one')
        self.assertEqual(restored['routing_traces'], original['routing_traces'])
        self.assertEqual(restored['request_metrics'], original['request_metrics'])
        self.assertEqual(restored['status'], 'paused')

    def test_unchanged_diagnostics_are_not_rewritten_and_poll_never_reads_them(self):
        self.store.save(self.task)
        with patch('cheapos.storage.write_json', wraps=write_json) as writer:
            self.task['updated_at'] = 'later'
            self.store.save(self.task)
        self.assertEqual([Path(call.args[0]).name for call in writer.call_args_list], ['task.json'])
        with patch('cheapos.task_diagnostics.read', side_effect=AssertionError('Poll loaded diagnostics')):
            task, etag = self.store.poll('one')
            public = public_task(task)
            self.assertEqual(self.store.poll('one', etag), (None, etag))
        self.assertNotIn('routing_traces', public)
        self.assertNotIn('structural_telemetry', json.dumps(public))
        self.assertTrue(public['diagnostics']['available'])

    def test_legacy_record_migrates_on_save_without_modifying_history(self):
        write_json(self.path, self.task)
        restarted = self.restart()
        self.assertNotIn('diagnostics_ref', json.loads(self.path.read_text()))
        task = restarted.get('one')
        restarted.save(task)
        self.assertIn('diagnostics_ref', json.loads(self.path.read_text()))
        self.assertEqual(restarted.get('one')['events'], self.task['events'])
        self.assertEqual(restarted.get('one')['routing_traces'], self.task['routing_traces'])

    def test_failed_task_commit_retains_previous_diagnostics_until_retry(self):
        self.store.save(self.task)
        previous = self.path.read_bytes()
        self.task['routing_traces'][0]['selected_model'] = 'fixture/replacement'
        def fail_task(path, value, **kwargs):
            if Path(path).name == 'task.json':
                raise OSError('simulated interrupted task commit')
            return write_json(path, value, **kwargs)
        with patch('cheapos.storage.write_json', side_effect=fail_task), self.assertRaises(OSError):
            self.store.save(self.task)
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(self.restart().get('one')['routing_traces'][0]['selected_model'], 'fixture/model')
        self.store.save(self.task)
        self.assertEqual(self.restart().get('one')['routing_traces'][0]['selected_model'], 'fixture/replacement')
        self.assertEqual(len(list((self.path.parent / 'diagnostics').glob('*.json'))), 1)

    def test_failed_diagnostics_write_falls_back_without_blocking_saved_work(self):
        def fail_details(path, value, **kwargs):
            if Path(path).parent.name == 'diagnostics':
                raise OSError('diagnostic storage unavailable')
            return write_json(path, value, **kwargs)
        with patch('cheapos.storage.write_json', side_effect=fail_details):
            self.store.save(self.task)
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved['routing_traces'], self.task['routing_traces'])
        self.assertEqual(self.restart().get('one')['request_metrics'], self.task['request_metrics'])

    def test_missing_or_corrupt_diagnostics_never_remove_the_task_or_its_ledger(self):
        self.store.save(self.task)
        reference = json.loads(self.path.read_text())['diagnostics_ref']
        detail_path = task_diagnostics.path_for(self.path.parent, reference)
        for content in ('{broken', None):
            with self.subTest(content=content):
                if content is None:
                    detail_path.unlink()
                else:
                    detail_path.write_text(content)
                restarted = self.restart()
                task = restarted.get('one')
                self.assertEqual(task['status'], 'paused')
                self.assertEqual(task['request_metrics'][0]['id'], 'request1')
                self.assertEqual(task['request_metrics'][0]['accounted_tokens'], 10)
                self.assertEqual(task['pending_review'], self.task['pending_review'])
                self.assertIn('unavailable', restarted.diagnostics('one')['notice'])

    def test_diagnostic_pages_and_export_are_separate_from_task_summary(self):
        self.task['routing_traces'] = [dict(self.task['routing_traces'][0], id=str(i)) for i in range(12)]
        self.store.save(self.task)
        page = self.store.diagnostics('one')
        self.assertEqual([r['id'] for r in page['routing_traces']], [str(i) for i in range(4, 12)])
        self.assertEqual(page['next_offset'], 8)
        older = self.store.diagnostics('one', offset=8)
        self.assertEqual([r['id'] for r in older['routing_traces']], ['0', '1', '2', '3'])
        self.assertIsNone(older['next_offset'])
        exported = self.store.diagnostics('one', export=True)
        self.assertEqual(len(exported['routing_traces']), 12)
        self.assertIn('request1', exported['request_measurements'])
        self.assertNotIn('Private conversation', json.dumps(exported))
        summary = task_export.summary(public_task(self.store.get('one')))
        self.assertEqual([s['kind'] for s in summary['steps']], ['user', 'tool'])
        self.assertEqual(summary['usage'], self.task['usage'])
        self.assertEqual(summary['checks'][0]['passed'], True)
        self.assertEqual(summary['checkpoints'][0]['decision'], 'PENDING')
        for omitted in ('DIAGNOSTIC', 'routing_traces', 'structural_telemetry', 'CHECK OUTPUT', '/private/project'):
            self.assertNotIn(omitted, json.dumps(summary))

    def test_untrusted_references_cannot_read_outside_the_task(self):
        for reference in ({'version': 1, 'digest': '../secret'}, {'version': 2, 'digest': 'a' * 64}):
            self.task['diagnostics_ref'] = reference
            self.assertIsNotNone(task_diagnostics.read(self.path.parent, self.task)[1])
        directory = self.path.parent / 'diagnostics'
        directory.parent.mkdir(parents=True)
        directory.symlink_to(self.store.root, target_is_directory=True)
        self.task['diagnostics_ref'] = {'version': 1, 'digest': 'a' * 64}
        self.assertIsNotNone(task_diagnostics.read(self.path.parent, self.task)[1])

    def test_local_http_routes_load_diagnostics_only_when_requested(self):
        self.store.save(self.task)
        handler = LocalHandler.__new__(LocalHandler)
        handler.headers = {}
        handler.server = SimpleNamespace(engine=SimpleNamespace(store=self.store))
        handler.trusted = lambda: True
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        for path, field in (('/api/tasks/one', 'diagnostics'), ('/api/tasks/one/export', 'steps'),
                            ('/api/tasks/one/diagnostics', 'routing_traces'),
                            ('/api/tasks/one/diagnostics?export=1', 'request_measurements')):
            handler.path = path
            handler.wfile = io.BytesIO()
            handler.do_GET()
            body = json.loads(handler.wfile.getvalue())
            self.assertIn(field, body)
        for path in ('/api/tasks/missing/diagnostics', '/api/tasks/one/diagnostics?offset=-1'):
            handler.path = path
            handler.wfile = io.BytesIO()
            handler.do_GET()
            self.assertIn('error', json.loads(handler.wfile.getvalue()))
