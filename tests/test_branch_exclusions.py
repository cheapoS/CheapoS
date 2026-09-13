"""A test command's private-index edits cannot bypass branch file exclusions."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cheapos.workspace import Workspace, git
from cheapos.engine import Engine
from cheapos.verification import evidence_identity
from cheapos import branch_evidence, branch_commits, branch_workspace


class BranchExclusionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        git(self.root, 'init', '-q', '-b', 'main')
        (self.root / 'readme').write_text('baseline\n')
        git(self.root, 'add', '.')
        git(self.root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'base')
        self.base = git(self.root, 'rev-parse', 'HEAD').strip()
        self.workspace = Workspace(self.root)
        self.context = dict(run_id='run', plan_revision=1, item_id='item', item_revision=1, feature_parent=self.base)

    def tearDown(self):
        self.temp.cleanup()

    def stage(self, name, data=b'forbidden content', mode='100644'):
        oid = self.base if mode == '160000' else branch_workspace.source_git(self.root, 'hash-object', '-w', '--stdin', input=data)
        git(self.root, 'update-index', '--add', '--cacheinfo', mode, oid, name)
        return git(self.root, 'write-tree').strip()

    def test_new_secret_staged_by_check_is_not_exposed_as_candidate_and_is_retained(self):
        tree = self.stage('.env')
        with self.assertRaisesRegex(ValueError, 'allowed workspace'):
            branch_evidence.candidate({'workspace':str(self.root)}, self.context, [], ['Safe files only'])
        self.assertEqual(git(self.root, 'write-tree').strip(), tree)
        self.assertEqual(git(self.root, 'show', ':.env').strip(), 'forbidden content')
        self.assertFalse((self.root / '.env').exists())

    def test_worker_reviewer_and_snapshot_surfaces_reject_staged_secret(self):
        tree = self.stage('.env')
        engine = Engine.__new__(Engine)
        engine.runtimes = {}
        task = {'id':'fixture', 'workspace':str(self.root), 'branch_run':{},
                'prompt':'safe request', 'checkpoints':[], 'check_command':['python3'],
                'active_role':'worker', 'demo':True}
        with self.assertRaises(ValueError):
            engine.initial_messages(task)
        for role in ('worker', 'reviewer'):
            task['active_role'] = role
            with self.assertRaises(ValueError):
                engine.file_tool(task, 'get_diff', {})
        with self.assertRaises(ValueError):
            engine.refresh_changes(task)
        with patch('cheapos.verification.runner_identity', return_value={'executable':'fixture'}):
            self.assertIsNone(evidence_identity(task))
        self.assertEqual(git(self.root, 'write-tree').strip(), tree)

    def test_new_symlink_or_gitlink_staged_without_worktree_file_is_retained(self):
        for mode in ('120000', '160000'):
            with self.subTest(mode=mode):
                tree = self.stage('link', mode=mode)
                with self.assertRaisesRegex(ValueError, 'mode'):
                    self.workspace.patch(validate=True)
                self.assertEqual(git(self.root, 'write-tree').strip(), tree)
                git(self.root, 'update-index', '--force-remove', 'link')

    def test_source_tree_defense_rejects_new_secret_and_nonregular_modes(self):
        for name, mode in (('.env','100644'), ('credentials.json','100644'), ('new-link','120000'), ('new-module','160000')):
            with self.subTest(name=name):
                tree = self.stage(name, mode=mode)
                with self.assertRaisesRegex(ValueError, 'forbidden|unsupported'):
                    branch_commits._preserve_exclusions(str(self.root), self.base, tree, {'skipped':[]})
                self.assertEqual(git(self.root, 'write-tree').strip(), tree)
                git(self.root, 'update-index', '--force-remove', name)

    def test_oversized_staged_blob_is_rejected_without_loading_patch(self):
        tree = self.stage('large', b'x' * 2_000_001)
        with self.assertRaisesRegex(ValueError, '2 MB'):
            self.workspace.patch(validate=True)
        self.assertEqual(git(self.root, 'write-tree').strip(), tree)

    def test_allowed_executable_and_deletion_keep_working(self):
        path = self.root / 'script'
        path.write_text('#!/bin/sh\ntrue\n')
        path.chmod(0o755)
        (self.root / 'readme').unlink()
        patch = self.workspace.patch(validate=True)
        self.assertIn('100755', patch)
        self.assertIn('deleted file mode', patch)
        tree = git(self.root, 'write-tree').strip()
        branch_commits._preserve_exclusions(str(self.root), self.base, tree, {'skipped':[]})


if __name__ == '__main__':
    unittest.main()
