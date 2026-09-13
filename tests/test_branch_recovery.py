import copy
import json
import unittest
import threading
import time
import shutil
from pathlib import Path
from cheapos.engine import Engine, Runtime
from cheapos.branch_budget import Ledger
from test_engine import wait_for
import test_branch_execution as execution
from cheapos import branch_commits, branch_evidence
from cheapos.workspace import git
import test_branch_start as fixture


class BranchRecoveryTests(unittest.TestCase):
    setUp = fixture.BranchStartTests.setUp

    def started(self):
        proposal = self.engine.branch.prepare(self.values)
        return self.engine.branch.authorize(proposal['task_id'], {'proposal_id': proposal['proposal_id'], 'approved': True})

    def restart(self):
        restarted = Engine(self.root / 'state', fixture_delay=0)
        self.addCleanup(restarted.shutdown)
        restarted.config = copy.deepcopy(self.engine.config)
        return restarted

    def test_restart_worker_check_review_retains_allowance_and_clears_transients_without_dispatch(self):
        task = self.started()
        for status, item_status in [('running', 'working'), ('waiting_approval', 'checking'), ('reviewing', 'reviewing')]:
            with self.subTest(status=status):
                task['status'] = status
                task['branch_run'].update(status='running', current_item_id='one')
                task['branch_run']['items'][0]['status'] = item_status
                task['branch_run']['consumption'].update(working_seconds=46, requests=7, dollars=.25)
                task.update(stream={'text': 'partial'}, check_stream={'output': 'partial'}, pending_approval={'command': ['old']})
                self.engine.store.save(task)
                restarted = self.restart()
                loaded = restarted.store.get(task['id'])
                self.assertFalse(restarted.runtimes)
                self.assertEqual(loaded['branch_run']['pause_reason'], 'restart')
                self.assertEqual(loaded['branch_run']['items'][0]['status'], item_status)
                self.assertEqual(loaded['branch_run']['consumption']['working_seconds'], 46)
                self.assertEqual(loaded['branch_run']['consumption']['requests'], 7)
                for key in ('stream', 'check_stream', 'pending_approval'): self.assertIsNone(loaded[key])

    def test_restart_resume_requires_fresh_scoped_consent_without_reauthorizing_run(self):
        task = self.started()
        restarted = self.restart()
        launched = []
        restarted.branch.launch = lambda task_id: launched.append(task_id) or restarted.store.get(task_id)
        proposal = restarted.branch.resume(task['id'], {})
        self.assertTrue(proposal['needs_consent'])
        self.assertFalse(launched)
        with self.assertRaises(ValueError): restarted.branch.resume(task['id'], {'approved': True, 'proposal_id': 'forged'})
        result = restarted.branch.resume(task['id'], {'approved': True, 'proposal_id': proposal['proposal_id']})
        self.assertFalse(result['needs_consent'])
        self.assertEqual(launched, [task['id']])
        self.assertEqual(result['task']['branch_run']['authorization_ref'], task['branch_run']['authorization_ref'])
        self.assertTrue(restarted.branch.scopes.authorize(result['task'], task['check_command']))

    def test_feature_ref_drift_and_checked_out_worktree_block_before_dispatch(self):
        task = self.started()
        self.engine.branch.launch = self.launch
        original = task['branch_run']['expected_feature_tip']
        tree = git(self.source, 'rev-parse', original + '^{tree}').strip()
        other = git(self.source, 'commit-tree', tree, '-p', original, '-m', 'External').strip()
        git(self.source, 'update-ref', 'refs/heads/feature/job', other)
        with self.assertRaises(ValueError): self.engine.branch.resume(task['id'], {})
        self.assertFalse(self.engine.runtimes)
        git(self.source, 'update-ref', 'refs/heads/feature/job', original)
        git(self.source, 'worktree', 'add', str(self.root / 'linked'), 'feature/job')
        with self.assertRaises(ValueError): self.engine.branch.resume(task['id'], {})
        self.assertFalse(self.engine.runtimes)

    def test_target_movement_preserves_feature_run_and_revocation_prevents_resume(self):
        task = self.started()
        old_feature = task['branch_run']['expected_feature_tip']
        (self.source / 'operator.txt').write_text('New target work')
        git(self.source, 'add', '.'); git(self.source, 'commit', '-qm', 'Operator target change')
        result = self.engine.branch.resume(task['id'], {})
        self.assertFalse(result['needs_consent'])
        self.assertEqual(result['task']['branch_run']['expected_feature_tip'], old_feature)
        self.engine.branch.revoke(task['id'])
        with self.assertRaises(ValueError): self.engine.branch.resume(task['id'], {})
        self.assertEqual(git(self.source, 'rev-parse', 'feature/job').strip(), old_feature)

    def test_pause_cancels_real_check_process_and_route_cooldown(self):
        task = self.started()
        marker = self.root / 'check-started'
        (Path(task['workspace']) / 'test_slow.py').write_text('import unittest, time\nfrom pathlib import Path\nclass Slow(unittest.TestCase):\n def test_wait(self):\n  Path(' + repr(str(marker)) + ').write_text("running")\n  time.sleep(30)\n')
        errors = []
        runtime = Runtime(task)
        runtime.branch_ledger = Ledger(runtime, lambda: self.engine.store.save(task), lock=self.engine.lock)
        def check():
            runtime.branch_ledger.begin()
            try: self.engine.checks(runtime)
            except Exception as error: errors.append(error)
            finally: runtime.branch_ledger.end()
        runtime.thread = threading.Thread(target=check)
        self.engine.runtimes[task['id']] = runtime
        runtime.thread.start()
        try:
            wait_for(marker.exists, seconds=10)
            self.engine.stop(task['id'])
            runtime.thread.join(5)
            self.assertFalse(runtime.thread.is_alive())
            self.assertEqual(task['checks'][-1]['outcome'], 'user_paused')
            self.assertTrue(errors)
        finally:
            runtime.stop.set(); runtime.thread.join(5)
        consumed = task['branch_run']['consumption']['working_seconds']
        task['route_unavailable'] = {'can_wait': True, 'retry_at': time.time() + 30, 'role': 'worker'}
        waiting = Runtime(task)
        waiting.branch_ledger = Ledger(waiting, lambda: self.engine.store.save(task), lock=self.engine.lock)
        def cooldown():
            waiting.branch_ledger.begin()
            try: self.engine.wait_for_route(waiting)
            except InterruptedError: pass
            finally: waiting.branch_ledger.end()
        waiting.thread = threading.Thread(target=cooldown)
        self.engine.runtimes[task['id']] = waiting
        waiting.thread.start()
        try:
            wait_for(lambda: task.get('route_wait') is not None)
            self.engine.stop(task['id']); waiting.thread.join(5)
            self.assertFalse(waiting.thread.is_alive())
            self.assertIsNone(task['route_wait'])
            self.assertGreater(task['branch_run']['consumption']['working_seconds'], consumed)
        finally:
            waiting.stop.set(); waiting.thread.join(5)

    def test_restart_from_actual_blocked_review_keeps_uncertain_request_and_no_dispatch(self):
        task = self.started()
        entered = threading.Event()
        scripted = execution.ScriptedRun()
        class Provider:
            streams_output = True
            def complete_with_progress(self, messages, tools, maximum, emit, stopped):
                if any(t['function']['name'] == 'review_decision' for t in tools):
                    entered.set()
                    while not stopped(): time.sleep(.01)
                    raise InterruptedError('Fixture review interrupted')
                return scripted.complete(messages, tools, maximum)
        self.engine.provider_factory = lambda *args: Provider()
        self.launch(task['id'])
        runtime = self.engine.runtimes[task['id']]
        try:
            self.assertTrue(entered.wait(30))
            # Snapshot the durable state at the actual interrupted request boundary.
            crash_state = self.root / 'crash-state'
            target = crash_state / 'tasks' / task['id'] / 'task.json'
            target.parent.mkdir(parents=True)
            shutil.copyfile(self.root / 'state/tasks' / task['id'] / 'task.json', target)
            saved = json.loads(target.read_text())
            restarted = Engine(crash_state, fixture_delay=0)
            self.addCleanup(restarted.shutdown)
            loaded = restarted.store.get(task['id'])
            self.assertFalse(restarted.runtimes)
            self.assertEqual(loaded['branch_run']['pause_reason'], 'restart')
            self.assertEqual(loaded['branch_run']['items'][0]['status'], 'reviewing')
            self.assertEqual(loaded['usage'], saved['usage'])
            self.assertIsNotNone(loaded['in_flight'])
            self.assertFalse(loaded['branch_run']['pending_operations'])
            self.assertEqual(git(self.source, 'rev-list', '--count', 'main..feature/job').strip(), '0')
        finally:
            runtime.stop.set(); runtime.thread.join(10)
            self.assertFalse(runtime.thread.is_alive())

    def test_restart_finishes_source_commit_once_before_fresh_grant_and_next_item(self):
        task = self.started(); run = task['branch_run']; item = run['items'][0]
        run['current_item_id'] = item['id']; item['status'] = 'committing'
        (Path(task['workspace']) / 'hello.py').write_text('value=2\n')
        self.engine.checks(Runtime(task))
        current = branch_evidence.candidate(task, branch_commits.context(run, item), item['required_checks'], item['acceptance_criteria'])
        item['ready_receipt'] = branch_evidence.ready_receipt(current, branch_evidence.current_checks(current, task['checks']), {'candidate_id': current['id'], 'decision': 'APPROVE', 'feedback': 'Verified changed value'}, 'worker', 'reviewer', {'Works': {'passed': True, 'evidence': 'Read hello.py and ran required check'}})
        operation = branch_commits.prepare(task, run, item, item['ready_receipt'], self.engine.branch.validate_authority)
        run['pending_operations'] = [operation]
        def interrupted_save(value):
            if value['stage'] == 'source_committed': raise OSError('Crash after source CAS')
            run['pending_operations'] = [copy.deepcopy(value)]
            self.engine.store.save(task)
        with self.assertRaises(OSError): branch_commits.finish(task, run, item, operation, interrupted_save, self.engine.branch.validate_authority)
        self.assertEqual(git(self.source, 'rev-parse', 'feature/job').strip(), operation['new_tip'])
        restarted = self.restart()
        result = restarted.branch.resume(task['id'], {})
        self.assertTrue(result['needs_consent'])
        loaded = restarted.store.get(task['id']); recovered = loaded['branch_run']
        self.assertFalse(recovered['pending_operations'])
        self.assertEqual(recovered['items'][0]['status'], 'committed')
        self.assertEqual(len(recovered['completed_operations']), 1)
        self.assertEqual(len([event for event in recovered['events'] if event['kind'] == 'item_completed']), 1)
        self.assertEqual(git(self.source, 'rev-list', '--count', operation['old_tip'] + '..feature/job').strip(), '1')
        restarted.branch.resume(task['id'], {})
        self.assertEqual(len(restarted.store.get(task['id'])['branch_run']['completed_operations']), 1)
        self.assertFalse(restarted.runtimes)


if __name__ == '__main__': unittest.main()
