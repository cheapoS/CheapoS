import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from cheapos.engine import Engine, Runtime
from cheapos.storage import Store


class TaskMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.task = dict(id='known', title='Original', source='/fixture', status='ready',
                         created_at='2026', updated_at='2026', demo=False, usage={}, events=[])
        self.store.save(self.task)

    def tearDown(self):
        self.temp.cleanup()

    def test_metadata_survives_worker_saves_and_restart_without_rewriting_history(self):
        barrier = threading.Barrier(2)
        def worker():
            barrier.wait()
            for i in range(20):
                self.task['events'].append(i)
                self.store.publish(self.task)
                self.store.save(self.task)
        thread = threading.Thread(target=worker)
        thread.start()
        barrier.wait()
        self.store.update_metadata('known', {'custom_title': '  Useful name  ', 'pinned': True})
        thread.join()
        store = Store(self.temp.name)
        self.assertEqual(store.visible()[0]['title'], 'Useful name')
        self.assertTrue(store.visible()[0]['pinned'])
        self.assertEqual(store.get('known')['events'], list(range(20)))
        self.assertEqual(store.get('known')['title'], 'Original')

    def test_defaults_archive_idempotence_and_malformed_record(self):
        self.assertEqual(self.store.visible()[0]['title'], 'Original')
        first = self.store.update_metadata('known', {'archived': True})
        self.assertEqual(first, self.store.update_metadata('known', {'archived': True}))
        self.assertEqual(self.store.visible(), [])
        self.assertEqual(len(self.store.visible('archived')), 1)
        self.assertEqual(len(self.store.list()), 1)
        self.store.update_metadata('known', {'archived': False})
        self.assertEqual(len(self.store.visible()), 1)
        (Path(self.temp.name) / 'tasks/known/metadata.json').write_text('{bad')
        self.assertEqual(self.store.visible()[0]['title'], 'Original')

    def test_invalid_updates_are_atomic(self):
        for values in [{'custom_title': ''}, {'custom_title': 'a'*121}, {'custom_title': 'x\ny'},
                       {'custom_title': 2}, {'pinned': 1}, {'archived': 'yes'}, {'trashed_at': 'x'},
                       {'custom_title': 'valid', 'pinned': 'no'}]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.store.update_metadata('known', values)
        self.assertEqual(self.store.visible()[0]['title'], 'Original')
        with self.assertRaises(ValueError):
            self.store.update_metadata('../missing', {'pinned': True})
        self.store.update_metadata('known', {'custom_title': '🌱'*120})
        self.store.update_metadata('known', {'custom_title': None})
        self.assertEqual(self.store.visible()[0]['title'], 'Original')

    def test_controller_archive_guards_and_restore_does_not_dispatch(self):
        engine = Engine(Path(self.temp.name) / 'engine')
        self.addCleanup(engine.shutdown)
        task = engine.create_demo()
        runtime = Runtime(task)
        runtime.thread = Mock()
        runtime.thread.is_alive.return_value = True
        engine.runtimes[task['id']] = runtime
        engine.update_task_metadata(task['id'], {'custom_title': 'Running name', 'pinned': True})
        with self.assertRaisesRegex(ValueError, 'Pause'):
            engine.update_task_metadata(task['id'], {'archived': True})
        runtime.thread.is_alive.return_value = False
        task['commit_pending'] = {'saved': True}
        engine.store.save(task)
        with self.assertRaisesRegex(ValueError, 'commit'):
            engine.update_task_metadata(task['id'], {'archived': True})
        task['commit_pending'] = None
        engine.store.save(task)
        engine.update_task_metadata(task['id'], {'archived': True})
        with self.assertRaisesRegex(ValueError, 'Restore'):
            engine.start(task['id'])
        engine.update_task_metadata(task['id'], {'archived': False})
        self.assertEqual(engine.store.get(task['id'])['status'], 'ready')
        runtime.thread.start.assert_not_called()
