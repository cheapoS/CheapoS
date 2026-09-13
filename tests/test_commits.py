import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from cheapos import commits
from cheapos.verification import evidence_identity
from cheapos.engine import Engine, Runtime, needs_patch_review
from cheapos.workspace import Workspace, git
from commit_fixture import CommitCase


class CommitTests(CommitCase):
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
        second = self.approve(self.preview())
        self.assertEqual(git(self.source, 'show', '--format=', '--name-only', second['commit']).strip(), 'approved.txt')
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD').strip(), second['commit'])
        self.assertEqual(git(self.source, 'rev-parse', second['commit'] + '^').strip(), first['commit'])
        self.assertEqual((self.source / 'approved.txt').read_text(), 'next content\n')
        self.assertEqual(git(self.source, 'rev-list', '--count', 'HEAD').strip(), '3')

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


if __name__ == '__main__':
    unittest.main()
