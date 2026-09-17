"""In-memory review continuation; no Git fixtures, sleeps or model/network calls."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_review, branch_review_recovery as recovery, branch_pause, routing
from cheapos.engine import ProgressPause
from cheapos.providers import BudgetError
from cheapos.provider_recovery import review_turns
from tests import test_branch_disagreement as fixtures


class ItemReviewRecoveryTests(unittest.TestCase):
    fixture = fixtures.ReviewCoachingTests.fixture

    def automatic_fixture(self):
        task, engine, runtime = self.fixture()
        task.update(execution={'mode': 'remote'}, route={'base_url': 'gateway'},
                    usage={'cost': 0, 'reviewer': {'tokens': 100}}, limits={'cost': 0})
        return task, engine, runtime

    def approval(self, invalid=False):
        return {'tool_calls': [{'id': 'decision', 'name': 'review_decision', 'result': {
            'decision': 'APPROVE', 'candidate_id': 'candidate', 'feedback': 'Meets criteria',
            'defects': [fixtures.defect()] if invalid else [],
            'criteria_outcomes': {'exact values': {'passed': True, 'evidence': 'Source and checks'}}}}]}

    def selector(self, task, model='replacement'):
        def select(engine, runtime, role, replace):
            self.assertEqual(role, 'reviewer');self.assertTrue(replace)
            self.assertIn(task['providers']['reviewer']['model'], recovery.failed_models(task))
            task['providers']['reviewer'] = {'model': model}
        return select

    def test_invalid_approvals_handoff_without_worker_or_check_replay(self):
        task, engine, runtime = self.automatic_fixture()
        task['branch_run']['guidance'] = [{'item_id': 'one', 'message': 'Keep exact values.'}]
        before = copy.deepcopy(task)
        seen = []
        def respond(rt, messages, tools, role):
            pending = task['pending_review'];pending['review_requests'] = pending.get('review_requests', 0) + 1
            seen.append(copy.deepcopy(messages))
            return self.approval(task['providers']['reviewer']['model'] == 'reviewer')
        engine.request.side_effect = respond
        with patch.object(routing, 'select_remote', side_effect=self.selector(task)) as select:
            self.assertEqual(branch_review.checkpoint(engine, runtime, {})['decision'], 'APPROVE')
        self.assertEqual(engine.request.call_count, 4);select.assert_called_once()
        self.assertIn('Keep exact values.', json.dumps(seen[-1]))
        self.assertNotIn('cheapoS automatic review reassessment', json.dumps(seen[-1]))
        history = task['branch_run']['review_recovery']['candidate']['history']
        self.assertEqual(history[0]['review']['review_requests'], 3)
        self.assertEqual(task['branch_run']['review_disagreements']['candidate']['unsupported_attempts'], 3)
        self.assertEqual(task['review_count'], 4)
        for key in ('checks', 'usage', 'limits'):
            self.assertEqual(task[key], before[key])
        self.assertEqual(task['branch_run']['plan'], before['branch_run']['plan'])
        engine.checks.assert_not_called();engine.file_tool.assert_not_called()
        branch_review.evidence.ready_receipt.assert_called_once()

    def test_resume_old_exhausted_review_switches_and_preserves_valid_rejection(self):
        task, engine, runtime = self.automatic_fixture()
        task['pending_review'] = {'branch_candidate_id': 'candidate', 'review_requests': 7,
            'stop_diagnostic': {'kind': 'review_stall', 'reason': 'invalid_decision', 'coached': True}}
        task['branch_run']['review_disagreements'] = {'candidate': {'unsupported_attempts': 3}}
        runtime.task = task = json.loads(json.dumps(task))  # Saved legacy state on restart.
        result = self.approval()['tool_calls'][0]['result']
        result.update(decision='REQUEST_CHANGES', defects=[fixtures.defect()], feedback='A real defect remains.')
        engine.request.return_value = {'tool_calls': [{'id': 'reject', 'name': 'review_decision', 'result': result}]}
        with patch.object(routing, 'select_remote', side_effect=self.selector(task)) as select:
            self.assertEqual(branch_review.checkpoint(engine, runtime, {})['decision'], 'REQUEST_CHANGES')
        select.assert_called_once();engine.request.assert_called_once()
        branch_review.evidence.ready_receipt.assert_not_called()
        self.assertTrue(task['branch_run']['items'][0]['review_repair']['defects'])

    def test_repeated_reads_tool_errors_and_missing_decisions_recover_automatically(self):
        for failure in ('reads', 'tool_errors', 'no_decision'):
            with self.subTest(failure=failure):
                task, engine, runtime = self.automatic_fixture()
                if failure == 'tool_errors':engine.file_tool.return_value = {'error': 'Unknown file'}
                def respond(rt, messages, tools, role, **kwargs):
                    if task['providers']['reviewer']['model'] != 'reviewer':return self.approval()
                    if failure == 'no_decision':return {'content': 'Still considering.'}
                    return {'tool_calls': [{'id': 'read', 'name': 'read_file', 'result': {'path': 'report.py'}}]}
                engine.request.side_effect = respond
                with patch.object(routing, 'select_remote', side_effect=self.selector(task)) as select:
                    self.assertEqual(branch_review.checkpoint(engine, runtime, {})['decision'], 'APPROVE')
                select.assert_called_once();self.assertEqual(engine.request.call_count, 4)
                engine.checks.assert_not_called()

    def test_pool_exhaustion_remains_durable_and_resume_never_replays_failed_reviewers(self):
        task, engine, runtime = self.automatic_fixture()
        engine.request.return_value = self.approval(invalid=True)
        def select(e, rt, role, replace):
            failed = recovery.failed_models(rt.task)
            if len(failed) >= 4:
                raise routing.RoutingPause('No unused eligible reviewer is available.')
            rt.task['providers']['reviewer'] = {'model': 'replacement-' + str(len(failed))}
        with patch.object(routing, 'select_remote', side_effect=select) as choose:
            for _ in range(3):
                with self.assertRaises(routing.RoutingPause) as caught:
                    branch_review.checkpoint(engine, runtime, {})
                self.assertIn('No unused eligible reviewer', str(caught.exception))
                runtime.task = json.loads(json.dumps(runtime.task))
        self.assertEqual(choose.call_count, 6);self.assertEqual(engine.request.call_count, 12)
        self.assertEqual(runtime.task['branch_run']['review_disagreements']['candidate']['unsupported_attempts'], 12)
        branch_review.evidence.ready_receipt.assert_not_called()

    def test_manual_pin_stop_and_budget_cannot_be_bypassed_by_handoff(self):
        for boundary in ('pin', 'stop', 'budget'):
            with self.subTest(boundary=boundary):
                task, engine, runtime = self.automatic_fixture()
                task['pending_review'] = {'branch_candidate_id': 'candidate',
                    'stop_diagnostic': {'kind': 'review_stall', 'reason': 'invalid_decision', 'coached': True}}
                if boundary == 'pin':task['operator_reviewer_model'] = 'reviewer'
                elif boundary == 'stop':runtime.stop = SimpleNamespace(is_set=lambda: True)
                else:runtime.guard.side_effect = BudgetError('Authorized spending exhausted')
                error = ProgressPause if boundary == 'pin' else InterruptedError if boundary == 'stop' else BudgetError
                with patch.object(routing, 'select_remote') as select, self.assertRaises(error):
                    branch_review.checkpoint(engine, runtime, {})
                select.assert_not_called();engine.request.assert_not_called()

    def test_interrupted_selection_resumes_once_with_same_history(self):
        task, engine, runtime = self.automatic_fixture()
        # Restart can occur after the last request was saved but before _stop.
        task['pending_review'] = {'branch_candidate_id': 'candidate', 'review_requests': 8}
        def interrupted(e, rt, role, replace):
            rt.task['providers']['reviewer'] = {'model': 'replacement'}
            raise InterruptedError('Restart after selection')
        with patch.object(routing, 'select_remote', side_effect=interrupted), self.assertRaises(InterruptedError):
            branch_review.checkpoint(engine, runtime, {})
        runtime.task = task = json.loads(json.dumps(task))
        engine.request.return_value = self.approval()
        with patch.object(routing, 'select_remote') as select:
            self.assertEqual(branch_review.checkpoint(engine, runtime, {})['decision'], 'APPROVE')
        select.assert_not_called();engine.request.assert_called_once()
        self.assertEqual(len(task['branch_run']['review_recovery']['candidate']['history']), 1)

    def test_request_baseline_keeps_cumulative_counts_and_outage_accounting(self):
        task = {'request_metrics': [{'id': 'failure', 'role': 'reviewer', 'purpose': 'work',
            'review_candidate_id': 'candidate', 'status': 'failed', 'dispatched': True, 'error_code': 'http_503'}]}
        pending = {'branch_candidate_id': 'candidate', 'review_requests': 11, 'review_turn_baseline': 7}
        self.assertEqual(review_turns(task, pending), 3)
        self.assertEqual(pending['review_requests'], 11)


class ReviewerRouteExclusionTests(unittest.TestCase):
    def test_selector_excludes_failed_aliases_workers_paid_and_cooling_models_before_probe(self):
        policy = {'version': 1, 'base_url': 'http://127.0.0.1:20128/v1', 'connection_revision': 'a'*32, 'included_models': []}
        models = [{'id': name, 'free': True, 'tool_calling': True} for name in
                  ('failed/model', 'no-think/failed/model', 'worker/model', 'paid/model', 'cool/model', 'good/model')]
        models[3]['free'] = False
        task = {'execution': {'mode': 'remote'}, 'providers': {'worker': {'model': 'worker/model'}, 'reviewer': {'model': 'failed/model'}},
                'events': [], 'route': {'base_url': policy['base_url'], 'access_policy': policy}, 'access_policy': policy,
                'pending_review': {'branch_candidate_id': 'candidate'},
                'branch_run': {'review_recovery': {'candidate': {'failed_models': ['failed/model']}}}}
        pool = SimpleNamespace(observation=lambda endpoint, model, *a: {'cooling_down': model == 'cool/model'},
            rank=lambda *a: 0, fresh_probe=lambda *a: False, claim_probe=lambda *a: (True, None), release_probe=Mock(), record=Mock())
        gateway = SimpleNamespace(settings=policy, matches=lambda _: True, catalog=lambda **k: {'status': 'ready', 'models': models}, pool=pool)
        engine = SimpleNamespace(gateway=gateway, event=Mock(), store=SimpleNamespace(save=Mock()),
            request=Mock(return_value={'tool_calls': [{'id': 'probe'}]}), parse_call=lambda _: ('routing_ready', {'marker': routing.PROBE_MARKER}))
        runtime = SimpleNamespace(task=task, failed_models=set())
        routing.select_remote(engine, runtime, 'reviewer', replace=True)
        self.assertEqual(task['providers']['reviewer']['model'], 'good/model')
        engine.request.assert_called_once()
