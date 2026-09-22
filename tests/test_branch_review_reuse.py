"""Pure receipt/completion cases: no Git, subprocesses, waits or live models."""
import copy
import threading
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_final as final, branch_review_reuse as reuse, branch_evidence as evidence
from cheapos import branch_update, review_assessment
from tests.test_review_assessment import assessment, fixture_review_call


COMMAND = ['python3', '-m', 'unittest']
CODE = '+return max(lower, min(value, upper))'


def sealed(value, digest=final._hash):
    value = copy.deepcopy(value); value.pop('id', None)
    return {**value, 'id': digest(value)}


class ReviewReuseTests(unittest.TestCase):
    def fixture(self):
        plan = {'items': [{'id': 'one', 'acceptance_criteria': ['Both bounds work']}], 'final_checks': [COMMAND]}
        row = {'id': 'one:1', 'item_id': 'one', 'title': 'Clamp', 'instructions': 'Preserve both bounds', 'criterion': 'Both bounds work'}
        manifest = sealed({'version': 2, 'run_id': 'run', 'base_sha': 'base', 'feature_ref': 'feature', 'target_ref': 'main',
            'feature_tip': 'approved-tip', 'feature_tree': 'approved-tree', 'target_tip': 'target', 'review_base_sha': 'base',
            'plan_revision': 1, 'plan_digest': 'plan', 'plan_content_digest': final._hash(plan),
            'commits': [{'item_id': 'one', 'new_tip': 'approved-tip'}], 'requirements': [row],
            'chunks': [{'id': 'diff:1', 'kind': 'diff', 'content': CODE, 'digest': final._hash(CODE)}], 'diff': CODE, 'files': [{'path': 'clamp.py'}]})
        current = self.candidate(manifest, 'inputs')
        record = self.check('inputs')
        checks = evidence.current_checks(current, [record])
        task = {'id': 'task', 'review_contract_version': 1, 'checks': [record], 'prompt': 'Fix both bounds',
            'providers': {'worker': {'model': 'worker'}, 'reviewer': {'model': 'reviewer'}},
            'usage': {'cost': 0}, 'limits': {'dollars': 0}, 'execution': {'mode': 'remote'}, 'route': {'base_url': 'gateway'},
            'branch_run': {'id': 'run', 'plan': plan, 'plan_revision': 1, 'expected_feature_tip': 'approved-tip',
                          'items': [{'id': 'one', 'status': 'committed', 'commit': 'approved-tip'}],
                          'workspace_mapping': {'source': 'source'}, 'target_update_history': []}}
        basis = {'version': 1, 'manifest': manifest, 'candidate': current, 'checks': checks,
            'reviews': [self.decision(manifest, checks, [])], 'review': self.decision(manifest, checks, ['one:1']),
            'worker_model': 'worker', 'reviewer_model': 'reviewer', 'integration_blocker': None,
            'review_input_digest': reuse.input_digest(task)}
        basis = sealed(basis); task['branch_run']['previous_readiness'] = [basis]
        engine = SimpleNamespace(lock=threading.RLock(), store=SimpleNamespace(save=Mock()), event=Mock(), request=Mock(), checks=Mock(),
                                 parse_call=lambda c: (c['function']['name'], json.loads(c['function']['arguments'])))
        engine.request.side_effect = self.respond
        runtime = SimpleNamespace(task=task, guard=Mock(), stop=SimpleNamespace(is_set=lambda: False))
        return task, engine, runtime, manifest, current, basis

    def candidate(self, manifest, inputs):
        return sealed({'context': {'run_id': 'run', 'plan_revision': manifest['plan_revision'], 'item_id': 'final',
                                 'item_revision': 1, 'feature_parent': manifest['feature_tip']},
            'workspace': 'workspace', 'review_contract_version': 1,
            'criteria': [r['id'] for r in manifest['requirements']], 'check_specifications': [COMMAND],
            'checks': [{'command': COMMAND, 'verification_identity': inputs}]}, evidence._digest)

    def check(self, inputs):
        return {'command': COMMAND, 'passed': True, 'exit_code': 0, 'verification_identity': inputs,
                'input_identity': inputs, 'output': 'Ran 2 tests\nOK'}

    def decision(self, manifest, checks, criteria):
        scope = final._hash({'manifest_id': manifest['id'], 'chunk_ids': ['diff:1'], 'criteria_ids': criteria, 'page': None})
        state = review_assessment.prepare(scope, {'diff': CODE, 'checks': checks}, criteria, partial=not criteria)
        result = {'decision': 'APPROVE', 'manifest_id': manifest['id'], 'chunk_ids': ['diff:1'], 'criteria_ids': criteria,
                  'feedback': 'Reviewed both bounds.', 'reviewer_model': 'reviewer',
                  'review_assessment': assessment(criteria or ['packet'])}
        review_assessment.validate(state, result)
        return result

    def respond(self, runtime, messages, tools, role, **kw):
        params = tools[0]['function']['parameters']['properties']
        args = {'decision': 'APPROVE', 'manifest_id': params['manifest_id']['enum'][0],
                'chunk_ids': params['chunk_ids'].get('enum', [[]])[0],
                'criteria_ids': params['criteria_ids'].get('enum', [[]])[0], 'feedback': 'Inspected integration impact.'}
        message = {'tool_calls': [{'id': 'decision', 'function': {'name': 'final_review_decision', 'arguments': json.dumps(args)}}]}
        return fixture_review_call(message, messages)

    def update(self, task, manifest):
        new = sealed({**manifest, 'feature_tip': 'merged-tip', 'feature_tree': 'merged-tree',
                      'target_tip': 'incoming', 'review_base_sha': 'incoming'})
        op = {'old_tip': manifest['feature_tip'], 'new_tip': new['feature_tip'], 'tree': new['feature_tree'],
              'target_tip': new['review_base_sha'], 'stage': 'completed', 'approved': True}
        op['digest'] = branch_update.receipt_digest(op)
        task['branch_run']['target_update_history'].append(op)
        task['branch_run']['expected_feature_tip'] = new['feature_tip']
        return new, self.candidate(new, 'new-inputs')

    def run_final(self, task, engine, runtime, manifest, current, delta=CODE):
        def checks(rt, command, **kw):
            record = self.check(current['checks'][0]['verification_identity'])
            task['checks'].append(record)
            return record
        engine.checks.side_effect = checks
        with patch.object(final, 'build_manifest', return_value=manifest), \
             patch.object(evidence, 'candidate', return_value=current), \
             patch.object(reuse, 'diff', return_value=delta), patch.object(final.work, 'source_git', return_value=''):
            result = final.final_check_review(engine, runtime)
            if result['decision'] == 'APPROVE':
                self.assertTrue(final.validate(result['readiness'], task))
            return result

    def test_direction_after_synthesis_redirects_without_false_branch_drift(self):
        from cheapos.engine import OperatorRedirect
        task, engine, runtime, manifest, current, _ = self.fixture()
        task['branch_run'].pop('previous_readiness')
        before_checks = copy.deepcopy(task['checks'])
        review = final.review_paged
        def completed(*args, **kwargs):
            result = review(*args, **kwargs)
            if args[5]:  # Guidance arrives after the final synthesis reply.
                task['steer_guidance'] = 'Check the required styles too.'
                runtime.guard.side_effect = OperatorRedirect('New guidance')
            return result
        with patch.object(final, 'review_paged', side_effect=completed):
            with self.assertRaises(OperatorRedirect):
                self.run_final(task, engine, runtime, manifest, current)
        self.assertNotIn('readiness', task['branch_run'])
        self.assertEqual(task['checks'], before_checks)
        engine.checks.assert_not_called()

    def resolution(self, task, old):
        criteria = ['Preserve both branches', 'No conflict markers remain']
        item = {'id': 'resolve', 'title': 'Resolve conflicts', 'instructions': 'Resolve captured context',
                'acceptance_criteria': criteria}
        task['branch_run']['plan']['items'].append(item)
        new, _ = self.update(task, old)
        new.update(plan_revision=2, plan_digest='updated-plan', plan_content_digest=final._hash(task['branch_run']['plan']))
        candidate = self.candidate(new, 'resolution-inputs')
        candidate.update(criteria=criteria, patch=CODE)
        candidate['context'].update(item_id='resolve', feature_parent=old['feature_tip'])
        candidate = sealed(candidate, evidence._digest)
        checks = evidence.current_checks(candidate, [self.check('resolution-inputs')])
        review = {'decision': 'APPROVE', 'candidate_id': candidate['id'], 'feedback': 'Both branches preserved.',
            'review_assessment': assessment(criteria),
            'integration_review': {'candidate_id': candidate['id'], 'task_tip': old['feature_tip'],
                'target_tip': 'incoming', 'context_digest': 'context', 'candidate_tree': new['feature_tree'],
                'full_patch_digest': evidence._digest(CODE)}}
        proof = review_assessment.prepare(candidate['id'], {'diff': CODE, 'checks': checks}, criteria)
        review_assessment.validate(proof, review)
        outcomes = {c: {'passed': True, 'evidence': 'Inspected both branches.'} for c in criteria}
        receipt_text = evidence.ready_receipt(candidate, checks, review, 'worker', 'reviewer', outcomes)
        receipt = json.loads(receipt_text)
        new['commits'].append({'item_id': 'resolve', 'receipt_id': receipt['id'], 'new_tip': 'resolution-tip', 'tree': new['feature_tree']})
        new['requirements'].extend({'id': f'resolve:{n}', 'item_id': 'resolve', 'title': item['title'],
            'instructions': item['instructions'], 'criterion': c, 'receipt_id': receipt['id']} for n, c in enumerate(criteria, 1))
        task['branch_run']['items'].append({**item, 'status': 'committed', 'commit': 'resolution-tip',
                                           'commit_receipt': {'receipt': receipt_text}})
        task['branch_run']['plan_revision'] = 2
        op = task['branch_run']['target_update_history'][-1]
        op.update(old_tip='resolution-tip', origin='conflict_resolution', resolution_item='resolve', context_digest='context')
        op['digest'] = branch_update.receipt_digest(op)
        new = sealed(new)
        return new, self.candidate(new, 'final-inputs'), receipt

    def test_reviewed_resolution_uses_fresh_final_checks_without_another_model_review(self):
        task, engine, runtime, old, current, basis = self.fixture()
        manifest, current, receipt = self.resolution(task, old)
        result = self.run_final(task, engine, runtime, manifest, current)
        ready = result['readiness']
        self.assertEqual(ready['reuse']['mode'], 'resolved')
        self.assertEqual(ready['review'], receipt['review'])
        self.assertEqual(ready['reuse']['basis_id'], basis['id'])
        self.assertEqual(ready['checks'][0]['record']['input_identity'], 'final-inputs')
        engine.checks.assert_called_once(); engine.request.assert_not_called()

    def test_resolution_receipt_cannot_cover_changed_tree_or_extra_work(self):
        for change in ('tree', 'requirements', 'plan', 'extra_commit', 'missing_review'):
            with self.subTest(change=change):
                task, engine, runtime, old, current, basis = self.fixture()
                manifest, current, receipt = self.resolution(task, old)
                if change == 'tree': manifest['feature_tree'] = 'unreviewed-tree'
                elif change == 'requirements': manifest['requirements'][0]['criterion'] = 'Another feature'
                elif change == 'plan': task['branch_run']['plan']['new_scope'] = True
                elif change == 'extra_commit': manifest['commits'].append({'item_id': 'other'})
                else: task['branch_run']['items'][-1]['commit_receipt']['receipt'] = '{}'
                self.assertIsNone(reuse.prepare(task, sealed(manifest), current,
                    evidence.current_checks(current, [self.check('final-inputs')])))

    def test_legacy_approval_falls_back_to_normal_review_and_records_future_provenance(self):
        task, engine, runtime, manifest, current, basis = self.fixture()
        basis.pop('review_input_digest'); task['branch_run']['previous_readiness'] = [sealed(basis)]
        result = self.run_final(task, engine, runtime, manifest, current)
        self.assertNotIn('reuse', result['readiness'])
        self.assertEqual(result['readiness']['review_input_digest'], reuse.input_digest(task))
        self.assertEqual(engine.request.call_count, 2)

    def test_multiple_updates_preserve_chain_and_old_approvals(self):
        task, engine, runtime, old, current, basis = self.fixture(); manifest, current = self.update(task, old)
        first = self.run_final(task, engine, runtime, manifest, current)['readiness']
        task['branch_run']['previous_readiness'].append(first)
        second_manifest, second_current = self.update(task, manifest)
        second_manifest.update(feature_tip='next-merge', feature_tree='next-tree', target_tip='next-target', review_base_sha='next-target')
        op = task['branch_run']['target_update_history'][-1]
        op.update(new_tip='next-merge', tree='next-tree', target_tip='next-target'); op['digest'] = branch_update.receipt_digest(op)
        second_manifest = sealed(second_manifest); second_current = self.candidate(second_manifest, 'next-inputs')
        second = self.run_final(task, engine, runtime, second_manifest, second_current, '+next integration')['readiness']
        self.assertEqual(second['reuse']['basis_id'], first['id'])
        self.assertEqual(engine.request.call_count, 2)
        final.validate_record(second, task)
        task['branch_run']['previous_readiness'].pop(0)
        with self.assertRaises(ValueError): final.validate_record(second, task)

    def test_unchanged_recheck_reuses_checks_and_approval_without_model_calls(self):
        task, engine, runtime, manifest, current, basis = self.fixture()
        result = self.run_final(task, engine, runtime, manifest, current)
        ready = result['readiness']
        self.assertEqual(ready, basis)
        engine.request.assert_not_called(); engine.checks.assert_not_called()
        self.assertEqual(task['branch_run']['previous_readiness'], [basis])

    def test_destination_movement_keeps_review_but_still_requires_branch_update(self):
        task, engine, runtime, old, current, basis = self.fixture(); manifest, current = self.update(task, old)
        ready = self.run_final(task, engine, runtime, manifest, current)['readiness']
        moved = sealed({**manifest, 'target_tip': 'later-destination'})
        def git(*args, **kwargs):
            raise ValueError('Target is not an ancestor')
        engine.request.reset_mock()
        with patch.object(final, 'build_manifest', return_value=moved), patch.object(evidence, 'candidate', return_value=current), \
             patch.object(reuse, 'diff', return_value=CODE), patch.object(final.work, 'source_git', side_effect=git):
            result = final.final_check_review(engine, runtime)
        self.assertTrue(result['readiness']['integration_blocker'])
        self.assertEqual(result['readiness']['review'], ready['review'])
        engine.request.assert_not_called()

    def test_clean_update_runs_fresh_checks_and_one_focused_review(self):
        task, engine, runtime, old, current, basis = self.fixture()
        manifest, current = self.update(task, old)
        before = copy.deepcopy(basis)
        result = self.run_final(task, engine, runtime, manifest, current, delta='+dependency now preserves bounds')
        ready = result['readiness']; self.assertEqual(ready['reuse']['mode'], 'integration')
        engine.checks.assert_called_once(); engine.request.assert_called_once()
        packet = json.loads(engine.request.call_args.args[1][1]['content'])
        self.assertEqual(packet['diff'], '+dependency now preserves bounds')
        self.assertEqual(packet['requirements'], reuse.requirements(old))
        self.assertNotEqual(ready['review']['manifest_id'], basis['review']['manifest_id'])
        self.assertEqual(basis, before)
        self.assertEqual(ready['checks'][0]['record']['input_identity'], 'new-inputs')
        restored = json.loads(json.dumps(task)); runtime.task = restored
        engine.request.reset_mock(); engine.checks.reset_mock()
        self.run_final(restored, engine, runtime, manifest, current, delta='+dependency now preserves bounds')
        engine.request.assert_not_called(); engine.checks.assert_not_called()

    def test_clean_update_can_reject_cross_file_regression_without_replaying_original_chunks(self):
        task, engine, runtime, old, current, basis = self.fixture(); manifest, current = self.update(task, old)
        def reject(rt, messages, tools, role, **kw):
            reply = self.respond(rt, messages, tools, role, **kw)
            value = json.loads(reply['tool_calls'][0]['function']['arguments'])
            value.update(decision='REQUEST_CHANGES', defects=[{'criterion': 'one:1', 'kind': 'static', 'location': 'dependency.py:1',
                'expected': 'Both bounds work', 'observed': 'Changed lower bound is ignored',
                'support': 'The dependency returns upper without applying lower', 'reproduction': ''}])
            reply['tool_calls'][0]['function']['arguments'] = json.dumps(value)
            return reply
        engine.request.side_effect = reject
        result = self.run_final(task, engine, runtime, manifest, current, delta='+return upper')
        self.assertEqual(result['decision'], 'REQUEST_CHANGES'); self.assertNotIn('readiness', result)
        engine.request.assert_called_once(); self.assertEqual(basis['review']['decision'], 'APPROVE')

    def test_changed_scope_direction_missing_provenance_and_invalid_receipts_cannot_reuse(self):
        for change in ('direction', 'plan', 'requirements', 'missing_provenance', 'approval', 'check', 'update', 'unrelated_run'):
            with self.subTest(change=change):
                task, engine, runtime, old, current, basis = self.fixture(); manifest, current = self.update(task, old)
                if change == 'direction': task['steer_guidance'] = 'Also require strict validation'
                elif change == 'plan': manifest['plan_content_digest'] = 'different'
                elif change == 'requirements': manifest['requirements'][0]['criterion'] = 'Different request'
                elif change == 'missing_provenance': basis.pop('review_input_digest')
                elif change == 'approval': basis['review']['decision'] = 'REQUEST_CHANGES'
                elif change == 'check': basis['checks'][0]['record']['passed'] = False
                elif change == 'update': task['branch_run']['target_update_history'][0]['approved'] = False
                else: manifest['run_id'] = 'other'
                task['branch_run']['previous_readiness'] = [sealed(basis)]
                with patch.object(reuse, 'diff', return_value=CODE):
                    self.assertIsNone(reuse.prepare(task, sealed(manifest), current, evidence.current_checks(current, [self.check('new-inputs')])))

    def test_required_check_failure_does_not_reuse_approval(self):
        task, engine, runtime, old, current, basis = self.fixture(); manifest, current = self.update(task, old)
        engine.checks.return_value = {'passed': False, 'exit_code': 1}
        with patch.object(final, 'build_manifest', return_value=manifest), patch.object(evidence, 'candidate', return_value=current):
            result = final.final_check_review(engine, runtime)
        self.assertEqual(result['decision'], 'REQUEST_CHANGES'); self.assertNotIn('readiness', result)
        engine.request.assert_not_called()

    def test_merged_receipt_rejects_missing_basis_tampered_diff_and_cancellation(self):
        task, engine, runtime, old, current, basis = self.fixture(); manifest, current = self.update(task, old)
        ready = self.run_final(task, engine, runtime, manifest, current)['readiness']
        bad = copy.deepcopy(ready); bad['reuse']['diff'] = '+hidden change'; bad = sealed(bad)
        with self.assertRaises(ValueError): final.validate_record(bad, task)
        with patch.object(reuse, 'diff', return_value='+unexpected integration'):
            with self.assertRaises(ValueError): reuse.validate_diff(ready, task)
        task['branch_run']['previous_readiness'] = []
        with self.assertRaises(ValueError): final.validate_record(ready, task)
        task['branch_run']['previous_readiness'] = [basis]
        runtime.stop.is_set = lambda: True
        with self.assertRaises(InterruptedError): self.run_final(task, engine, runtime, manifest, current)
