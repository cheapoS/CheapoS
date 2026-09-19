"""Small deterministic cache/permission cases; no Node installation or model calls."""
import tempfile
import json
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos.carto import Carto
from cheapos.storage import write_json


class ImmediateThread:
    def __init__(self, target, args, **kwargs):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class CartoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / 'repo'
        self.source.mkdir()
        self.carto = Carto(self.root / 'profile')
        write_json(self.carto.settings_file, {str(self.source): True})
        self.calls = []
        self.addCleanup(patch.stopall)
        patch('cheapos.carto.threading.Thread', ImmediateThread).start()
        patch.object(self.carto, 'available', return_value=True).start()
        patch('cheapos.carto.Workspace.list_files', return_value=['app.py']).start()
        patch.object(self.carto, 'call', side_effect=self.call).start()
        (self.source / 'app.py').write_text('def hello(): return 1\n')

    def call(self, request):
        self.calls.append(request)
        return {'indexed': len(request.get('files', [])), 'errors': 0} if request['action'] == 'index' else {'found': 'app.py'}

    def context(self, **kwargs):
        return self.carto.context(self.source, self.source, **kwargs)

    def test_first_index_then_reuse_and_refresh_changed_or_deleted_files(self):
        self.assertEqual(self.context()['status'], 'indexing')
        first = self.context()
        self.assertEqual(first['status'], 'ready')
        self.assertEqual(first['indexed_files'], 1)
        self.assertEqual([c['action'] for c in self.calls], ['index', 'query'])
        (self.source / 'app.py').write_text('def hello(): return 2\n')
        self.assertEqual(self.context()['status'], 'indexing')
        self.assertNotEqual(self.context()['identity'], first['identity'])
        mirror = Path(self.calls[0]['root'])
        self.assertIn('return 2', (mirror / 'app.py').read_text())
        (self.source / 'app.py').unlink()
        self.assertEqual(self.context()['status'], 'indexing')
        self.assertFalse((mirror / 'app.py').exists())
        self.assertEqual(self.context()['indexed_files'], 0)

    def test_rebuild_discards_database(self):
        self.context()
        database = Path(self.calls[0]['root']) / '.carto' / 'carto.db'
        database.parent.mkdir()
        database.write_text('broken')
        self.context(rebuild=True)
        self.assertFalse(database.exists())

    def test_worktrees_have_separate_caches(self):
        other = self.root / 'task-copy'
        other.mkdir()
        (other / 'app.py').write_text('other task')
        self.context()
        self.carto.context(self.source, other)
        self.assertNotEqual(self.calls[0]['root'], self.calls[1]['root'])

    def test_disabled_missing_runtime_and_failures_do_not_block(self):
        write_json(self.carto.settings_file, {str(self.source):False})
        self.assertEqual(self.context()['status'], 'disabled')
        write_json(self.carto.settings_file, {str(self.source): True})
        with patch.object(self.carto, 'available', return_value=False):
            self.assertEqual(self.context()['status'], 'unavailable')
        with patch.object(self.carto, 'call', side_effect=ValueError('failed index')):
            self.context()
            self.assertEqual(self.context()['status'], 'unavailable')
        self.assertEqual(self.calls, [])

    def test_project_mapping_defaults_on_and_preserves_explicit_opt_out(self):
        self.carto.settings_file.unlink()
        self.assertTrue(self.carto.status(self.source)['enabled'])
        self.assertEqual(self.carto.prepare(self.source)['status'], 'indexing')
        self.assertEqual([c['action'] for c in self.calls], ['index'])
        self.assertEqual(self.context()['status'], 'ready')
        self.calls.clear()
        write_json(self.carto.settings_file, {str(self.source): False})
        self.assertFalse(self.carto.status(self.source)['enabled'])
        self.assertEqual(self.carto.prepare(self.source)['status'], 'disabled')
        self.assertEqual(self.context()['status'], 'disabled')
        self.assertEqual(self.calls, [])

    def test_add_project_returns_before_capture_and_duplicate_requests_share_work(self):
        pending = []
        class DeferredThread:
            def __init__(self, target, args, **kwargs):
                self.run = lambda: target(*args)
            def start(self):
                pending.append(self.run)
        with patch('cheapos.carto.threading.Thread', DeferredThread), \
                patch.object(self.carto, 'capture', wraps=self.carto.capture) as capture:
            self.assertEqual(self.carto.prepare(self.source)['status'], 'indexing')
            self.carto.prepare(self.source)
            self.assertEqual(self.context()['status'], 'indexing')
            self.assertEqual(len(pending), 1)
            capture.assert_not_called()
            self.assertEqual(self.calls, [])
            pending.pop()()
            capture.assert_called_once()
        self.assertFalse(self.carto.building)
        self.assertEqual(self.context()['status'], 'ready')

    def test_reopening_reuses_index_and_refreshes_changes_without_a_timer(self):
        self.carto.prepare(self.source)
        self.carto.prepare(self.source)
        self.assertEqual([c['action'] for c in self.calls], ['index'])
        (self.source / 'app.py').write_text('def different(): return 42\n')
        self.carto.prepare(self.source)
        self.assertEqual([c['action'] for c in self.calls], ['index', 'index'])
        (self.source / 'app.py').unlink()
        self.carto.prepare(self.source)
        self.assertEqual(self.context()['indexed_files'], 0)

    def test_warmup_failures_and_unavailable_runtime_leave_file_discovery_usable(self):
        with patch.object(self.carto, 'available', return_value=False), \
                patch.object(self.carto, 'capture') as capture:
            self.assertEqual(self.carto.prepare(self.source)['status'], 'unavailable')
            capture.assert_not_called()
        with patch.object(self.carto, 'capture', side_effect=ValueError('fixture unavailable')):
            self.carto.prepare(self.source)
        self.assertFalse(self.carto.building)
        self.assertEqual(self.carto.prepare(self.source)['status'], 'unavailable')
        self.assertEqual(self.context()['status'], 'unavailable')
        self.assertEqual((self.source / 'app.py').read_text(), 'def hello(): return 1\n')

    def test_thread_start_failure_does_not_break_project_registration(self):
        thread = Mock()
        thread.start.side_effect = RuntimeError('cannot start thread')
        with patch('cheapos.carto.threading.Thread', return_value=thread):
            self.assertEqual(self.carto.prepare(self.source)['status'], 'unavailable')
        self.assertFalse(self.carto.building)

    def test_disabled_queued_project_is_not_indexed(self):
        pending = []
        class DeferredThread:
            def __init__(self, target, args, **kwargs):
                self.run = lambda: target(*args)
            def start(self):
                pending.append(self.run)
        with patch('cheapos.carto.threading.Thread', DeferredThread):
            self.carto.prepare(self.source)
            write_json(self.carto.settings_file, {str(self.source): False})
            pending.pop()()
        self.assertFalse(self.carto.building)
        self.assertEqual(self.calls, [])

    def test_index_operations_share_serial_gate(self):
        # No sleeping threads: assert both warm-up and task refresh execute
        # their index mutation under the same non-reentrant serialization gate.
        original = self.carto.call
        def guarded(request):
            if request['action'] == 'index':
                self.assertFalse(self.carto.index_lock.acquire(blocking=False))
            return original(request)
        with patch.object(self.carto, 'call', side_effect=guarded):
            self.carto.prepare(self.source)
            (self.source / 'app.py').write_text('def edited(): pass\n')
            self.context()
        self.assertEqual([c['action'] for c in self.calls], ['index', 'index'])

    def test_registered_project_schedules_mapping_after_saving_without_extra_authority(self):
        from cheapos.engine import Engine
        from cheapos.workspace import Workspace
        engine = object.__new__(Engine)
        profile = self.root / 'registration'
        profile.mkdir()
        engine.store = SimpleNamespace(root=profile)
        engine.lock = threading.RLock()
        engine.projects = lambda **kwargs: []
        engine.hidden_project_paths = lambda: {str(self.source)}
        def prepare(source):
            self.assertEqual(json.loads((profile / 'projects.json').read_text()), [str(self.source)])
            self.assertEqual(json.loads((profile / 'hidden-projects.json').read_text()), [])
            return {'status': 'indexing'}
        engine.carto = SimpleNamespace(prepare=Mock(side_effect=prepare))
        with patch.object(Workspace, 'project_root', return_value=self.source):
            result = engine.open_project({'repository': str(self.source)})
        engine.carto.prepare.assert_called_once_with(str(self.source))
        self.assertEqual(result, {'path': str(self.source), 'name': 'repo'})
        self.assertEqual({p.name for p in profile.iterdir()}, {'projects.json', 'hidden-projects.json'})

    def test_building_index_never_serves_stale_context(self):
        self.context()
        import hashlib
        key = hashlib.sha256(str(self.source).encode()).hexdigest()
        self.carto.building.add(key)
        self.assertEqual(self.context()['status'], 'indexing')
        self.assertEqual(len(self.calls), 1)

    def test_invalid_paths_and_symlinks_cannot_be_read(self):
        with self.assertRaises(ValueError): self.context(path='../secret.py')
        outside = self.root / 'secret.py'
        outside.write_text('secret')
        (self.source / 'app.py').unlink()
        (self.source / 'app.py').symlink_to(outside)
        self.assertEqual(self.carto.capture(self.source)[0], {})

    def test_settings_corruption_and_invalid_queries(self):
        self.carto.settings_file.write_text('[]')
        self.assertEqual(self.context()['status'], 'disabled')
        write_json(self.carto.settings_file, {str(self.source): True})
        with self.assertRaises(ValueError): self.context(query=['bad'])

    def test_worker_tool_is_read_only_and_accounted(self):
        from cheapos.engine import Engine, READ_TOOLS
        engine = object.__new__(Engine)
        engine.carto = self.carto
        engine.runtimes = {}
        engine.event = lambda *args: None
        task = {'id': 'fixture', 'source': str(self.source), 'workspace': str(self.source), 'tool_actions': 0}
        self.assertIn('get_project_context', [t['function']['name'] for t in READ_TOOLS])
        self.assertEqual(engine.file_tool(task, 'get_project_context', {})['status'], 'indexing')
        self.assertEqual(task['tool_actions'], 1)
