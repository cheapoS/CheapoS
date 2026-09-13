import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cheapos import branch_commits as commits, branch_workspace as bw, branch_evidence as evidence
from cheapos.workspace import Workspace, git


class BranchCommitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()
        git(self.source, 'init', '-q', '-b', 'main')
        git(self.source, 'config', 'user.name', 'Fixture')
        git(self.source, 'config', 'user.email', 'fixture@example.invalid')
        (self.source / 'code').write_text('one\n')
        (self.source / '.env').write_text('excluded\n')
        (self.source / 'link').symlink_to('code')
        git(self.source, 'add', '.')
        git(self.source, 'commit', '-qm', 'Base')
        mapping = bw.create(bw.prepare(self.source, self.root / 'state/tasks/one/workspace', 'refs/heads/main', 'refs/heads/feature/job', 'refs/heads/main', 'run'), lambda _: None)
        self.item = {'id': 'one', 'title': 'First item', 'required_checks': [], 'acceptance_criteria': ['correct content']}
        self.run = {'id': 'run', 'plan_revision': 1, 'plan_digest': 'digest', 'current_item_id': 'one', 'expected_feature_tip': mapping['feature_tip'], 'workspace_mapping': mapping, 'plan': {'items': [copy.deepcopy(self.item)]}}
        self.task = {'workspace': mapping['workspace'], 'workspace_generation': 0}
        self.saved = []
        self.allowed = True

    def authorize(self, task, run):
        if not self.allowed: raise ValueError('Stale authority')

    def receipt(self, text='two\n'):
        (Path(self.task['workspace']) / 'code').write_text(text)
        current = evidence.candidate(self.task, commits.context(self.run, self.item), self.item['required_checks'], self.item['acceptance_criteria'])
        return evidence.ready_receipt(current, [], {'candidate_id': current['id'], 'decision': 'APPROVE', 'feedback': 'Read exact content'}, 'worker', 'reviewer', {'correct content': {'passed': True, 'evidence': 'Read code content'}})

    def prepare(self, text='two\n'):
        return commits.prepare(self.task, self.run, self.item, self.receipt(text), self.authorize)

    def save(self, operation):
        self.saved.append(copy.deepcopy(operation))

    def finish(self, operation, persist=None):
        return commits.finish(self.task, self.run, self.item, operation, persist or self.save, self.authorize)

    def apply_result(self, operation):
        self.run['expected_feature_tip'] = operation['new_tip']
        self.run['workspace_mapping'].update(feature_tip=operation['new_tip'], workspace_head=operation['private_new'])

    def test_two_patches_preserve_source_checkout_and_excluded_entries(self):
        (self.source / 'code').write_text('staged\n')
        git(self.source, 'add', 'code')
        (self.source / 'code').write_text('operator dirty\n')
        (self.source / 'local').write_text('untracked')
        before = (git(self.source, 'rev-parse', 'HEAD'), git(self.source, 'write-tree'), git(self.source, 'status', '--porcelain'))
        first = self.finish(self.prepare())
        self.apply_result(first)
        self.item.update(id='two', title='Second item')
        self.run['current_item_id'] = 'two'
        self.run['plan']['items'].append(copy.deepcopy(self.item))
        second = self.finish(self.prepare('three\n'))
        self.assertEqual(git(self.source, 'rev-parse', second['new_tip'] + '^').strip(), first['new_tip'])
        self.assertEqual(git(self.source, 'show', 'feature/job:code').strip(), 'three')
        self.assertEqual(git(self.source, 'show', 'feature/job:.env').strip(), 'excluded')
        self.assertEqual(git(self.source, 'ls-tree', 'feature/job', 'link').split()[0], '120000')
        self.assertEqual(before, (git(self.source, 'rev-parse', 'HEAD'), git(self.source, 'write-tree'), git(self.source, 'status', '--porcelain')))
        self.assertEqual(Workspace(self.task['workspace']).patch(), '')

    def test_every_durable_failure_boundary_retries_exact_commit(self):
        for stage in ('intent', 'source_committed', 'private_advanced', 'completed'):
            with self.subTest(stage=stage):
                operation = self.prepare('change ' + stage + '\n')
                self.saved = []
                def fail(value):
                    if value['stage'] == stage: raise OSError('save interrupted')
                    self.save(value)
                with self.assertRaises(OSError): self.finish(operation, fail)
                # Recover the last durable journal, or original prepared intent.
                recovered = self.finish(self.saved[-1] if self.saved else operation)
                self.assertEqual(recovered['new_tip'], operation['new_tip'])
                self.assertEqual(git(self.source, 'rev-list', '--count', recovered['old_tip'] + '..' + recovered['new_tip']).strip(), '1')
                self.assertEqual(git(self.task['workspace'], 'rev-parse', 'HEAD').strip(), operation['private_new'])
                self.apply_result(recovered)

    def test_source_success_finishes_without_fresh_authority(self):
        operation = self.prepare()
        def fail(value):
            if value['stage'] == 'source_committed': raise OSError('interrupt')
            self.save(value)
        with self.assertRaises(OSError): self.finish(operation, fail)
        self.allowed = False
        self.finish(self.saved[-1])

    def test_reject_stale_authority_changed_candidate_and_external_ref(self):
        operation = self.prepare()
        self.allowed = False
        with self.assertRaises(ValueError): self.finish(operation)
        self.allowed = True
        (Path(self.task['workspace']) / 'code').write_text('changed after checks')
        with self.assertRaises(ValueError): self.finish(operation)
        (Path(self.task['workspace']) / 'code').write_text('two\n')
        other = bw.source_git(self.source, 'commit-tree', operation['tree'], '-p', operation['old_tip'], input='External\n')
        git(self.source, 'update-ref', 'refs/heads/feature/job', other)
        with self.assertRaises(ValueError): self.finish(operation)

    def test_checked_out_destination_and_excluded_overlap(self):
        operation = self.prepare()
        git(self.source, 'worktree', 'add', str(self.root / 'linked'), 'feature/job')
        with self.assertRaises(ValueError): self.finish(operation)
        git(self.source, 'worktree', 'remove', str(self.root / 'linked'))
        (Path(self.task['workspace']) / 'link').mkdir()
        (Path(self.task['workspace']) / 'link/new').write_text('unsafe overlap')
        with self.assertRaises(ValueError): self.prepare()

    def test_ownership_marker_is_checked_atomically_with_feature_update(self):
        operation = self.prepare()
        original = bw.source_git
        def race(source, *args, **kwargs):
            if args[:1] == ('update-ref',) and '--stdin' in args:
                original(source, 'update-ref', self.run['workspace_mapping']['ownership_ref'], operation['old_tip'])
            return original(source, *args, **kwargs)
        with patch.object(bw, 'source_git', side_effect=race):
            with self.assertRaises(ValueError): self.finish(operation)
        self.assertEqual(git(self.source, 'rev-parse', 'feature/job').strip(), operation['old_tip'])

    def test_no_change_creates_no_commit_and_control_titles_fail(self):
        operation = self.finish(self.prepare('one\n'))
        self.assertEqual(operation['old_tip'], operation['new_tip'])
        self.assertEqual(operation['private_old'], operation['private_new'])
        self.assertEqual(operation['outcome'], 'satisfied_without_change')
        self.item['title'] = 'bad\nmessage'
        with self.assertRaises(ValueError): self.prepare()

    def test_shared_repository_lock_and_changed_inputs_after_intent(self):
        mapping = self.run['workspace_mapping']
        self.assertIs(commits.repository_lock(mapping), commits.repository_lock(copy.deepcopy(mapping)))
        operation = self.prepare()
        def edit(value):
            self.save(value)
            if value['stage'] == 'intent': (Path(self.task['workspace']) / 'code').write_text('raced')
        with self.assertRaises(ValueError): self.finish(operation, edit)
        self.assertEqual(git(self.source, 'rev-parse', 'feature/job').strip(), operation['old_tip'])


if __name__ == '__main__': unittest.main()
