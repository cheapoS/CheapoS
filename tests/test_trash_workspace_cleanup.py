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