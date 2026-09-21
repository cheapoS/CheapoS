"""Evidence-gate regressions: pure/in-memory, no Git, network or model calls."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import review_assessment as review, branch_final, branch_planner


def assessment(criteria=('requested_change',), *, source='diff', quote='return max(lower, min(value, upper))', checks=True):
    implementation = {'reason': 'The lower bound is enforced without removing the upper bound.',
                      'citations': [{'source': source, 'quote': quote}]}
    verification = {'reason': 'The saved check passed; inspect its assertions to establish behavioral coverage.',
                    'citations': [{'source': 'checks', 'quote': '"passed": true'}]} if checks else copy.deepcopy(implementation)
    return {'criteria': {key: copy.deepcopy(implementation) for key in criteria},
            'regressions': copy.deepcopy(implementation), 'verification': verification,
            'limitations': ['No rendered UI behavior was verified by this check.']}


def fixture_review_call(message, messages):
    """Upgrade successful scripted fixture replies to the current wire contract.

    This supplies known fixture evidence, not a model-quality oracle. Negative
    approval tests construct their responses explicitly and never use this helper.
    """
    for call in message.get('tool_calls', []):
        if call['function']['name'] not in {'review_decision', 'final_review_decision'}:
            continue
        result = json.loads(call['function']['arguments'])
        if result.get('decision') != 'APPROVE':
            continue
        packet = json.loads(messages[1]['content'])
        contract = packet.get('review_evidence')
        if not contract:
            continue
        partial = not packet.get('criteria_ids') and 'chunk' in packet
        state = review.prepare('fixture', packet, contract['criteria'], partial=partial)
        for value in contract['sources']:
            if value.get('content'):
                review.add(state, value['id'], value['kind'], value['content'])
        sources = state['sources']
        source = next((key for key, value in sources.items() if value['kind'] == 'code'), None)
        if source is None and partial:
            source = 'packet'
        assert source is not None, 'Fixture must deliver implementation evidence before approval'
        quote = sources[source]['content']
        claim = {'reason': 'Inspected the supplied fixture implementation against its requested behavior.',
                 'citations': [{'source': source, 'quote': quote}]}
        check_source = next((key for key, value in sources.items() if value['kind'] == 'check'), source)
        result['review_assessment'] = {'criteria': {key: copy.deepcopy(claim) for key in contract['criteria']},
            'regressions': copy.deepcopy(claim),
            'verification': {'reason': 'The fixture check records exercise its declared behavior.',
                'citations': [{'source': check_source, 'quote': sources[check_source]['content']}]},
            'limitations': []}
        call['function']['arguments'] = json.dumps(result)
    return message


class ReviewAssessmentTests(unittest.TestCase):
    def state(self):
        return review.prepare('candidate', {'diff': '+return max(lower, min(value, upper))',
                                            'checks': [{'passed': True}]}, ['requested_change'])

    def approval(self):
        return {'decision': 'APPROVE', 'feedback': 'The implementation preserves both bounds.',
                'review_assessment': assessment()}

    def test_real_citations_are_bound_to_candidate_and_assessment(self):
        state = self.state(); result = self.approval()
        review.validate(state, result)
        review.retained(result, 'candidate')
        self.assertIn('return max', result['_review_evidence']['excerpts']['diff']['content'])
        self.assertIn('No rendered UI behavior', review.visible_feedback(result))
        with self.assertRaises(ValueError): review.retained(result, 'different-candidate')
        result['review_assessment']['limitations'] = []
        with self.assertRaises(ValueError): review.retained(result, 'candidate')

    def test_empty_fictional_check_only_and_conflicting_approvals_fail(self):
        variants = []
        empty = self.approval(); empty['feedback'] = ''; variants.append(empty)
        missing = self.approval(); missing.pop('review_assessment'); variants.append(missing)
        fake = self.approval(); fake['review_assessment']['criteria']['requested_change']['citations'][0]['quote'] = 'assert all_behavior_is_correct'; variants.append(fake)
        unchecked = self.approval(); unchecked['review_assessment'] = assessment(source='checks', quote='"passed": true'); variants.append(unchecked)
        omitted = self.approval(); omitted['review_assessment']['criteria'] = {}; variants.append(omitted)
        conflict = self.approval(); conflict['defects'] = [{'summary': 'Still broken'}]; variants.append(conflict)
        for result in variants:
            with self.subTest(result=result), self.assertRaises(ValueError): review.validate(self.state(), result)
        # Rejection and requests for targeted verification remain possible.
        review.validate(self.state(), {'decision': 'REQUEST_TESTS', 'feedback': 'Exercise both bounds.'})

    def test_reads_register_actual_content_not_tool_errors_or_simulations(self):
        state = self.state()
        for name, result in [('read_file', {'content': 'def caller(): pass'}),
                             ('get_diff', '+def caller(): pass'),
                             ('read_check_output', {'output': 'Ran 3 tests: OK'}),
                             ('inspect_image', {'status': 'success', 'analysis': 'Label is clipped.'})]:
            observed = review.observation(state, name, {'path': 'file'}, result)
            self.assertIn(observed['evidence_id'], state['sources'])
        for result in ({'error': 'not found'}, {'status': 'mock', 'analysis': 'simulated'}, {'status': 'fallback', 'analysis': 'unavailable'}):
            self.assertNotIn('evidence_id', review.observation(state, 'inspect_image', {}, result))
        svg = review.observation(state, 'inspect_image', {}, {'status': 'success', 'format': 'svg', 'analysis': '<svg/>'})
        self.assertEqual(state['sources'][svg['evidence_id']]['kind'], 'code')

    def test_synthesis_gets_validated_source_excerpts_not_only_prior_approval(self):
        state = self.state(); result = self.approval(); review.validate(state, result)
        combined = review.prepare('final', {'coverage': [{'review': result}], 'checks': [{'passed': True}]}, ['one:1'])
        source = next(s for s, value in combined['sources'].items() if value['kind'] == 'code')
        final = self.approval(); final['review_assessment'] = assessment(['one:1'], source=source)
        review.validate(combined, final)
        self.assertIn('return max', json.dumps(review.display(combined)))
        claim_only = review.prepare('final', {'coverage': [{'review': {'decision': 'APPROVE'}}]}, ['one:1'])
        with self.assertRaises(ValueError): review.validate(claim_only, final)

    def test_synthesis_does_not_repeat_source_excerpts_in_transmitted_receipts(self):
        state = self.state(); result = self.approval(); review.validate(state, result)
        packet = {'coverage': [{'review': result}], 'checks': [{'passed': True}]}
        combined = review.prepare('final', packet, ['one:1'])
        packet['review_evidence'] = review.display(combined)
        wire = review.packet_for_model(packet)
        self.assertIn('_review_evidence', packet['coverage'][0]['review'])
        self.assertNotIn('_review_evidence', wire['coverage'][0]['review'])
        self.assertIn('Verification limitations', wire['coverage'][0]['review']['feedback'])
        self.assertEqual(json.dumps(wire).count('return max'), 1)

    def test_repeated_unsupported_approval_changes_reviewer_without_new_authority(self):
        task = {'providers': {'reviewer': {'model': 'first'}}, 'limits': {'dollars': 0}, 'checks': [{'passed': True}]}
        checkpoint = {'messages': [{'role': 'tool', 'content': 'existing evidence'}]}
        runtime = SimpleNamespace(task=task, failed_models=set(), guard=Mock(), stop=SimpleNamespace(is_set=lambda: False))
        engine = SimpleNamespace(store=SimpleNamespace(save=Mock()), event=Mock())
        before = copy.deepcopy(task)
        with patch('cheapos.model_pool.automatic', return_value=True), patch('cheapos.routing.select_remote') as select:
            self.assertFalse(review.handoff(engine, runtime, checkpoint))
            self.assertFalse(review.handoff(engine, runtime, checkpoint))
            self.assertTrue(review.handoff(engine, runtime, checkpoint))
            select.assert_called_once_with(engine, runtime, 'reviewer', replace=True)
        self.assertEqual(task, before)
        self.assertEqual(runtime.failed_models, {'first'})
        self.assertEqual(checkpoint['messages'], [])

    def test_pinned_reviewer_cannot_loop_or_switch_without_authority(self):
        task = {'providers': {'reviewer': {'model': 'pinned'}}}
        checkpoint = {'evidence_failures': {'pinned': 3}, 'messages': ['saved']}
        runtime = SimpleNamespace(task=task, failed_models=set())
        engine = SimpleNamespace(store=SimpleNamespace(save=Mock()))
        with patch('cheapos.model_pool.automatic', return_value=False), patch('cheapos.routing.select_remote') as select:
            with self.assertRaisesRegex(ValueError, 'Automatic replacement is not authorized'):
                review.handoff(engine, runtime, checkpoint, rejected=False)
        select.assert_not_called()
        self.assertEqual(checkpoint['messages'], ['saved'])

    def test_check_json_order_does_not_reject_the_same_delivered_facts(self):
        state = self.state()
        state['sources']['checks']['content'] = '{"passed": true, "exit_code": 0}'
        result = self.approval()
        result['review_assessment']['verification']['citations'][0]['quote'] = '{"exit_code":0,"passed":true}'
        review.validate(state, result)
        result['review_assessment']['verification']['citations'][0]['quote'] = '{"exit_code":1,"passed":true}'
        with self.assertRaises(ValueError): review.validate(state, result)

    def test_planner_must_supply_observable_acceptance_criteria(self):
        value = {'status': 'plan', 'plan': {'items': [{'id': 'one', 'title': 'Fix', 'instructions': 'Fix', 'required_checks': []}], 'limits': {}}, 'clarification': ''}
        message = {'tool_calls': [{'function': {'name': 'propose_branch_plan', 'arguments': json.dumps(value)}}]}
        with self.assertRaisesRegex(branch_planner.PlanningResponseError, 'acceptance_criteria'):
            branch_planner._parse(message, {})

    def test_reviewer_completion_alone_does_not_improve_quality_ranking(self):
        from cheapos.model_pool import FreeModelPool
        pool = FreeModelPool.__new__(FreeModelPool)
        pool.fresh_probe = Mock(return_value=False)
        pool.observation = Mock(return_value={'role_evidence': {'reviewer': {'samples': 10, 'reviews_completed': 10, 'completed': 10}}})
        completed = pool.rank('route', {'id': 'reviewer'}, 'reviewer', connection_revision='revision')
        pool.observation.return_value = {'role_evidence': {'reviewer': {}}}
        self.assertEqual(completed, pool.rank('route', {'id': 'reviewer'}, 'reviewer', connection_revision='revision'))
        pool.observation.return_value = {'role_evidence': {'reviewer': {'independently_validated': 1}}}
        self.assertLess(pool.rank('route', {'id': 'reviewer'}, 'reviewer', connection_revision='revision'), completed)


if __name__ == '__main__':
    unittest.main()
