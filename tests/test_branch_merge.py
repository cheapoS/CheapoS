import copy
import shutil
import tempfile
import unittest
from unittest.mock import patch
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

    def test_linked_destination_must_stay_clean_and_match_preview(self):
        (self.source / 'file').write_text('dirty')
        with self.assertRaisesRegex(ValueError, 'uncommitted'):
            self.prepare()
        (self.source / 'file').write_text('old\n')
        git(self.source, 'switch', '-qc', 'operator')
        other = self.root / 'other'
        git(self.source, 'worktree', 'add', str(other), 'main')
        (self.source / 'file').write_text('unrelated operator edits')
        operation = self.prepare()
        self.assertEqual(operation['destination'], str(other))
        (other / 'file').write_text('destination edits')
        with self.assertRaisesRegex(ValueError, 'uncommitted'):
            self.prepare()
        with self.assertRaisesRegex(ValueError, 'uncommitted'):
            merge.integrate(operation, self.save, lambda op: None)
        (other / 'file').write_text('old\n')
        moved = self.root / 'moved'
        git(self.source, 'worktree', 'move', str(other), str(moved))
        with self.assertRaisesRegex(ValueError, 'destination changed'):
            merge.integrate(operation, self.save, lambda op: None)
        git(self.source, 'worktree', 'move', str(moved), str(other))
        # The same path and Git metadata must not authorize a replacement directory.
        other.rename(moved)
        shutil.copytree(moved, other)
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            merge.integrate(operation, self.save, lambda op: None)
        self.assertEqual(git(self.source, 'rev-parse', 'main').strip(), operation['target_old'])
        self.assertEqual((self.source / 'file').read_text(), 'unrelated operator edits')

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
        git(self.source, 'switch', '-qc', 'operator')
        other = self.root / 'other'
        git(self.source, 'worktree', 'add', str(other), 'main')
        operation = self.prepare()
        def fail(op):
            if op['stage'] == 'target_integrated':
                raise OSError('save failed')
            self.save(op)
        with self.assertRaises(OSError):
            merge.integrate(operation, fail, lambda op: None)
        self.assertEqual(self.saved[-1]['stage'], 'intent')
        self.assertEqual(git(other, 'rev-parse', 'HEAD').strip(), self.tip)
        result = merge.integrate(self.saved[-1], self.save, lambda op: None)
        self.assertEqual(result['stage'], 'completed')
        self.assertEqual(git(other, 'rev-list', '--count', 'HEAD').strip(), '2')
        self.assertEqual((other / 'file').read_text(), 'new\n')
        self.assertEqual((self.source / 'file').read_text(), 'old\n')

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

class MergeDestinationTests(unittest.TestCase):
    """Ambiguous registry/foreign repository checks need no Git fixture."""
    def test_duplicate_target_worktrees_are_not_chosen_arbitrarily(self):
        records=b'worktree /first\0branch refs/heads/main\0\0worktree /second\0branch refs/heads/main\0'
        with patch.object(workspace,'source_git',return_value=records):
            with self.assertRaisesRegex(ValueError,'multiple worktrees'):
                merge._destination({'source':'/first'},'refs/heads/main')

    def test_replaced_destination_cannot_redirect_to_another_repository(self):
        with patch.object(workspace,'inspect_source',return_value={'source':'/target','common_identity':['other',1,2]}), \
                patch.object(workspace,'source_git') as git:
            with self.assertRaisesRegex(ValueError,'no longer belongs'):
                merge.destination_identity({'common_identity':['original',1,3]},'/target')
        git.assert_not_called()


if __name__ == '__main__':
    unittest.main()
