"""Merge acknowledgment/dispatch tests: memory only, no Git, model calls or sleeps."""
import copy
import threading
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_completion, branch_integration, branch_runs
from cheapos.admission import Admission
from cheapos.branch_authorization import ProposalRegistry


class BranchIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.saved = {'id': 'task', 'status': 'completed', 'events': [], 'branch_run': {
            'id': 'run', 'schema_version': 1, 'status': 'ready_for_merge', 'items': [],
            'events': [], 'event_sequence': 0, 'readiness': {'id': 'ready'},
            'final_evidence': {'acceptance_satisfied': True, 'checks_passed': True, 'review_approved': True,
                               'candidate_id': 'candidate', 'review_candidate_id': 'candidate',
                               'worker_model': 'worker', 'reviewer_model': 'reviewer'},
            'workspace_mapping': {'source': '/fixture'}}}
        self.engine = SimpleNamespace(lock=threading.RLock(), runtimes={},
            store=SimpleNamespace(get=lambda _: copy.deepcopy(self.saved), save=self.save))
        self.engine.admission = Admission(self.engine)
        self.engine.require_active_task = self.engine.admission.require_mutable
        self.engine.event = lambda task, *args: self.save(task)
        self.controller = SimpleNamespace(engine=self.engine, final_proposals=ProposalRegistry(),
                                          validate_authority=Mock())
        self.operation = {'id': 'operation', 'stage': 'prepared', 'feature_tip': 'a' * 40}
        self.contract = {'kind': 'merge', 'run_id': 'run', 'readiness_id': 'ready', 'operation': self.operation}
        self.proposal = self.controller.final_proposals.prepare('task', self.contract)
        self.values = {'preview_id': self.proposal['proposal_id'], 'approved': True}
        self.thread_patch = patch.object(branch_integration.threading, 'Thread')
        self.thread = self.thread_patch.start()
        self.addCleanup(self.thread_patch.stop)

    def save(self, task):
        self.saved = copy.deepcopy(task)

    def start(self, values=None):
        return branch_completion.merge(self.controller, 'task', values or self.values, background=True)

    def test_ack_is_durable_before_dispatch_without_git_or_evidence_reads(self):
        self.thread.return_value.start.side_effect = lambda: self.assertEqual(
            self.saved['branch_run']['merge_operation'], self.operation)
        with patch.object(branch_completion.final, 'validate') as evidence, patch.object(branch_completion.branch_merge, '_validate') as git:
            receipt = self.start()
        evidence.assert_not_called(); git.assert_not_called()
        self.assertEqual(receipt['branch_run']['merge_progress']['stage'], 'accepted')
        self.assertEqual(receipt['branch_run']['status'], 'merging')
        self.assertNotIn('merge_receipt', receipt['branch_run'])
        self.assertEqual(self.saved['branch_run']['merge_preview_id'], self.values['preview_id'])
        with self.assertRaises(ValueError): self.engine.admission.require_idle('task')
        receipt['branch_run']['status'] = 'altered'
        self.assertEqual(self.saved['branch_run']['status'], 'merging')

    def test_double_click_returns_same_operation_and_different_preview_is_rejected(self):
        first = self.start()
        self.assertEqual(self.start(), first)
        self.thread.return_value.start.assert_called_once()
        other = self.controller.final_proposals.prepare('task', {**self.contract, 'operation': {'id': 'other'}})
        with self.assertRaisesRegex(ValueError, 'different merge'):
            self.start({'preview_id': other['proposal_id'], 'approved': True})

    def test_consent_expiry_and_stale_readiness_reject_before_dispatch(self):
        for values in ({**self.values, 'approved': False}, {**self.values, 'extra': True}, {'recover': True, 'approved': True}):
            with self.assertRaises(ValueError): self.start(values)
        self.saved['branch_run']['readiness']['id'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'Readiness changed'): self.start()
        self.saved['branch_run']['readiness']['id'] = 'ready'
        self.controller.final_proposals.proposals[self.proposal['proposal_id']]['expires'] = 0
        with self.assertRaisesRegex(ValueError, 'expired'): self.start()
        self.thread.assert_not_called()

    def test_dispatch_holds_task_claim_while_existing_integrator_runs(self):
        self.start()
        self.engine.admission.repository = Mock(return_value=nullcontext())
        def integrate(controller, task_id, values, progress):
            self.assertEqual(values, {'approved': True, 'recover': True})
            self.assertEqual(self.engine.admission.operations[task_id], threading.get_ident())
            task = self.engine.store.get(task_id)
            progress(task, 'checking')
            self.assertEqual(self.saved['branch_run']['merge_progress']['label'], 'Checking reviewed changes')
        with patch.object(branch_completion, '_integrate', side_effect=integrate) as dispatch:
            branch_integration.complete(self.controller, 'task')
        dispatch.assert_called_once()
        self.assertNotIn('task', self.engine.admission.operations)

    def test_failure_keeps_exact_operation_and_concrete_reason_for_recovery(self):
        self.start()
        self.engine.admission.repository = Mock(return_value=nullcontext())
        with patch.object(branch_completion, '_integrate', side_effect=ValueError('Target checkout has uncommitted changes')):
            branch_integration.complete(self.controller, 'task')
        self.assertEqual(self.saved['status'], 'paused')
        self.assertEqual(self.saved['branch_run']['merge_operation'], self.operation)
        self.assertIn('uncommitted changes', self.saved['error'])
        self.assertNotIn('task', self.engine.admission.operations)
        self.start({'approved': True, 'recover': True})
        self.assertEqual(self.saved['branch_run']['status'], 'merging')
        self.assertNotIn('pause_detail', self.saved['branch_run'])

    def test_restart_retains_approved_operation_and_completed_duplicate_never_dispatches(self):
        self.start()
        self.engine.admission.operations.clear()
        branch_runs.recover_restart(self.saved['branch_run'])
        self.assertEqual(self.saved['branch_run']['status'], 'paused')
        self.assertEqual(self.saved['branch_run']['merge_operation'], self.operation)
        self.start({'approved': True, 'recover': True})
        run = self.saved['branch_run']
        run['merge_receipt'] = {**run.pop('merge_operation'), 'stage': 'completed'}
        run['status'] = 'merged'
        self.engine.admission.operations.clear()
        self.thread.reset_mock()
        self.assertEqual(self.start()['branch_run']['status'], 'merged')
        self.thread.assert_not_called()

    def test_thread_start_failure_preserves_approval_and_releases_reservation(self):
        self.thread.return_value.start.side_effect = RuntimeError('Thread could not start')
        with self.assertRaises(RuntimeError): self.start()
        self.assertEqual(self.saved['branch_run']['merge_operation'], self.operation)
        self.assertNotIn('task', self.engine.admission.operations)
        self.assertEqual(self.saved['branch_run']['merge_progress']['status'], 'failed')

    def test_slow_validation_does_not_hold_acknowledgment_or_engine_lock(self):
        self.thread_patch.stop()
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        self.engine.admission.repository = Mock(return_value=nullcontext())
        def integrate(controller, task_id, values, progress):
            entered.set()
            if not release.wait(2): raise AssertionError('Validation gate was not released')
        complete = branch_integration.complete
        def dispatch(*args):
            try: complete(*args)
            finally: finished.set()
        with patch.object(branch_completion, '_integrate', side_effect=integrate), patch.object(branch_integration, 'complete', side_effect=dispatch):
            try:
                receipt = self.start()
                self.assertEqual(receipt['branch_run']['merge_progress']['stage'], 'accepted')
                self.assertTrue(entered.wait(2))
                self.assertTrue(self.engine.lock.acquire(timeout=.2))
                self.engine.lock.release()
                self.assertEqual(self.start()['branch_run']['merge_operation']['id'], 'operation')
            finally:
                release.set()
                self.assertTrue(finished.wait(2))
