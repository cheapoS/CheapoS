import shutil
import tempfile
import unittest
import json
from pathlib import Path
from cheapos.storage import Store
from cheapos.workspace import git

class TrashWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()
        git(self.source, 'init', '-q', '-b', 'main')
        git(self.source, 'config', 'user.name', 'Test')
        git(self.source, 'config', 'user.email', 'test@example.invalid')
        (self.source / 'file').write_text('content')
        git(self.source, 'add', '.')
        git(self.source, 'commit', '-qm', 'base')
        
        self.storage_root = self.root / 'storage'
        self.storage_root.mkdir()
        self.storage = Store(self.storage_root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_trash_removes_worktree(self):
        # Create a task with a workspace that is a worktree, using the
        # real branch_run.workspace_mapping structure the app persists.
        task_id = 'task-one'
        task_path = self.storage_root / 'tasks' / task_id
        task_path.mkdir(parents=True)
        workspace = task_path / 'workspace'

        git(self.source, 'worktree', 'add', '-b', 'feature/test', str(workspace), 'main')

        task = {
            'id': task_id,
            'status': 'paused',
            'created_at': '2026-09-20T03:00:00Z',
            'branch_run': {
                'workspace_mapping': {
                    'source': str(self.source),
                    'workspace': str(workspace),
                }
            }
        }
        (task_path / 'task.json').write_text(json.dumps(task))
        self.storage.tasks[task_id] = task

        self.storage.set_trashed(task_id, True)
        self.storage.empty_trash()

        # Verify worktree is removed from source
        worktrees = git(self.source, 'worktree', 'list')
        self.assertNotIn(str(workspace), worktrees)

    def test_empty_trash_preserves_unrelated_temporary_worktrees(self):
        temp_wt = self.root / 'cheapos-temp-wt'
        git(self.source, 'worktree', 'add', '-b', 'feature/temp', str(temp_wt), 'main')
        (temp_wt / 'file').write_text('unpublished edits')
        self.storage.empty_trash()
        self.assertIn(str(temp_wt), git(self.source, 'worktree', 'list'))
        self.assertEqual((temp_wt / 'file').read_text(), 'unpublished edits')

    def test_merged_copy_cleanup_preserves_history_and_protects_later_edits(self):
        import copy
        import threading
        from types import SimpleNamespace
        from unittest.mock import patch
        from cheapos.admission import Admission
        from cheapos.storage_maintenance import Maintenance, register, owned_workspace
        from cheapos.workspace import Workspace
        from cheapos.pr_followup import later_patch
        task_id = 'merged-task'
        directory = self.storage_root / 'tasks' / task_id
        workspace, snapshot = Workspace.snapshot(self.source, directory / 'workspace')
        tip = git(self.source, 'rev-parse', 'HEAD').strip()
        task = {'id': task_id, 'title': 'Merged improvement', 'workspace': str(workspace.root),
                'source': str(self.source), 'snapshot': snapshot, 'status': 'completed',
                'created_at': '2026-09-20T03:00:00Z', 'messages': [{'role': 'user', 'content': 'Keep history'}],
                'checks': [{'passed': True}], 'patch': 'saved diff', 'checkpoints': [{'decision':'APPROVE'}],
                'pull_request': {'id': 'publication', 'source': str(self.source), 'head': tip,
                                 'merged_head': tip, 'ci': {'state': 'merged', 'head': tip}}}
        register(self.storage, task)
        self.storage.save(task)
        engine = SimpleNamespace(store=self.storage, lock=threading.RLock(), runtimes={},
                                 command_permissions={}, previews=SimpleNamespace(runs={}))
        engine.admission = Admission(engine)
        maintenance = Maintenance(engine)
        (directory / 'check-output').mkdir()
        (directory / 'check-output' / 'saved.log').write_text('verification passed')
        before = copy.deepcopy(self.storage.get(task_id))
        self.assertEqual(maintenance.view()['eligible_count'], 1)
        # Open PR, active execution and active preview must all retain the copy.
        task['pull_request']['ci']['state'] = 'success'; self.storage.save(task)
        self.assertFalse(maintenance.reclaim(task_id))
        task['pull_request']['ci']['state'] = 'merged'; self.storage.save(task)
        engine.admission.pending[task_id] = 'interactive'
        self.assertFalse(maintenance.reclaim(task_id)); engine.admission.pending.clear()
        engine.previews.runs[task_id] = {'thread': SimpleNamespace(is_alive=lambda: True)}
        self.assertFalse(maintenance.reclaim(task_id)); engine.previews.runs.clear()
        file = workspace.root / 'file'
        for later in ('new.txt', '.ignored-cache'):
            (workspace.root / later).write_text('keep this')
            with self.assertRaisesRegex(ValueError, 'Unpublished'):
                maintenance.reclaim(task_id)
            (workspace.root / later).unlink()
        file.write_text('later staged change'); git(workspace.root, 'add', 'file')
        file.write_text('content')
        with self.assertRaisesRegex(ValueError, 'staged'):
            maintenance.reclaim(task_id)
        git(workspace.root, 'reset', '--quiet', 'HEAD', '--', 'file')
        git(workspace.root, 'rm', '--cached', '--quiet', 'file')
        with self.assertRaisesRegex(ValueError, 'staged'):
            maintenance.reclaim(task_id)
        git(workspace.root, 'reset', '--quiet', 'HEAD', '--', 'file')
        git(workspace.root, 'branch', 'unpublished')
        with self.assertRaisesRegex(ValueError, 'Additional Git'):
            maintenance.reclaim(task_id)
        git(workspace.root, 'branch', '-D', 'unpublished')
        # A writer racing proof capture must not turn later edits into consent.
        from cheapos.storage_maintenance import cleanup_inventory
        def capture_then_edit(path):
            result = cleanup_inventory(path)
            (path / 'file').write_text('racing edit')
            return result
        with patch('cheapos.storage_maintenance.cleanup_inventory', side_effect=capture_then_edit):
            with self.assertRaisesRegex(ValueError, 'Unpublished'):
                maintenance.reclaim(task_id)
        self.assertEqual(file.read_text(), 'racing edit')
        file.write_text('content')
        # Simulate shutdown halfway through removal. A new Maintenance resumes
        # from a local proof; no agent/Git workflow or real-time waits involved.
        def interrupted(path):
            (path / 'file').unlink()
            raise OSError('interrupted cleanup')
        with patch('cheapos.storage_maintenance.shutil.rmtree', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                maintenance.reclaim(task_id)
        quarantine = directory / 'workspace-reclaim'
        (quarantine / 'new.txt').write_text('external writer')
        restarted = Maintenance(engine)
        with self.assertRaisesRegex(ValueError, 'Files changed'):
            restarted.reclaim(task_id)
        self.assertTrue((quarantine / 'new.txt').exists())
        (quarantine / 'new.txt').unlink()
        self.assertTrue(restarted.reclaim(task_id))
        saved = self.storage.get(task_id)
        self.assertFalse(workspace.root.exists()); self.assertFalse(quarantine.exists())
        for key in ('messages','checks','patch','checkpoints','pull_request'):
            self.assertEqual(saved[key], before[key])
        self.assertEqual((directory / 'check-output' / 'saved.log').read_text(), 'verification passed')
        self.assertEqual(later_patch(saved), '')
        self.assertEqual(restarted.view()['tasks'][0]['state'], 'reclaimed')
        self.assertFalse(restarted.reclaim(task_id))
        # Task deletion must never follow a forged path or a replaced directory.
        task['workspace'] = str(self.source)
        with self.assertRaisesRegex(ValueError, 'outside'):
            owned_workspace(self.storage, task)
        task['workspace'] = str(workspace.root)
        workspace.root.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'link'):
            owned_workspace(self.storage, task)
        self.assertTrue((self.source / 'file').exists())
