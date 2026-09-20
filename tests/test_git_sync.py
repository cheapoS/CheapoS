"""Small local Git fetch/fast-forward cases; no GitHub, inference or waits."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cheapos import git_sync, github
from cheapos.workspace import git


class GitSyncTests(unittest.TestCase):
    def test_local_workflow_never_fetches_and_saved_remote_is_authoritative(self):
        with patch.object(git_sync, 'synchronize', return_value={'state': 'current'}) as sync:
            self.assertIsNone(git_sync.before_task('/project', None))
            self.assertIsNone(git_sync.before_task('/project', {'values': {'git': {'workflow': 'local'}}}))
            sync.assert_not_called()
            snapshot = {'values': {'git': {'workflow': 'pull_request', 'remote': 'upstream'}}}
            git_sync.before_task('/project', snapshot, 'refs/heads/master')
            sync.assert_called_once_with('/project', 'upstream', 'refs/heads/master')

    def test_fetch_fast_forward_retry_dirty_worktrees_and_divergence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            remote = root / 'remote.git'; source = root / 'source'; writer = root / 'writer'
            git(root, 'init', '-q', '--bare', '-b', 'production', str(remote))
            git(root, 'clone', '-q', str(remote), str(source))
            git(source, 'config', 'user.name', 'Test'); git(source, 'config', 'user.email', 'test@example.invalid')
            (source / 'app.txt').write_text('base\n'); (source / 'notes.txt').write_text('notes\n')
            git(source, 'add', '.'); git(source, 'commit', '-qm', 'base'); git(source, 'push', '-q', 'origin', 'production')
            git(root, 'clone', '-q', str(remote), str(writer))
            git(writer, 'config', 'user.name', 'Test'); git(writer, 'config', 'user.email', 'test@example.invalid')
            def change(value):
                (writer / 'app.txt').write_text(value)
                git(writer, 'commit', '-qam', 'remote change'); git(writer, 'push', '-q', 'origin', 'production')
                return git(writer, 'rev-parse', 'HEAD').strip()
            with patch.object(github, 'destination', return_value=('org/repo', str(remote))):
                tip = change('merged\n')
                # Unrelated staged and unstaged drafts survive the real merge.
                (source / 'notes.txt').write_text('staged\n'); git(source, 'add', 'notes.txt')
                (source / 'notes.txt').write_text('unstaged\n')
                result = git_sync.synchronize(source, 'origin', merged_commit=tip)
                self.assertEqual(result['state'], 'updated', result)
                self.assertEqual(git(source, 'rev-parse', 'HEAD').strip(), tip)
                self.assertEqual(git(source, 'rev-parse', 'origin/production').strip(), tip)
                self.assertEqual(git(source, 'show', ':notes.txt'), 'staged\n')
                self.assertEqual((source / 'notes.txt').read_text(), 'unstaged\n')
                self.assertEqual(git_sync.synchronize(source, 'origin', merged_commit=tip)['state'], 'current')
                # A different checked-out target is updated without switching source.
                linked = root / 'linked'
                git(source, 'checkout', '-qb', 'operator')
                git(source, 'worktree', 'add', '-q', str(linked), 'production')
                next_tip = change('second merge\n')
                self.assertEqual(git_sync.synchronize(source, 'origin', 'refs/heads/production')['state'], 'updated')
                self.assertEqual(git(linked, 'rev-parse', 'HEAD').strip(), next_tip)
                self.assertEqual(git(source, 'branch', '--show-current').strip(), 'operator')
                self.assertEqual((source / 'app.txt').read_text(), 'merged\n')
                # Overlap defers, and a later attempt resumes without a reset/stash.
                latest = change('third merge\n')
                (linked / 'app.txt').write_text('operator draft\n')
                self.assertEqual(git_sync.synchronize(source, 'origin', 'refs/heads/production')['state'], 'deferred')
                self.assertEqual((linked / 'app.txt').read_text(), 'operator draft\n')
                self.assertEqual(git(linked, 'rev-parse', 'HEAD').strip(), next_tip)
                (linked / 'app.txt').write_text('second merge\n')
                self.assertEqual(git_sync.synchronize(source, 'origin', 'refs/heads/production')['state'], 'updated')
                # Local commits are never reset, including after another remote merge.
                git(linked, 'commit', '--allow-empty', '-qm', 'local commit')
                local = git(linked, 'rev-parse', 'HEAD').strip()
                self.assertEqual(git_sync.synchronize(source, 'origin', 'refs/heads/production')['state'], 'ahead')
                change('fourth merge\n')
                self.assertEqual(git_sync.synchronize(source, 'origin', 'refs/heads/production')['state'], 'diverged')
                self.assertEqual(git(linked, 'rev-parse', 'HEAD').strip(), local)
                mismatch = git_sync.synchronize(source, 'origin', 'refs/heads/production', expected_destination=('other/repo', str(remote)))
                self.assertEqual(mismatch['state'], 'destination_changed')
                self.assertEqual(git_sync.synchronize(source, 'origin', 'refs/heads/production', merged_commit=local)['state'], 'merge_not_fetched')
                self.assertEqual(git(source, 'for-each-ref', 'refs/cheapos/sync').strip(), '')
                self.assertEqual((linked / 'app.txt').read_text(), 'third merge\n')

    def test_network_failure_is_safe_and_never_exposes_stderr(self):
        with patch.object(git_sync.work, 'inspect_source', side_effect=ValueError('https://secret@private.test')):
            result = git_sync.synchronize('/project', 'origin')
        self.assertEqual(result['state'], 'unavailable')
        self.assertTrue(result['retryable'])
        self.assertNotIn('secret', str(result))
