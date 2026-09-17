"""Small, offline checks for history-independent presentation and polling."""
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos.server import LocalHandler
from cheapos.storage import Store


class TaskPollingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        # Exercise the real store without starting lifetime/club background jobs.
        self.store = Store.__new__(Store)
        self.store.root = Path(temp.name)
        self.store.lock = threading.RLock()
        self.store.tasks = {}
        self.store._view_versions = {}
        self.store.lifetime = Mock()
        self.task = dict(id='one', title='Original', requests=['hi', 'Fix the button'],
                         status='ready', created_at='2026', updated_at='2026',
                         usage={'worker': {'tokens': 10}}, events=[{'id': 'old', 'kind': 'state'}],
                         changes=[{'path': 'button.js'}], messages=['private context'])
        self.store.save(self.task)

    def test_sidebar_and_metadata_never_copy_execution_history(self):
        class UncopyableHistory(list):
            def __deepcopy__(self, memo):
                raise AssertionError('Sidebar traversed execution history')
        self.store.tasks['one']['events'] = UncopyableHistory([{'id': 'old'}])
        self.assertIsNone(self.store.metadata('one')['custom_title'])
        summary = self.store.visible()[0]
        self.assertEqual(summary['title'], 'Fix the button')
        self.assertEqual(summary['saved_change_count'], 1)
        self.assertNotIn('events', summary)
        summary['usage']['worker']['tokens'] = 999
        self.assertEqual(self.store.tasks['one']['usage']['worker']['tokens'], 10)
        with self.assertRaisesRegex(ValueError, 'Task not found'):
            self.store.metadata('../missing')

    def test_unchanged_poll_skips_copy_and_new_stream_revises_without_timestamp_change(self):
        initial, etag = self.store.poll('one')
        self.assertEqual(initial['title'], 'Fix the button')
        initial['events'].clear()
        self.assertEqual(len(self.store.get('one')['events']), 1)
        with patch('cheapos.storage.copy.deepcopy', side_effect=AssertionError('unnecessary copy')):
            self.assertEqual(self.store.poll('one', etag), (None, etag))
        self.task['stream'] = {'content': 'Live output'}
        self.store.publish(self.task)
        updated, new_etag = self.store.poll('one', etag)
        self.assertNotEqual(etag, new_etag)
        self.assertEqual(updated['updated_at'], initial['updated_at'])
        self.assertEqual(updated['stream']['content'], 'Live output')
        self.assertNotIn('stream', json.loads((self.store.root / 'tasks/one/task.json').read_text()))
        self.task['status'] = 'paused'
        self.store.save(self.task)
        self.assertEqual(self.store.poll('one', new_etag)[0]['status'], 'paused')

    def test_metadata_and_new_store_versions_invalidate_without_rewriting_task(self):
        path = self.store.root / 'tasks/one/task.json'
        saved = path.read_bytes()
        _, etag = self.store.poll('one')
        self.store.update_metadata('one', {'custom_title': 'New title', 'pinned': True})
        updated, renamed = self.store.poll('one', etag)
        self.assertNotEqual(etag, renamed)
        self.assertEqual(updated['title'], 'New title')
        self.assertTrue(updated['pinned'])
        self.assertEqual(path.read_bytes(), saved)
        self.store.set_trashed('one', True)
        trashed, latest = self.store.poll('one', renamed)
        self.assertIsNotNone(trashed['trashed_at'])
        self.assertEqual(self.store.visible(), [])
        self.store._view_versions = {}  # A restart must force a fresh view.
        self.assertIsNotNone(self.store.poll('one', latest)[0])

    def test_versions_are_task_scoped_and_deleted_tasks_do_not_return_not_modified(self):
        _, etag = self.store.poll('one')
        self.store.save({**self.task, 'id': 'two'})
        self.assertIsNotNone(self.store.poll('two', etag)[0])
        self.assertEqual(self.store.poll('one', etag), (None, etag))
        self.store.delete_task('one')
        with self.assertRaisesRegex(ValueError, 'Task not found'):
            self.store.poll('one', etag)
        self.store.save(self.task)
        self.assertIsNotNone(self.store.poll('one', etag)[0])

    def test_http_not_modified_skips_projection_and_has_no_body(self):
        _, etag = self.store.poll('one')
        handler = LocalHandler.__new__(LocalHandler)
        handler.path = '/api/tasks/one'
        handler.headers = {'If-None-Match': etag}
        handler.server = SimpleNamespace(engine=SimpleNamespace(store=self.store))
        handler.trusted = lambda: True
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = io.BytesIO()
        with patch('cheapos.server.public_task', side_effect=AssertionError('unnecessary projection')):
            handler.do_GET()
        handler.send_response.assert_called_once_with(304)
        handler.send_header.assert_called_once_with('ETag', etag)
        self.assertEqual(handler.wfile.getvalue(), b'')
        handler.headers = {}
        handler.send_response.reset_mock()
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        response = json.loads(handler.wfile.getvalue())
        self.assertEqual(response['events'], self.task['events'])
        self.assertEqual(response['title'], 'Fix the button')
        self.assertNotIn('messages', response)
