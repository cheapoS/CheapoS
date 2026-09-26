"""Small local snapshots and mocked GitHub reads; no models, network or waits."""
import copy
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import pr_followup as follow, github, git_sync, git_workflow
from cheapos.engine import Engine, Runtime
from cheapos.workspace import Workspace, git


class AdmissionTests(unittest.TestCase):
    def test_stale_client_learns_merge_before_accepting_a_message(self):
        task = {'id': 'a', 'patch': 'later edits', 'pull_request': {
            'id': 'publication', 'number': 7, 'repo': 'org/repo', 'head': 'published', 'base': 'production'}}
        engine = SimpleNamespace(lock=threading.RLock(), require_active_task=Mock(),
            store=SimpleNamespace(get=lambda _: task, save=Mock()))
        with patch.object(github, 'api', return_value={'merged': True, 'head': {'sha': 'published'},
                    'base': {'ref': 'production'}, 'merge_commit_sha': 'merged'}) as api:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, 'Continue in a new task'):
                    follow.check_before_work(engine, 'a')
            api.assert_called_once()
        self.assertEqual(task['patch'], 'later edits')
        self.assertEqual(task['pull_request']['ci']['state'], 'merged')

    def test_active_worker_stops_at_next_boundary_after_merge_is_known(self):
        runtime = Runtime({'pull_request': {'head':'published', 'ci':{'state':'merged','head':'published'}}})
        with self.assertRaisesRegex(InterruptedError, 'Later edits are saved'):
            runtime.guard()

    def test_nested_work_entries_read_once_and_network_failure_never_dispatches(self):
        class Owner:
            @follow.work_entry
            def start(self, task_id): return self.steer(task_id)
            @follow.work_entry
            def steer(self, task_id): return 'accepted'
        owner = Owner()
        with patch.object(follow, 'check_before_work') as check:
            self.assertEqual(owner.start('a'), 'accepted')
            check.assert_called_once_with(owner, 'a')
        with patch.object(follow, 'check_before_work', side_effect=ValueError('offline')):
            with self.assertRaisesRegex(ValueError, 'offline'): owner.start('a')


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.engine = Engine(self.root / 'profile', fixture_delay=0)
        self.addCleanup(self.engine.shutdown)
        self.source = self.root / 'source'; self.source.mkdir()
        git(self.source, 'init', '-q', '-b', 'production')
        git(self.source, 'config', 'user.name', 'Test'); git(self.source, 'config', 'user.email', 'test@example.invalid')
        (self.source / 'app.txt').write_text('published implementation\n')
        (self.source / 'remove.txt').write_text('retired\n')
        (self.source / 'binary.dat').write_bytes(b'\0published\xff')
        git(self.source, 'add', '.'); git(self.source, 'commit', '-qm', 'published')
        self.head = git(self.source, 'rev-parse', 'HEAD').strip()
        view = self.engine.settings_store.view()
        self.engine.settings_store.save({'git.workflow':'pull_request', 'keep_up_to_date': True}, expected_revision=view['revision'], operation_id='followup-fixture')
        self.task = self.engine.create({'repository': str(self.source), 'prompt': 'Original improvement', 'conversational': True})
        self.task['pull_request'] = {'id':'publication', 'source':str(self.source), 'base':'production',
            'repo':'org/repo', 'push_url':'https://github.com/org/repo.git', 'remote':'origin', 'number':7,
            'head':self.head, 'ci':{'state':'merged','head':self.head,'merged_commit':self.head},
            'url':'https://github.com/org/repo/pull/7', 'patch':''}
        self.workspace = Path(self.task['workspace'])
        (self.workspace / 'app.txt').write_text('published implementation\nlater fix\n')
        (self.workspace / 'remove.txt').unlink()
        (self.workspace / 'binary.dat').write_bytes(b'\0later\xff')
        (self.workspace / 'new.txt').write_text('new file\n'); (self.workspace / 'new.txt').chmod(0o755)
        self.engine.refresh_changes(self.task)
        self.task.update(status='approved', checks=[{'passed':True}], checkpoints=[{'decision':'APPROVE'}])
        self.engine.store.save(self.task)
        (self.source / 'unrelated.txt').write_text('another merged PR\n')
        git(self.source, 'add', '.'); git(self.source, 'commit', '-qm', 'new main')
        self.tip = git(self.source, 'rev-parse', 'HEAD').strip()

    def test_only_later_edits_survive_and_fresh_task_needs_new_review(self):
        self.task['command_backend'] = 'bubblewrap'
        self.engine.store.save(self.task)
        before = git(self.workspace, 'status', '--porcelain')
        git(self.source, 'checkout', '--detach', '-q')
        (self.source / 'local-draft.txt').write_text('never copy my draft\n')
        receipt = {'state':'updated', 'remote_head':self.tip, 'retryable':False}
        with patch.object(git_sync, 'synchronize', return_value=receipt) as sync:
            child = follow.create(self.engine, self.task['id'], {})
            self.assertEqual(child['command_backend'], 'bubblewrap')
            sync.assert_called_once()
            again = follow.create(self.engine, self.task['id'], {})
            self.assertEqual(child['id'], again['id'])
            sync.assert_called_once()  # Retry does not rebuild or reset a child.
        self.assertEqual(child['status'], 'awaiting_reply')
        self.assertEqual(child['checks'], []); self.assertEqual(child['checkpoints'], [])
        self.assertIsNone(child['pending_approval'])
        self.assertNotIn('pull_request', child)
        self.assertFalse(child['auto_approve_checks'])
        self.assertEqual(child['settings_snapshot'], self.task['settings_snapshot'])
        self.assertEqual(child['git_target'], {'branch':'refs/heads/production', 'head':self.tip})
        self.assertEqual(child['integration_policy'], {'keep_up_to_date': True,
            'target_ref':'refs/heads/production', 'target_tip':self.tip})
        self.assertTrue(child['follow_up']['applied'])
        workspace = Path(child['workspace'])
        self.assertEqual((workspace / 'unrelated.txt').read_text(), 'another merged PR\n')
        self.assertFalse((workspace / 'local-draft.txt').exists())
        self.assertFalse((workspace / 'remove.txt').exists())
        self.assertEqual((workspace / 'binary.dat').read_bytes(), b'\0later\xff')
        self.assertTrue((workspace / 'new.txt').stat().st_mode & 0o111)
        self.assertEqual((workspace / 'app.txt').read_text(), 'published implementation\nlater fix\n')
        self.assertEqual(git(self.workspace, 'status', '--porcelain'), before)
        self.assertEqual(follow.context(child)['history']['original_request'], self.task['prompt'])
        self.assertNotIn(child['id'], self.engine.runtimes)
        # Publishing the follow-up uses its reviewed committed base, not local
        # drafts or unrelated local commits added after the snapshot.
        (self.source / 'extra.txt').write_text('local unpushed commit\n')
        git(self.source, 'add', 'extra.txt'); git(self.source, 'commit', '-qm', 'local work')
        candidate = copy.deepcopy(child)
        candidate['checkpoints'] = [{'decision':'APPROVE','diff':candidate['patch']}]
        candidate['checks'] = [{}]
        with patch.object(self.engine, 'reviewed_patch'), patch('cheapos.engine.current_evidence', return_value=True):
            published = git_workflow._candidate(self.engine, candidate)
        self.assertEqual(published['parent'], self.tip)
        self.assertNotIn('extra.txt', git(self.source, 'ls-tree', '--name-only', published['tree']))

        # Lost parent-link write recovers the persisted child rather than creating another.
        parent = self.engine.store.get(self.task['id']); parent.pop('followups'); self.engine.store.save(parent)
        with patch.object(git_sync, 'synchronize') as sync:
            self.assertEqual(follow.create(self.engine, self.task['id'], {})['id'], child['id'])
            sync.assert_not_called()

    def test_overlap_retains_patch_for_agent_without_clobbering_new_code(self):
        (self.source / 'app.txt').write_text('newer implementation\n')
        git(self.source, 'commit', '-qam', 'overlap')
        tip = git(self.source, 'rev-parse', 'HEAD').strip()
        with patch.object(git_sync, 'synchronize', return_value={'state':'deferred', 'remote_head':tip, 'retryable':True}):
            child = follow.create(self.engine, self.task['id'], {})
        self.assertFalse(child['follow_up']['applied'])
        self.assertIn('later fix', follow.context(child)['retained_later_edits'])
        self.assertEqual((Path(child['workspace']) / 'app.txt').read_text(), 'newer implementation\n')
        self.assertEqual(child['patch'], '')

    def test_busy_unmerged_overrides_and_unavailable_fetch_do_not_create(self):
        with self.assertRaises(ValueError): follow.create(self.engine, self.task['id'], {'approved':True})
        with patch.object(git_sync, 'synchronize', return_value={'state':'unavailable'}):
            with self.assertRaisesRegex(ValueError, 'Could not fetch'): follow.create(self.engine, self.task['id'], {})
        with patch.object(self.engine.admission, 'require_idle', side_effect=ValueError('busy')):
            with self.assertRaisesRegex(ValueError, 'busy'): follow.create(self.engine, self.task['id'], {})
        self.assertNotIn('followups', self.engine.store.get(self.task['id']))
        self.task['pull_request']['ci']['state'] = 'passed'; self.engine.store.save(self.task)
        with self.assertRaisesRegex(ValueError, 'Refresh'): follow.create(self.engine, self.task['id'], {})


if __name__ == '__main__': unittest.main()
