import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cheapos import commits, reconciliation
from cheapos.engine import Engine, Runtime, needs_patch_review
from cheapos.workspace import Workspace, git


class CommitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = Engine(Path(self.temp.name) / 'state')
        self.task = self.engine.create_demo()
        self.source = Path(self.task['source'])
        git(self.source, 'config', 'user.name', 'Test Operator')
        git(self.source, 'config', 'user.email', 'operator@example.invalid')
        self.workspace = Workspace(self.task['workspace'])
        self.workspace.write_file('approved.txt', 'approved content\n')
        self.review()
        self.head = git(self.source, 'rev-parse', 'HEAD').strip()

    def tearDown(self):
        self.engine.shutdown()
        self.temp.cleanup()

    def review(self, status='approved'):
        self.engine.refresh_changes(self.task)
        self.task['status'] = status
        generation = self.task.get('workspace_generation', 0)
        self.task['checks'].append({'passed': True, 'digest': hashlib.sha256(self.task['patch'].encode()).hexdigest(), 'generation': generation})
        self.task['checkpoints'].append({'decision': 'APPROVE', 'diff': self.task['patch'], 'worker_summary': 'Add approved example', 'generation': generation})
        self.engine.store.save(self.task)

    def preview(self):
        return self.engine.prepare_commit(self.task['id'])

    def approve(self, preview, **extra):
        return self.engine.apply_commit(self.task['id'], {'approved': True, 'approval_id': preview['approval_id'], 'message': preview['message'], **extra})

    def test_preview_is_read_only_and_explicit_commit_uses_operator_identity(self):
        before = git(self.source, 'status', '--porcelain')
        p = self.preview()
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD').strip(), self.head)
        self.assertEqual(git(self.source, 'status', '--porcelain'), before)
        self.assertFalse((self.source / 'approved.txt').exists())
        with self.assertRaisesRegex(ValueError, 'Approve'):
            self.approve(p, approved=False)
        result = self.approve(p, message='Add an approved example\n\nChosen by the operator.')
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD').strip(), result['commit'])
        self.assertEqual(git(self.source, 'log', '-1', '--format=%an').strip(), 'Test Operator')
        self.assertEqual(git(self.source, 'show', '--format=', '--name-only', 'HEAD').strip(), 'approved.txt')
        self.assertEqual(git(self.source, 'status', '--porcelain'), '')
        self.assertEqual((self.source / 'approved.txt').read_text(), 'approved content\n')
        self.assertEqual(self.workspace.patch(), '')
        saved = self.engine.store.get(self.task['id'])
        self.assertEqual(saved['patch'], '')
        self.assertEqual(saved['status'], 'awaiting_reply')
        self.assertEqual(saved['commits'][0]['patch'], p['patch'])
        context = json.loads(self.engine.initial_messages(saved)[1]['content'])
        self.assertEqual(context['source_commits'][-1]['commit'], result['commit'])
        self.assertEqual(context['current_diff'], '')

    def test_duplicate_approval_is_idempotent_even_after_restart(self):
        p = self.preview()
        result = self.approve(p)
        self.assertEqual(self.approve(p), result)
        self.engine.shutdown()
        self.engine = Engine(Path(self.temp.name) / 'state')
        self.assertEqual(self.approve(p), result)
        self.assertEqual(git(self.source, 'rev-list', '--count', 'HEAD').strip(), '2')

    def test_decline_saves_the_patch_and_blocks_stale_approval_until_reopened(self):
        p = self.preview()
        digest = hashlib.sha256(self.task['patch'].encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'patch changed'):
            self.engine.commit_decision(self.task['id'], {'decision':'defer','patch_digest':'old'})
        self.engine.commit_decision(self.task['id'], {'decision':'defer','patch_digest':digest})
        with self.assertRaisesRegex(ValueError, 'left these changes uncommitted'):
            self.approve(p)
        self.assertFalse((self.source / 'approved.txt').exists())
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD').strip(), self.head)
        self.engine.shutdown()
        self.engine = Engine(Path(self.temp.name) / 'state')
        saved = self.engine.store.get(self.task['id'])
        self.assertEqual(saved['human_decision'], {'decision':'defer','digest':digest})
        self.assertEqual(saved['patch'], self.task['patch'])
        self.engine.commit_decision(self.task['id'], {'decision':'review','patch_digest':digest})
        with patch.object(self.engine, 'checks', side_effect=AssertionError('No checks at commit')), patch.object(self.engine, 'request', side_effect=AssertionError('No model calls at commit')):
            self.approve(self.preview())

    def test_followup_commits_only_the_next_patch(self):
        first = self.approve(self.preview())
        self.task = self.engine.store.get(self.task['id'])
        self.workspace.replace_text('approved.txt', 'approved content', 'next content')
        self.review()
        p = self.preview()
        self.assertNotIn('new file mode', p['patch'])
        second = self.approve(p)
        self.assertNotEqual(first['commit'], second['commit'])
        self.assertEqual(git(self.source, 'rev-list', '--count', 'HEAD').strip(), '3')
        self.assertEqual((self.source / 'approved.txt').read_text(), 'next content\n')

    def test_missing_stale_or_wrong_task_approval_cannot_commit(self):
        p = self.preview()
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.approve(p, approval_id='not-a-preview')
        self.engine.commit_previews[p['approval_id']]['created'] -= 601
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.approve(p)
        p = self.preview()
        self.engine.commit_previews[p['approval_id']]['task_id'] = 'another-task'
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.approve(p)
        self.assertFalse((self.source / 'approved.txt').exists())

    def test_patch_or_head_changes_invalidate_preview(self):
        p = self.preview()
        self.workspace.replace_text('approved.txt', 'approved content', 'different content')
        with self.assertRaisesRegex(ValueError, 'verification'):
            self.approve(p)
        self.review()
        with self.assertRaisesRegex(ValueError, 'changed after preview'):
            self.approve(p)
        p = self.preview()
        git(self.source, 'commit', '--allow-empty', '-qm', 'Another commit')
        with self.assertRaisesRegex(ValueError, 'changed after preview'):
            self.approve(p)
        self.assertFalse((self.source / 'approved.txt').exists())

    def test_dirty_index_worktree_and_untracked_files_are_preserved(self):
        p = self.preview()
        target = self.source / 'personal.txt'
        target.write_text('my unrelated work')
        for staged in (False, True):
            if staged:
                git(self.source, 'add', 'personal.txt')
            with self.assertRaisesRegex(ValueError, 'uncommitted'):
                self.approve(p)
            self.assertEqual(target.read_text(), 'my unrelated work')
            self.assertFalse((self.source / 'approved.txt').exists())
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD').strip(), self.head)

    def test_source_file_conflict_is_rejected(self):
        self.workspace.replace_text('math_utils.py', 'return min(value, upper)', 'return max(lower, min(value, upper))')
        self.review()
        target = self.source / 'math_utils.py'
        target.write_text(target.read_text() + '\n# external source edit\n')
        git(self.source, 'add', 'math_utils.py')
        git(self.source, 'commit', '-qm', 'Separate source change')
        with self.assertRaises(commits.ProjectConflict):
            self.preview()

    def reconcile(self):
        return self.engine.reconcile_project(self.task['id'], {'patch_digest': hashlib.sha256(self.task['patch'].encode()).hexdigest()})

    def source_change(self, name, content):
        (self.source / name).write_text(content)
        git(self.source, 'add', '--', name)
        git(self.source, 'commit', '-qm', 'Separate project changes')

    def test_add_add_reconciliation_keeps_both_versions_and_commits_only_after_new_review(self):
        self.source_change('approved.txt', 'existing project content\n')
        head = git(self.source, 'rev-parse', 'HEAD')
        old_workspace, old_patch = self.task['workspace'], self.task['patch']
        with self.assertRaises(commits.ProjectConflict) as failure:
            self.preview()
        self.assertEqual(failure.exception.files, ['approved.txt'])
        self.task = self.reconcile()
        self.assertEqual(self.task['status'], 'paused')
        self.assertEqual(self.task['workspace_generation'], 1)
        self.assertEqual(self.task['reconciliation']['conflicts'], ['approved.txt'])
        self.assertEqual(Workspace(old_workspace).patch(), old_patch)
        self.assertEqual((Path(old_workspace) / 'approved.txt').read_text(), 'approved content\n')
        self.assertTrue((Path(self.task['workspace']).parent / 'before.json').exists())
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD'), head)
        self.assertEqual(git(self.source, 'status', '--porcelain'), '')
        self.workspace = Workspace(self.task['workspace'])
        merged = self.workspace.text_bytes('approved.txt').decode()
        for text in ('<<<<<<< CURRENT PROJECT', 'existing project content', 'approved content', '>>>>>>> SAVED TASK'):
            self.assertIn(text, merged)
        with self.assertRaisesRegex(ValueError, 'conflict markers'):
            self.engine.checks(Runtime(self.task))
        self.workspace.replace_text('approved.txt', merged, 'existing project content\napproved content\n')
        with self.assertRaisesRegex(ValueError, 'verification and review'):
            self.preview()
        self.review()
        p = self.preview()
        self.assertNotIn('new file mode', p['patch'])
        self.approve(p)
        self.assertEqual((self.source / 'approved.txt').read_text(), 'existing project content\napproved content\n')
        self.assertEqual(self.workspace.patch(), '')
        self.assertEqual(git(self.source, 'status', '--porcelain'), '')

    def test_identical_added_file_is_already_applied_without_an_empty_commit(self):
        self.source_change('approved.txt', 'approved content\n')
        head = git(self.source, 'rev-parse', 'HEAD')
        task = self.reconcile()
        self.assertEqual(task['status'], 'awaiting_reply')
        self.assertEqual(task['patch'], '')
        self.assertEqual(task['reconciliation']['conflicts'], [])
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD'), head)
        self.assertIn('nothing left to commit', task['events'][-1]['detail'])

    def test_same_patch_on_new_project_baseline_requires_fresh_checks_and_review(self):
        self.source_change('other.txt', 'new project context\n')
        old_patch = self.task['patch']
        self.task = self.reconcile()
        self.assertEqual(self.task['patch'], old_patch)
        self.assertEqual((Path(self.task['workspace']) / 'other.txt').read_text(), 'new project context\n')
        self.assertTrue(needs_patch_review(self.task))
        self.task['status'] = 'approved'
        self.engine.store.save(self.task)
        with self.assertRaisesRegex(ValueError, 'verification'):
            self.preview()
        self.task['checks'][-1]['generation'] = 1
        self.engine.store.save(self.task)
        with self.assertRaisesRegex(ValueError, 'review'):
            self.preview()
        self.assertTrue(needs_patch_review(self.task))
        self.task['checkpoints'][-1]['generation'] = 1
        self.assertFalse(needs_patch_review(self.task))

    def test_reconciliation_merges_nonoverlapping_edits_and_preserves_source_deletion(self):
        text = ''.join(f'line {i}\n' for i in range(40))
        self.source_change('long.txt', text)
        self.workspace.write_file('long.txt', text)
        git(self.workspace.root, 'add', 'long.txt')
        git(self.workspace.root, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'File baseline')
        self.workspace.replace_text('long.txt', 'line 2\n', 'task line 2\n')
        self.review()
        self.source_change('long.txt', text.replace('line 30\n', 'project line 30\n'))
        git(self.source, 'rm', 'test_math_utils.py')
        git(self.source, 'commit', '-qm', 'Remove old test')
        task = self.reconcile()
        self.assertEqual(task['reconciliation']['conflicts'], [])
        merged = (Path(task['workspace']) / 'long.txt').read_text()
        self.assertIn('task line 2\n', merged)
        self.assertIn('project line 30\n', merged)
        self.assertFalse((Path(task['workspace']) / 'test_math_utils.py').exists())

    def test_reconciliation_preserves_empty_file_additions_and_executable_mode(self):
        self.workspace.write_file('empty.txt', '')
        self.workspace.path('approved.txt').chmod(0o700)
        self.review()
        task = self.reconcile()
        self.assertTrue((Path(task['workspace']) / 'empty.txt').is_file())
        self.assertTrue((Path(task['workspace']) / 'approved.txt').stat().st_mode & 0o111)

    def test_delete_modify_reconciliation_preserves_project_text_for_resolution(self):
        self.workspace.path('math_utils.py').unlink()
        self.review()
        self.source_change('math_utils.py', 'def clamp(*args):\n    return 7\n')
        task = self.reconcile()
        self.assertIn('math_utils.py', task['reconciliation']['conflicts'])
        self.assertIn('return 7', (Path(task['workspace']) / 'math_utils.py').read_text())

    def test_reconciliation_rejects_stale_approval_dirty_source_and_pending_commit(self):
        with self.assertRaisesRegex(ValueError, 'patch changed'):
            self.engine.reconcile_project(self.task['id'], {'patch_digest': 'stale'})
        (self.source / 'personal.txt').write_text('keep this')
        with self.assertRaisesRegex(ValueError, 'uncommitted'):
            self.reconcile()
        self.assertEqual((self.source / 'personal.txt').read_text(), 'keep this')
        self.assertEqual(self.engine.store.get(self.task['id'])['workspace'], self.task['workspace'])
        self.task['commit_pending'] = {'anything': True}
        self.engine.store.save(self.task)
        with self.assertRaisesRegex(ValueError, 'saved commit attempt'):
            self.reconcile()

    def test_reconciliation_rejects_concurrent_source_move_and_retains_old_task(self):
        original = Workspace.snapshot
        def moved(*args, **kwargs):
            result = original(*args, **kwargs)
            git(self.source, 'commit', '--allow-empty', '-qm', 'Source advanced')
            return result
        with patch.object(Workspace, 'snapshot', side_effect=moved):
            with self.assertRaisesRegex(ValueError, 'changed during reconciliation'):
                self.reconcile()
        self.assertEqual(self.engine.store.get(self.task['id'])['workspace'], self.task['workspace'])
        self.assertEqual(self.workspace.text_bytes('approved.txt'), b'approved content\n')

    def test_reconciled_copy_and_historical_evidence_survive_restart(self):
        old_checks = self.task['checks']
        task = self.reconcile()
        self.engine.shutdown()
        self.engine = Engine(Path(self.temp.name) / 'state')
        saved = self.engine.store.get(task['id'])
        self.assertEqual(saved['workspace'], task['workspace'])
        self.assertEqual(saved['checks'], old_checks)
        self.assertEqual(saved['workspace_generation'], 1)
        self.assertIn('project_reconciliation', json.loads(self.engine.initial_messages(saved)[1]['content']))

    def test_old_checkpoint_cannot_overwrite_a_reconciled_copy(self):
        self.task['checkpoints'][-1]['number'] = 1
        self.engine.store.save(self.task)
        task = self.reconcile()
        before = Workspace(task['workspace']).patch()
        with self.assertRaisesRegex(ValueError, 'previous task copy'):
            self.engine.rollback_checkpoint(task['id'], 1)
        self.assertEqual(Workspace(task['workspace']).patch(), before)

    def test_checkpoint_reruns_checks_after_project_context_changes(self):
        self.task['checks'][-1]['command'] = self.task['check_command']
        self.engine.store.save(self.task)
        self.task = self.reconcile()
        with patch.object(self.engine, 'checks', return_value={'passed': False}) as checks:
            result = self.engine.checkpoint(Runtime(self.task), {'summary': 'Reconciled project'})
        checks.assert_called_once()
        self.assertEqual(result['decision'], 'REQUEST_CHANGES')

    def test_completed_reconciliation_does_not_steer_future_requests_back_to_old_work(self):
        self.task = self.reconcile()
        self.assertIn('operator requested reconciliation', reconciliation.guidance(self.task))
        self.review()
        self.assertEqual(reconciliation.guidance(self.task), '')

    def test_nonoverlapping_committed_source_edits_are_preserved(self):
        content = ''.join(f'line {i}\n' for i in range(40))
        (self.source / 'long.txt').write_text(content)
        git(self.source, 'add', 'long.txt')
        git(self.source, 'commit', '-qm', 'Long file baseline')
        self.workspace.write_file('long.txt', content)
        git(self.workspace.root, 'add', 'long.txt')
        git(self.workspace.root, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Long file baseline')
        self.workspace.replace_text('long.txt', 'line 2\n', 'approved line 2\n')
        self.review()
        (self.source / 'long.txt').write_text(content.replace('line 30\n', 'separate line 30\n'))
        git(self.source, 'add', 'long.txt')
        git(self.source, 'commit', '-qm', 'Separate edit')
        self.approve(self.preview())
        result = (self.source / 'long.txt').read_text()
        self.assertIn('approved line 2\n', result)
        self.assertIn('separate line 30\n', result)

    def test_unreviewed_patch_is_blocked_but_answer_after_review_is_allowed(self):
        self.task['status'] = 'awaiting_reply'
        self.engine.store.save(self.task)
        self.preview()
        self.task['checkpoints'][-1]['decision'] = 'REQUEST_CHANGES'
        self.engine.store.save(self.task)
        with self.assertRaisesRegex(ValueError, 'review'):
            self.preview()

    def test_hooks_do_not_run_and_detached_head_is_blocked(self):
        hook = self.source / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\ntouch should-not-exist\nexit 1\n')
        hook.chmod(0o700)
        self.approve(self.preview())
        self.assertFalse((self.source / 'should-not-exist').exists())
        git(self.source, 'checkout', '--detach', '-q')
        with self.assertRaisesRegex(ValueError, 'Check out a branch'):
            commits.source_state(self.source)

    def test_failed_ref_update_preserves_staged_patch_and_recovers_after_restart(self):
        p = self.preview()
        real = commits.source_git
        def fail_ref(source, *args, **kwargs):
            if args[0] == 'update-ref':
                raise ValueError('Ref is locked')
            return real(source, *args, **kwargs)
        with patch.object(commits, 'source_git', side_effect=fail_ref):
            with self.assertRaisesRegex(ValueError, 'saved commit attempt'):
                self.approve(p)
        self.assertTrue((self.source / 'approved.txt').exists())
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD').strip(), self.head)
        with self.assertRaisesRegex(ValueError, 'Finish the saved'):
            self.engine.start(self.task['id'])
        with self.assertRaisesRegex(ValueError, 'already approved and started'):
            self.engine.commit_decision(self.task['id'], {'decision':'defer','patch_digest':hashlib.sha256(p['patch'].encode()).hexdigest()})
        self.engine.shutdown()
        self.engine = Engine(Path(self.temp.name) / 'state')
        p = self.preview()
        self.assertTrue(p['retry'])
        result = self.approve(p)
        self.assertEqual(self.approve(p), result)
        self.assertEqual(git(self.source, 'status', '--porcelain'), '')
        self.assertEqual(git(self.source, 'rev-list', '--count', 'HEAD').strip(), '2')

    def test_recovery_after_source_commit_does_not_commit_twice(self):
        p = self.preview()
        with patch.object(commits, 'advance_workspace', side_effect=ValueError('Interrupted')):
            with self.assertRaisesRegex(ValueError, 'Interrupted'):
                self.approve(p)
        self.assertEqual(git(self.source, 'rev-list', '--count', 'HEAD').strip(), '2')
        self.approve(self.preview())
        self.assertEqual(self.workspace.patch(), '')
        self.assertEqual(git(self.source, 'rev-list', '--count', 'HEAD').strip(), '2')

    def test_recovery_does_not_discard_intervening_user_edits(self):
        p = self.preview()
        with patch.object(commits, 'apply_and_commit', side_effect=ValueError('Interrupted')):
            with self.assertRaises(ValueError):
                self.approve(p)
        (self.source / 'personal.txt').write_text('keep me')
        with self.assertRaisesRegex(ValueError, 'uncommitted'):
            self.preview()
        self.assertEqual((self.source / 'personal.txt').read_text(), 'keep me')


if __name__ == '__main__':
    unittest.main()
