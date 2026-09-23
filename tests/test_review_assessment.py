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

    This supplies known fixture evidence, not a model-quality oracle. Explicit
    assessments and mixed batches pass through without rewriting their meaning.
    """
    message = copy.deepcopy(message)
    calls = message.get('tool_calls', [])
    # Mixed batches may deliberately exercise cancellation or invalid decisions.
    # Do not turn them into successful review fixtures before dispatch can run.
    if len(calls) != 1:
        return message
    for call in calls:
        if call['function']['name'] not in {'review_decision', 'final_review_decision'}:
            continue
        result = json.loads(call['function']['arguments'])
        if result.get('decision') != 'APPROVE' or 'review_assessment' in result:
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
    def command_packet(self):
        criteria = ['npm run check passes with zero diagnostics', 'npm run build completes without errors',
                    'npm run verify outputs result PASS with all assertions satisfied']
        packet = {'diff': '+return max(lower, min(value, upper))',
                  'checks': [{'candidate_id': 'candidate', 'command': ['npm', 'run', name], 'record': {
                      'command': ['npm', 'run', name], 'directory': '.', 'passed': True, 'exit_code': 0,
                      'output': 'PASS' if name == 'verify' else '0 diagnostics'}} for name in ('check', 'build', 'verify')]}
        return criteria, packet

    def test_command_results_approve_from_exact_receipts_while_regressions_still_need_code(self):
        criteria, packet = self.command_packet()
        state = review.prepare('candidate', packet, criteria)
        result = self.approval(); result['review_assessment'] = assessment(criteria)
        for key in criteria:
            source, = state['criterion_checks'][key]
            result['review_assessment']['criteria'][key] = {
                'reason': 'The captured command completed successfully with the specified result.',
                'citations': [review.read(state, source)['citation']]}
        review.validate(state, result)
        review.retained(result, 'candidate')
        result['review_assessment']['regressions']['citations'] = [review.read(state, 'checks')['citation']]
        with self.assertRaisesRegex(review.EvidenceError, 'Regression assessment needs code'):
            review.validate(state, result)

    def test_command_claim_rejects_unrelated_check_stale_excerpt_and_mixed_behavior(self):
        criteria, packet = self.command_packet()
        state = review.prepare('candidate', packet, criteria)
        result = self.approval(); result['review_assessment'] = assessment(criteria)
        for key in criteria:
            result['review_assessment']['criteria'][key]['citations'] = [review.read(state, state['criterion_checks'][key][0])['citation']]
        wrong = copy.deepcopy(result)
        wrong['review_assessment']['criteria'][criteria[0]] = wrong['review_assessment']['criteria'][criteria[1]]
        with self.assertRaisesRegex(review.EvidenceError, 'matching current check receipt'):
            review.validate(state, wrong)
        newer = review.prepare('new-candidate', packet, criteria)
        with self.assertRaises(review.EvidenceError):
            review.validate(newer, result)
        for key in ('npm run check passes and the menu looks correct', 'Menu works when npm run build completes without errors',
                    'npm run check passes with no security vulnerabilities', 'npm run other passes'):
            self.assertFalse(review.prepare('candidate', packet, [key])['criterion_checks'])
        for field, value in (('passed', False), ('exit_code', 1), ('reason', 'cancelled')):
            changed = copy.deepcopy(packet)
            for row in changed['checks']: row['record'][field] = value
            self.assertFalse(review.prepare('candidate', changed, criteria)['criterion_checks'])

    def test_command_contract_refresh_preserves_old_reads_and_maps_final_requirement_ids(self):
        criteria, packet = self.command_packet()
        # Check evidence from a repaired legacy criterion uses the same reader
        # and provenance contract without changing the approved required list.
        packet['repair_checks'] = [packet['checks'].pop()]
        state = review.prepare('candidate', packet, criteria)
        self.assertEqual(set(state['criterion_checks']), set(criteria))
        self.assertIn('npm', state['sources']['checks']['content'])
        citation = review.read(state, 'diff')['citation']
        state.pop('criterion_checks')  # older saved review, including a handoff
        review.refresh_check_claims(state, packet)
        before = copy.deepcopy(state)
        review.refresh_check_claims(state, packet)
        self.assertEqual(state, before)
        self.assertIsNotNone(review.cited_excerpt(state, citation))
        packet['requirements'] = [{'id': 'SEo-7:1', 'criterion': criteria[0]}]
        final = review.prepare('final', packet, ['SEo-7:1'])
        self.assertEqual(list(final['criterion_checks']), ['SEo-7:1'])

    def state(self):
        return review.prepare('candidate', {'diff': '+return max(lower, min(value, upper))',
                                            'checks': [{'passed': True}]}, ['requested_change'])

    def approval(self):
        return {'decision': 'APPROVE', 'feedback': 'The implementation preserves both bounds.',
                'review_assessment': assessment()}

    def test_evidence_reader_lists_pages_searches_and_preserves_citable_source(self):
        state = self.state()
        content = 'a' * 9000 + 'needle: exact source' + 'b' * 9000
        review.add(state, 'long', 'code', content)
        before = copy.deepcopy(state)
        self.assertEqual(review.read(state), review.display(state))
        first = review.read(state, 'long')
        self.assertEqual(first['content'], content[:8000])
        self.assertTrue(first['has_more'])
        second = review.read(state, 'long', offset=first['next_offset'])
        self.assertEqual(second['content'], content[8000:16000])
        found = review.read(state, 'long', search='needle: exact source')
        self.assertIn('needle: exact source', found['content'])
        self.assertEqual(found['evidence_id'], 'long')
        self.assertEqual(found['digest'], state['sources']['long']['digest'])
        self.assertFalse(review.read(state, 'long', search='absent')['found'])
        self.assertEqual({k: v for k, v in state.items() if k != 'excerpts'}, before)
        result = self.approval()
        result['review_assessment'] = assessment(source=found['evidence_id'], quote='needle: exact source')
        review.validate(state, result)

    def test_returned_citations_preserve_unicode_without_retyping_and_survive_restart(self):
        state = self.state()
        content = '1: <meta content="Aircraft’s fuselage — why?">\\n\\t'
        observed = review.observation(state, 'read_file', {'path': 'build/article.html'}, {'content': content})
        reference = observed['citation']
        restored = json.loads(json.dumps(state))
        result = self.approval()
        for claim in [*result['review_assessment']['criteria'].values(), result['review_assessment']['regressions']]:
            claim['citations'] = [reference]
        result['review_assessment']['verification']['citations'] = [review.read(restored, 'checks')['citation']]
        review.validate(restored, result)
        self.assertEqual(result['_review_evidence']['excerpts'][reference['source']]['content'], content)
        self.assertEqual(result['_review_evidence']['scope'], 'candidate')

    def test_returned_citations_cannot_be_forged_moved_or_use_stale_source(self):
        state = self.state()
        reference = review.read(state, 'diff')['citation']
        self.assertIsNotNone(review.cited_excerpt(state, reference))
        for changed in ({**reference, 'excerpt_id': 'invented'}, {**reference, 'source': 'checks'},
                        {**reference, 'quote': 'invented behavior'}):
            self.assertIsNone(review.cited_excerpt(state, changed))
        other = copy.deepcopy(state); other['scope'] = 'different-candidate'
        self.assertIsNone(review.cited_excerpt(other, reference))
        review.add(state, 'diff', 'code', 'changed code')
        self.assertIsNone(review.cited_excerpt(state, reference))
        result = self.approval()
        result['review_assessment']['criteria']['requested_change']['citations'] = [reference]
        with self.assertRaises(review.EvidenceError):
            review.validate(state, result)

    def test_returned_check_reference_cannot_stand_in_for_implementation(self):
        state = self.state(); result = self.approval()
        reference = review.read(state, 'checks')['citation']
        result['review_assessment']['criteria']['requested_change']['citations'] = [reference]
        with self.assertRaisesRegex(review.EvidenceError, 'needs code/document or visual evidence'):
            review.validate(state, result)

    def test_returned_page_reference_includes_only_delivered_content(self):
        state = self.state(); review.add(state, 'long', 'code', 'x' * 8000 + 'unread code')
        reference = review.read(state, 'long')['citation']
        self.assertEqual(review.cited_excerpt(state, reference), 'x' * 8000)
        self.assertNotIn('unread code', review.cited_excerpt(state, reference))

    def test_evidence_reader_cannot_resolve_other_candidates_or_bad_arguments(self):
        state = self.state()
        review.add(state, 'old-source', 'code', 'prior code')
        other = review.prepare('new-candidate', {'diff': '+new code'}, ['requested_change'])
        for source in ('old-source', '../secret', ['diff']):
            self.assertIn('error', review.read(other, source))
        for args in ({'offset': -1}, {'offset': True}, {'offset': 99999}, {'search': ''}, {'search': ['code']}):
            with self.assertRaises(ValueError):
                review.read(other, 'diff', **args)
        self.assertNotIn('prior code', json.dumps(review.read(other)))
        result = self.approval()
        result['review_assessment'] = assessment(source='diff', quote='prior code', checks=False)
        with self.assertRaises(ValueError):
            review.validate(other, result)

    def test_evidence_reader_is_only_offered_with_review_contract(self):
        from cheapos.tools import REVIEW_TOOLS, WORKER_TOOLS
        before = copy.deepcopy(REVIEW_TOOLS)
        tools = review.tools_with_contract(REVIEW_TOOLS, self.state())
        self.assertIn('read_review_evidence', [t['function']['name'] for t in tools])
        self.assertNotIn('read_review_evidence', [t['function']['name'] for t in WORKER_TOOLS])
        self.assertEqual(REVIEW_TOOLS, before)

    def test_fixture_adapter_preserves_mixed_batches_and_explicit_assessments(self):
        def call(name, args):
            return {'id': name, 'function': {'name': name, 'arguments': json.dumps(args)}}
        approval = call('review_decision', {'decision': 'APPROVE', 'feedback': 'Ignore cancellation'})
        messages = [{'role': 'system', 'content': 'Review'},
                    {'role': 'user', 'content': json.dumps({'review_evidence': {'criteria': ['requested_change'], 'sources': []}})}]
        batch = {'tool_calls': [call('read_url', {'url': 'https://example.org/docs'}), approval]}
        before = copy.deepcopy(batch)
        self.assertEqual(fixture_review_call(batch, messages), before)
        explicit = {'tool_calls': [call('review_decision', {
            'decision': 'APPROVE', 'feedback': 'Unsupported', 'review_assessment': {}})]}
        before = copy.deepcopy(explicit)
        self.assertEqual(fixture_review_call(explicit, messages), before)
        state = self.state()
        packet = {'diff': state['sources']['diff']['content'], 'checks': [{'passed': True}],
                  'review_evidence': review.display(state)}
        single = {'tool_calls': [approval]}
        before = copy.deepcopy(single)
        upgraded = fixture_review_call(single, [{'role': 'system', 'content': 'Review'},
                                               {'role': 'user', 'content': json.dumps(packet)}])
        self.assertEqual(single, before)  # Reused fixture responses remain independent.
        review.validate(state, json.loads(upgraded['tool_calls'][0]['function']['arguments']))

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

    def test_check_output_citations_match_decoded_json_values(self):
        output = 'Ran 11 tests in 0.020s\n\nOK\nquoted "value" and \\path'
        state = review.prepare('candidate', {'diff': '+return max(lower, min(value, upper))',
            'checks': [{'record': {'output': output, 'exit_code': 0, 'passed': True}}]}, ['requested_change'])
        result = self.approval()
        for quote in ('Ran 11 tests in 0.020s\n\nOK', 'quoted "value" and \\path'):
            with self.subTest(quote=quote):
                result['review_assessment']['verification']['citations'][0]['quote'] = quote
                review.validate(state, result)
                review.retained(result, 'candidate')
                excerpt = result['_review_evidence']['excerpts']['checks']
                self.assertEqual(excerpt['content'], quote)
                self.assertEqual(excerpt['source_digest'], state['sources']['checks']['digest'])
        # Formatting tolerance cannot invent output, splice fields or strip diff markers.
        for quote in ('Ran 12 tests in 0.020s\n\nOK', 'OK\nexit_code 0', '"exit_code": 1'):
            result['review_assessment']['verification']['citations'][0]['quote'] = quote
            with self.subTest(quote=quote), self.assertRaises(ValueError): review.validate(state, result)
        result['review_assessment']['verification']['citations'][0]['quote'] = 'Ran 11 tests in 0.020s\n\nOK'
        result['review_assessment']['criteria']['requested_change']['citations'][0].update(
            source='diff', quote='return max(lower,\nmin(value, upper))')
        with self.assertRaises(ValueError): review.validate(state, result)

    def test_planner_must_supply_observable_acceptance_criteria(self):
        value = {'status': 'plan', 'plan': {'items': [{'id': 'one', 'title': 'Fix', 'instructions': 'Fix', 'required_checks': []}], 'limits': {}}, 'clarification': ''}
        message = {'tool_calls': [{'function': {'name': 'propose_branch_plan', 'arguments': json.dumps(value)}}]}
        with self.assertRaisesRegex(branch_planner.PlanningResponseError, 'acceptance_criteria'):
            branch_planner._parse(message, {})

    def test_numbered_code_quotes_preserve_content_and_survive_saved_review(self):
        state = self.state()
        observed = review.observation(state, 'read_file', {'path': 'bounds.py'}, {
            'path': 'bounds.py', 'content': '116: def clamp(value):\n117:     return max(lower, min(value, upper))'})
        source = observed['evidence_id']
        code = 'def clamp(value):\n    return max(lower, min(value, upper))'
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                saved = json.loads(json.dumps(state))
                if legacy:
                    saved['sources'][source].pop('format'); saved['sources'][source].pop('path')
                result = self.approval(); result['review_assessment'] = assessment(source=source, quote=code)
                review.validate(saved, result)
                review.retained(result, 'candidate')
                self.assertEqual(result['_review_evidence']['excerpts'][source]['content'], code)
                self.assertEqual(result['_review_evidence']['excerpts'][source]['source_digest'], state['sources'][source]['digest'])
                for fake in (code.replace('    return', 'return'), code.replace('max', 'min')):
                    result['review_assessment']['criteria']['requested_change']['citations'][0]['quote'] = fake
                    with self.assertRaises(review.EvidenceError): review.validate(saved, result)
                    self.assertNotIn('_review_evidence', result)

    def test_diff_quotes_keep_sides_hunks_and_files_separate(self):
        state = self.state()
        diff = ('diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,3 @@\n'
                ' def clamp(value):\n-    return value\n+    value = max(lower, value)\n+    return min(value, upper)\n'
                '@@ -10 +11 @@\n tail()\ndiff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n other()\n')
        review.add(state, 'diff', 'code', diff, format='diff')
        quote = 'def clamp(value):\n    value = max(lower, value)\n    return min(value, upper)'
        for legacy in (False, True):
            if legacy: state['sources']['diff'].pop('format')
            result = self.approval(); result['review_assessment'] = assessment(quote=quote)
            review.validate(state, result)
            for fake in ('return value\n    value = max', 'return min(value, upper)\ntail()', 'tail()\nother()',
                         'value = max(lower, value)\nreturn min(value, upper)'):
                result['review_assessment']['criteria']['requested_change']['citations'][0]['quote'] = fake
                with self.subTest(legacy=legacy, fake=fake), self.assertRaises(review.EvidenceError):
                    review.validate(state, result)
        # Arbitrary source text cannot have a '-' operator or a discontinuous
        # line range silently removed just because a quote would then match.
        for content in ('-one\n-two', '1: one\n3: two'):
            self.assertIsNone(review.matched_quote('read:test', {'kind': 'code', 'content': content}, 'one\ntwo'))

    def test_all_response_errors_reported_with_matching_delivered_sources(self):
        state = self.state()
        observed = review.observation(state, 'read_file', {'path': 'bounds.py'}, {
            'content': '1: def clamp(value):\n2:     return max(lower, min(value, upper))'})
        source = observed['evidence_id']
        result = self.approval(); result['feedback'] = ''
        result['review_assessment']['criteria']['requested_change']['citations'][0].update(
            source='bounds.py:1-2', quote='def clamp(value):\n    return max(lower, min(value, upper))')
        result['review_assessment']['regressions']['reason'] = ''
        result['review_assessment']['verification']['citations'] = [{'source': 'checks', 'quote': 'not delivered'}]
        result['review_assessment']['limitations'] = 'none'
        with self.assertRaises(review.EvidenceError) as caught:
            review.validate(state, result)
        correction = review.feedback(caught.exception, state)
        fields = {issue['field'] for issue in correction['issues']}
        self.assertTrue({'feedback', 'review_assessment.regressions.reason', 'review_assessment.limitations',
                         'review_assessment.verification.citations[0]'}.issubset(fields))
        citation = next(i for i in correction['issues'] if i['field'].endswith('requested_change.citations[0]'))
        self.assertEqual(citation['matching_source_ids'], [source])
        self.assertIn('read only genuinely missing context', correction['next_action'])
        self.assertNotIn('_review_evidence', result)
        # Suggestions are not evidence assignment: the reviewer must correct
        # its claims and cite the current source before a receipt can be issued.
        result = self.approval(); result['review_assessment'] = assessment(source=source,
            quote='def clamp(value):\n    return max(lower, min(value, upper))')
        review.validate(state, result)

    def test_diagnostics_do_not_turn_check_matches_into_implementation_evidence(self):
        state = self.state(); result = self.approval()
        result['review_assessment'] = assessment(source='missing', quote='"passed": true')
        with self.assertRaises(review.EvidenceError) as caught: review.validate(state, result)
        self.assertIn(['checks'], [i.get('matching_source_ids') for i in caught.exception.correction['issues']])
        result['review_assessment'] = assessment(source='checks', quote='"passed": true')
        with self.assertRaisesRegex(review.EvidenceError, 'code/document'): review.validate(state, result)
        self.assertNotIn('_review_evidence', result)

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
