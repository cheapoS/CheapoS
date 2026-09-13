import copy
import tempfile
import unittest
from pathlib import Path
from cheapos import branch_workspace as workspace, branch_merge as merge
from cheapos.workspace import git


class BranchMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()
        git(self.source, 'init', '-q', '-b', 'main')
        git(self.source, 'config', 'user.name', 'Test')
        git(self.source, 'config', 'user.email', 'test@example.invalid')
        (self.source / 'file').write_text('old\n')
        git(self.source, 'add', '.')
        git(self.source, 'commit', '-qm', 'initial')
        plan = workspace.prepare(self.source, self.root / 'state/tasks/one/workspace',
                                 'refs/heads/main', 'refs/heads/feature/test', 'refs/heads/main', 'run')
        self.mapping = workspace.create(plan, lambda p: None)
        private = self.mapping['workspace']
        (Path(private) / 'file').write_text('new\n')
        git(private, 'add', '.')
        # Build a source commit with exact bytes without touching source files/index.
        blob = workspace.source_git(self.source, 'hash-object', '-w', '--stdin', input=b'new\n')
        source_tree = workspace.source_git(self.source, 'mktree', input='100644 blob ' + blob + '\tfile\n')
        self.tip = workspace.source_git(self.source, 'commit-tree', source_tree, '-p', self.mapping['base_sha'], input='feature\n')
        git(self.source, 'update-ref', self.mapping['feature_ref'], self.tip, self.mapping['base_sha'])
        self.mapping['feature_tip'] = self.tip
        self.saved = []

    def tearDown(self):
        self.temp.cleanup()

    def save(self, operation):
        self.saved.append(copy.deepcopy(operation))

    def prepare(self):
        return merge.prepare(self.mapping, self.tip, 'refs/heads/main')

    def test_checked_out_target_updates_consistently_without_extra_commit(self):
        old = git(self.source, 'rev-parse', 'HEAD')
        operation = self.prepare()
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD'), old)
        self.assertEqual((self.source / 'file').read_text(), 'old\n')
        calls = []
        result = merge.integrate(operation, self.save, lambda op: calls.append(op['id']))
        self.assertEqual(result['stage'], 'completed')
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD').strip(), self.tip)
        self.assertEqual((self.source / 'file').read_text(), 'new\n')
        self.assertEqual(git(self.source, 'status', '--porcelain'), '')
        self.assertEqual(git(self.source, 'rev-list', '--count', 'HEAD').strip(), '2')
        self.assertEqual(merge.integrate(result, self.save, lambda op: None)['id'], operation['id'])
        self.assertEqual(len(calls), 2)

    def test_unchecked_out_target_preserves_dirty_selected_checkout(self):
        git(self.source, 'switch', '-qc', 'operator')
        (self.source / 'file').write_text('operator changes')
        index = git(self.source, 'write-tree')
        merge.integrate(self.prepare(), self.save, lambda op: None)
        self.assertEqual(git(self.source, 'symbolic-ref', 'HEAD').strip(), 'refs/heads/operator')
        self.assertEqual(git(self.source, 'write-tree'), index)
        self.assertEqual((self.source / 'file').read_text(), 'operator changes')
        self.assertEqual(git(self.source, 'rev-parse', 'main').strip(), self.tip)

    def test_dirty_and_other_worktree_target_refused(self):
        (self.source / 'file').write_text('dirty')
        with self.assertRaisesRegex(ValueError, 'uncommitted'):
            self.prepare()
        (self.source / 'file').write_text('old\n')
        git(self.source, 'switch', '-qc', 'operator')
        git(self.source, 'worktree', 'add', str(self.root / 'other'), 'main')
        with self.assertRaisesRegex(ValueError, 'another worktree'):
            self.prepare()

    def test_changed_feature_target_and_approval_refused(self):
        operation = self.prepare()
        def reject(op):
            raise ValueError('Readiness changed')
        with self.assertRaisesRegex(ValueError, 'Readiness'):
            merge.integrate(operation, self.save, reject)
        git(self.source, 'commit', '--allow-empty', '-qm', 'external')
        with self.assertRaisesRegex(ValueError, 'Target changed'):
            merge.integrate(operation, self.save, lambda op: None)
        with self.assertRaisesRegex(ValueError, 'diverged'):
            self.prepare()
        git(self.source, 'update-ref', self.mapping['feature_ref'], self.mapping['base_sha'], self.tip)
        with self.assertRaisesRegex(ValueError, 'Feature branch changed'):
            merge.integrate(operation, self.save, lambda op: None)

    def test_save_failure_after_git_success_recovers_one_fast_forward(self):
        operation = self.prepare()
        def fail(op):
            if op['stage'] == 'target_integrated':
                raise OSError('save failed')
            self.save(op)
        with self.assertRaises(OSError):
            merge.integrate(operation, fail, lambda op: None)
        self.assertEqual(self.saved[-1]['stage'], 'intent')
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD').strip(), self.tip)
        result = merge.integrate(self.saved[-1], self.save, lambda op: None)
        self.assertEqual(result['stage'], 'completed')
        self.assertEqual(git(self.source, 'rev-list', '--count', 'HEAD').strip(), '2')

    def test_failed_intent_save_and_tampered_manifest_do_not_move_target(self):
        operation = self.prepare()
        def fail(op):
            raise OSError('intent save failed')
        with self.assertRaises(OSError):
            merge.integrate(operation, fail, lambda op: None)
        self.assertEqual(git(self.source, 'rev-parse', 'main').strip(), operation['target_old'])
        operation['manifest_digest'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'manifest'):
            merge.integrate(operation, self.save, lambda op: None)
        self.assertEqual((self.source / 'file').read_text(), 'old\n')

    def test_recovery_does_not_overwrite_operator_edits(self):
        operation = self.prepare()
        def fail(op):
            if op['stage'] == 'target_integrated':
                raise OSError('save failed')
            self.save(op)
        with self.assertRaises(OSError):
            merge.integrate(operation, fail, lambda op: None)
        (self.source / 'file').write_text('later operator edit')
        with self.assertRaisesRegex(ValueError, 'uncommitted'):
            merge.integrate(self.saved[-1], self.save, lambda op: None)
        self.assertEqual((self.source / 'file').read_text(), 'later operator edit')

if __name__ == '__main__':
    unittest.main()
