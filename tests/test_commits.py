import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cheapos import commits
from cheapos.engine import Engine
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
        self.task['checks'].append({'passed': True, 'digest': hashlib.sha256(self.task['patch'].encode()).hexdigest()})
        self.task['checkpoints'].append({'decision': 'APPROVE', 'diff': self.task['patch'], 'worker_summary': 'Add approved example'})
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
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            self.preview()

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
