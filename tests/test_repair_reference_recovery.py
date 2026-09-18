"""Saved repair continuation with in-memory providers; no Git, waits or inference."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_disagreement as disagreement, branch_review, repair_scope, route_health
from cheapos import continuation_policy, review_disputes
from cheapos.branch_worker_recovery import restore_local_repair_routes
from cheapos.engine import Engine
from tests import test_branch_disagreement as fixtures


class RepairReferenceTests(unittest.TestCase):
    def fixture(self):
        task, engine, runtime = fixtures.ReviewCoachingTests.fixture(self)
        run = task['branch_run']
        original = copy.deepcopy(run['plan'])
        run['authorization'] = {'contract': {'plan': original}}
        refs = repair_scope.select(run, ['one:1'])
        previous = {**copy.deepcopy(original['items'][0]), 'id': 'revision-1'}
        run['amendments'] = [{'item': previous, 'requirement_refs': copy.deepcopy(refs)}]
        item = run['items'][0]
        item['id'] = run['current_item_id'] = 'revision-2'
        finding = dict(fixtures.defect(), criterion='revision-1:1')
        disagreement.attach(task, item, {'candidate_id': 'before', 'requirement_refs': refs, 'defects': [finding]})
        return task, engine, runtime, item

    def test_saved_alias_reaches_worker_then_independent_review_without_operator(self):
        task, engine, runtime, item = self.fixture()
        original_repair = copy.deepcopy(item['review_repair'])
        task.update(prompt='Fix exact values', mode='unattended', demo=True,
                    usage={'cost': 0, 'reviewer': {'tokens': 0}}, limits={'dollars': 0, 'reviewer_tokens': 200000})
        engine.fixture_response = Mock(return_value={'content': 'Ready for checkpoint'})
        # Exercise the actual failing dispatch preparation, then the existing
        # independent checkpoint path with its unchanged candidate/check guards.
        with patch('cheapos.engine.worker_system', return_value='Worker policy'):
            result = Engine._perform_request(engine, runtime, [{'role': 'system', 'content': 'Policy'}], [], 'worker')
        self.assertEqual(result, {'content': 'Ready for checkpoint'})
        engine.fixture_response.assert_called_once()
        self.assertEqual(item['review_repair'], original_repair)
        key = original_repair['finding_ids'][0]
        def approve(rt, messages, tools, role):
            self.assertEqual(role, 'reviewer')
            tool = next(t for t in tools if t['function']['name'] == 'review_decision')
            allowed = tool['function']['parameters']['properties']['defects']['items']['properties']['criterion']['enum']
            self.assertEqual(set(allowed), {'one:1', 'exact values', 'revision-1:1'})
            packet = json.loads(messages[1]['content'])
            self.assertEqual(packet['repair_review']['finding_ids'], [key])
            self.assertEqual(packet['repair_review']['dispositions'][0]['evidence'], 'report.py:12 and saved passing check')
            self.assertEqual(task['branch_run']['dispute_ledger']['findings'][key]['status'], 'requested')
            return {'tool_calls': [{'id': 'decision', 'name': 'review_decision', 'result': {
                'decision': 'APPROVE', 'candidate_id': 'candidate', 'feedback': 'Source and checks satisfy the criterion',
                'defects': [], 'criteria_outcomes': {'exact values': {'passed': True, 'evidence': 'Verified source and checks'}}}}]}
        engine.request.side_effect = approve
        args = {'repair_dispositions': [{'finding_id': key, 'candidate_id': 'before', 'disposition': 'disproved',
                                         'evidence': 'report.py:12 and saved passing check'}]}
        self.assertEqual(branch_review.checkpoint(engine, runtime, args)['decision'], 'APPROVE')
        self.assertEqual(task['branch_run']['dispute_ledger']['findings'][key]['status'], 'independently_resolved')
        branch_review.evidence.ready_receipt.assert_called_once()
        engine.checks.assert_not_called()
        self.assertEqual(engine.request.call_count, 1)
        self.assertNotIn('pending_approval', task)

    def test_rejection_keeps_original_alias_finding_identity_and_counterevidence(self):
        task, engine, runtime, item = self.fixture()
        key = item['review_repair']['finding_ids'][0]
        def reject(rt, messages, tools, role):
            return {'tool_calls': [{'id': 'reject', 'name': 'review_decision', 'result': {
                'decision': 'REQUEST_CHANGES', 'candidate_id': 'candidate', 'feedback': 'Defect is still present',
                'defects': [dict(fixtures.defect(), criterion='one:1', finding_id=key)]}}]}
        engine.request.side_effect = reject
        args = {'repair_dispositions': [{'finding_id': key, 'candidate_id': 'before', 'disposition': 'disproved',
                                         'evidence': 'report.py:12 retains the original value'}]}
        self.assertEqual(branch_review.checkpoint(engine, runtime, args)['decision'], 'REQUEST_CHANGES')
        self.assertEqual(item['review_repair']['finding_ids'], [key])
        self.assertEqual(item['review_repair']['prior_counterevidence'][0]['disposition'], 'disproved')
        self.assertEqual(len(task['branch_run']['dispute_ledger']['findings'][key]['history']), 2)
        disagreement.pending(task, item)
        branch_review.evidence.ready_receipt.assert_not_called()

    def test_unknown_out_of_scope_and_forged_aliases_are_local_errors(self):
        task, _, _, item = self.fixture()
        run = task['branch_run']
        run['authorization']['contract']['plan']['items'].append({'id': 'other', 'acceptance_criteria': ['other scope']})
        for ref in ('unknown:1', 'revision-1:0', 'revision-1:2', 'other:1'):
            with self.subTest(ref=ref):
                item['review_repair']['defects'][0]['criterion'] = ref
                with self.assertRaises(disagreement.SavedRepairError) as error:
                    disagreement.pending(task, item)
                classified = route_health.classify(error.exception)
                self.assertEqual(classified['category'], 'local_controller')
                self.assertFalse(classified['retry']); self.assertFalse(classified['quality_impact'])
                task.update(error_code=error.exception.code, status='error', active_role='worker')
                self.assertFalse(continuation_policy.implementation_handoff(task, item))
        item['review_repair']['defects'][0]['criterion'] = 'revision-1:1'
        run['amendments'][0]['requirement_refs'][0]['criterion'] = 'forged'
        with self.assertRaises(disagreement.SavedRepairError): disagreement.pending(task, item)

    def test_duplicate_text_mapping_cannot_expand_current_repair_scope(self):
        task, _, _, item = self.fixture()
        run = task['branch_run']
        run['authorization']['contract']['plan']['items'].append({'id': 'other', 'acceptance_criteria': ['exact values']})
        run['amendments'][0]['requirement_refs'] = repair_scope.select(run, ['one:1', 'other:1'])
        with self.assertRaises(disagreement.SavedRepairError): disagreement.pending(task, item)
        item['review_repair']['requirement_refs'] = repair_scope.select(run, ['one:1', 'other:1'])
        disagreement.pending(task, item)

    def legacy_failure(self):
        task, engine, runtime, item = self.fixture()
        reason = "Defect criterion must match a supplied acceptance criterion: ['one:1']"
        task['events'] = [{'id': 10, 'kind': 'worker_recovery', 'time': '2026-09-18T04:02:43', 'run_id': 'run',
                           'detail': {'item_id': item['id'], 'from': 'worker', 'reason': reason}}]
        task['request_metrics'] = [{'id': 'request', 'model': 'worker', 'role': 'worker', 'purpose': 'work',
                                    'run_id': 'run', 'branch_item_id': item['id'], 'requested_at': '2026-09-18T04:02:42',
                                    'status': 'failed', 'dispatched': False, 'error_code': None, 'failure_category': 'invalid_response'}]
        task['branch_run']['implementation_recovery'] = {'attempts': 1, 'failed_models': ['worker']}
        task['route'] = {'recovery': {'worker': {'from': 'worker', 'reason': reason}}}
        task['usage'] = {'worker': {'tokens': 123}}
        runtime.failed_models = {'worker'}
        return task, engine, runtime

    def test_legacy_local_exclusion_is_reclassified_once_without_erasing_history(self):
        task, engine, runtime = self.legacy_failure()
        before = copy.deepcopy(task)
        engine._request = Mock(return_value={'content': 'continue saved repair'})
        response = Engine._request_routed(engine, runtime, [], [], 'worker', config_override={})
        self.assertEqual(response, {'content': 'continue saved repair'})
        engine._request.assert_called_once()
        recovery = task['branch_run']['implementation_recovery']
        self.assertEqual(recovery['failed_models'], [])
        self.assertEqual(runtime.failed_models, set())
        self.assertEqual(recovery['attempts'], 1)
        self.assertEqual(recovery['reclassified_failures'][0]['request_ids'], ['request'])
        self.assertEqual(task['request_metrics'][0]['failure_category'], 'local_controller')
        self.assertEqual(task['events'][0], before['events'][0])
        self.assertEqual(task['usage'], before['usage'])
        self.assertEqual(task['branch_run']['dispute_ledger'], before['branch_run']['dispute_ledger'])
        self.assertNotIn('worker', task['route']['recovery'])
        engine.store.save.reset_mock()
        runtime.task = json.loads(json.dumps(task))
        restore_local_repair_routes(engine, runtime)
        engine.store.save.assert_not_called()

    def test_real_or_uncertain_failures_keep_exclusion(self):
        for change in ({'dispatched': True}, {'reservation': {}}, {'error_code': 'http_503'},
                       {'branch_item_id': 'other'}, {'run_id': 'other'}, {'status': 'responded'}):
            with self.subTest(change=change):
                task, engine, runtime = self.legacy_failure()
                task['request_metrics'][0].update(change)
                restore_local_repair_routes(engine, runtime)
                self.assertEqual(task['branch_run']['implementation_recovery']['failed_models'], ['worker'])
                engine.store.save.assert_not_called()
        task, engine, runtime = self.legacy_failure()
        other = copy.deepcopy(task['events'][0]); other['detail']['reason'] = 'Repeated evidence'
        task['events'].append(other)
        restore_local_repair_routes(engine, runtime)
        self.assertEqual(task['branch_run']['implementation_recovery']['failed_models'], ['worker'])
        engine.store.save.assert_not_called()


    def test_resume_restores_eligible_routes_before_replaying_saved_wait(self):
        task, engine, runtime = self.legacy_failure()
        task.update(status='running', retry_wait_enabled=True, route_resume_on_start=True,
                    route_wait={'retry_at': 5000},
                    route_unavailable={'retry_at': 5000, 'can_wait': True, 'scope': 'provider'})
        runtime.interrupt_request = SimpleNamespace(is_set=lambda: False)
        runtime.route_wait_started_at = 1000
        engine.wait_for_route = Mock(side_effect=AssertionError('Replayed stale route wait'))
        def continue_work(rt):
            self.assertEqual(rt.task['branch_run']['implementation_recovery']['failed_models'], [])
            self.assertFalse(rt.task['retry_wait_enabled'])
            self.assertNotIn('route_unavailable', rt.task)
            rt.task['status'] = 'awaiting_reply'
        engine._run_until_pause = Mock(side_effect=continue_work)
        Engine._run_with_wait(engine, runtime)
        engine.wait_for_route.assert_not_called()
        engine._run_until_pause.assert_called_once_with(runtime)
        self.assertIsNone(task['route_wait'])
        self.assertIsNone(runtime.route_wait_started_at)

    def test_resume_keeps_provider_wait_without_proven_local_exclusion(self):
        task, engine, runtime = self.legacy_failure()
        task['request_metrics'][0]['dispatched'] = True
        wait = {'retry_at': 5000, 'can_wait': True, 'scope': 'provider'}
        task.update(status='running', retry_wait_enabled=True, route_unavailable=wait)
        runtime.interrupt_request = SimpleNamespace(is_set=lambda: False)
        order = []
        def waiting(rt):
            self.assertEqual(rt.task['route_unavailable'], wait)
            order.append('wait')
        def proceed(rt):
            self.assertEqual(order, ['wait'])
            rt.task['status'] = 'awaiting_reply'
        engine.wait_for_route = Mock(side_effect=waiting)
        engine._run_until_pause = Mock(side_effect=proceed)
        Engine._run_with_wait(engine, runtime)
        engine.wait_for_route.assert_called_once_with(runtime)
        self.assertEqual(task['branch_run']['implementation_recovery']['failed_models'], ['worker'])
