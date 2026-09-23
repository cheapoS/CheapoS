"""Incremental review evidence, in memory; no providers, Git fixtures or waits."""
import copy
import json
import unittest

from cheapos import review_assessment as evidence, review_progress as progress


class ProgressTests(unittest.TestCase):
    def state(self):
        state = evidence.prepare('candidate', {'diff': '+return value',
            'checks': [{'command': ['npm', 'test'], 'passed': True, 'exit_code': 0}]}, ['Returns the value'])
        progress.bind(state, {'direction': 'Keep exact values'})
        return state

    def fill(self, state):
        for target in progress.targets(state):
            if target == 'limitations':
                progress.record(state, 'candidate', target, limitations=['Static inspection only'])
            else:
                source = 'checks' if target == 'verification' else 'diff'
                ref = evidence.read(state, source)['citation']
                progress.record(state, 'candidate', target, reason='Inspected the supplied evidence and its scope.', citations=[ref])

    def test_recorded_claims_need_explicit_complete_decision_and_revalidation(self):
        state = self.state()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            progress.complete(state, {'use_recorded_assessment': True})
        self.fill(state)
        state = json.loads(json.dumps(state))
        self.assertTrue(progress.display(state)['ready_for_final_decision'])
        self.assertFalse(progress.display(state)['approved'])
        result = {'decision': 'APPROVE', 'feedback': 'Inspected source and checks.', 'use_recorded_assessment': True}
        progress.complete(state, result)
        self.assertNotIn('_review_evidence', result)
        evidence.validate(state, result)
        evidence.retained(result, 'candidate')
        self.assertEqual(result['review_assessment']['limitations'], ['Static inspection only'])
        # Changed evidence cannot silently reuse the saved excerpt.
        state['sources']['diff']['content'] = '+return other'
        state['sources']['diff']['digest'] = evidence.digest('+return other')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            progress.complete(state, {'use_recorded_assessment': True})
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate(state, result)

    def test_commands_do_not_prove_behavior_and_stale_targets_cannot_record(self):
        state = self.state(); ref = evidence.read(state, 'checks')['citation']
        for target in ('criterion:1', 'regressions'):
            with self.subTest(target=target), self.assertRaises(evidence.EvidenceError):
                progress.record(state, 'candidate', target, reason='Tests passed.', citations=[ref])
        with self.assertRaisesRegex(ValueError, 'stale'):
            progress.record(state, 'older', 'verification', reason='Passed', citations=[ref])
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            progress.record(state, 'candidate', 'criterion:99', reason='Passed', citations=[ref])
        self.assertEqual(progress.display(state)['recorded_assessments'], {})

    def test_changed_scope_directions_or_check_contract_invalidates_progress(self):
        original = self.state(); self.fill(original)
        for field, value in [('scope', 'new'), ('criteria', ['Different behavior']), ('criterion_checks', {'Returns the value': ['check:new']})]:
            state = copy.deepcopy(original); state[field] = value
            progress.bind(state, {'direction': 'Keep exact values'})
            self.assertFalse(progress.display(state)['recorded_assessments'])
        progress.bind(original, {'direction': 'Use integers instead'})
        self.assertFalse(progress.display(original)['recorded_assessments'])

    def test_ambiguous_final_submission_cannot_hide_disagreement(self):
        for has_progress in (False, True):
            state = self.state()
            if has_progress: self.fill(state)
            before = copy.deepcopy(state)
            with self.subTest(has_progress=has_progress), self.assertRaisesRegex(ValueError, 'not both.*omit use_recorded_assessment'):
                progress.complete(state, {'use_recorded_assessment': True, 'review_assessment': {}})
            self.assertEqual(state, before)
        result = {'decision': 'APPROVE', 'feedback': 'No confirmation'}
        progress.complete(state, result)
        with self.assertRaises(evidence.EvidenceError): evidence.validate(state, result)

    def test_labeled_command_claims_match_only_their_actual_receipts(self):
        packet = {'checks': [{'command': ['npm', 'test'], 'passed': True, 'exit_code': 0}]}
        names = ['Components tests passed (npm test)', 'Ledger passed structural validation (npm test)']
        state = evidence.prepare('candidate', packet, names)
        self.assertEqual(set(state['criterion_checks']), set(names))
        progress.bind(state, {})
        for i, name in enumerate(names):
            ref = evidence.read(state, state['criterion_checks'][name][0])['citation']
            progress.record(state, 'candidate', f'criterion:{i+1}', reason='The matching captured command exited successfully.', citations=[ref])
        for name in ['Components tests passed (npm test) and the UI works',
                     'UI works and tests passed (npm test)']:
            self.assertFalse(evidence.prepare('candidate', packet, [name])['criterion_checks'])
        missing = evidence.prepare('candidate', packet, ['Ledger passed structural validation (node check-ledger.mjs)'])
        self.assertEqual(list(missing['criterion_checks'].values()), [[]])
        progress.bind(missing, {})
        with self.assertRaises(evidence.EvidenceError):
            progress.record(missing, 'candidate', 'criterion:1', reason='Other tests passed.',
                            citations=[evidence.read(missing, 'checks')['citation']])
        packet['checks'][0]['passed'] = False
        self.assertTrue(all(not sources for sources in evidence.prepare('candidate', packet, names)['criterion_checks'].values()))

    def test_missing_source_prefix_resolves_only_one_exact_current_source(self):
        state = self.state()
        result = evidence.observation(state, 'read_file', {'path': 'app.py'}, {'path': 'app.py', 'content': 'return value'})
        source = result['evidence_id']; suffix = source.split(':')[-1]
        recovered = evidence.read(state, suffix)
        self.assertEqual(recovered['evidence_id'], source)
        self.assertEqual(evidence.cited_excerpt(state, recovered['citation']), 'return value')
        self.assertIn('error', evidence.read(state, suffix[:-1]))
        evidence.add(state, 'check:' + suffix, 'check', 'unrelated receipt')
        self.assertIn('error', evidence.read(state, suffix))
