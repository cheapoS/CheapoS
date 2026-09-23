"""Offline review graph replays: no Git, sockets, sleeps or paid inference."""
import copy
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_final as final, review_workflow as workflow, review_unit
from cheapos.engine import Engine
from cheapos.instructions.runtime import audit_tools, prompt


class ReviewWorkflowTests(unittest.TestCase):
    def fixture(self, count=9):
        rows = [{'id': 'item:' + str(i + 1), 'item_id': 'item',
                 'criterion': 'Required behavior ' + str(i + 1)} for i in range(count)]
        task = {'review_contract_version': 1, 'prompt': 'Implement the requested behavior',
            'branch_run': {'current_item_id': None, 'plan': {'uncapped_work': True}, 'items': []},
            'providers': {'worker': {'model': 'worker'}, 'reviewer': {'model': 'reviewer'}},
            'usage': {'reviewer': {'tokens': 123}}, 'limits': {'dollars': 0},
            'checks': [{'passed': True, 'exit_code': 0, 'command': ['python', '-m', 'unittest']}]}
        runtime = SimpleNamespace(task=task, guard=Mock(), stop=threading.Event())
        engine = SimpleNamespace(store=SimpleNamespace(save=Mock()), event=Mock(),
            request=Mock(), checks=Mock(), file_tool=Mock(), parse_call=Engine.parse_call)
        manifest = {'id': 'manifest', 'requirements': rows,
                    'chunks': [{'id': 'diff:1', 'digest': 'digest'}]}
        packet = {'manifest_id': 'manifest', 'chunk_ids': ['diff:1'],
            'criteria_ids': [r['id'] for r in rows], 'requirements': rows,
            'diff': '+return min(max(value, low), high)', 'checks': task['checks']}
        engine.request.side_effect = self.approve
        return task, engine, runtime, manifest, packet

    def call(self, name, args, ident='c'):
        return {'role': 'assistant', 'tool_calls': [{'id': ident, 'type': 'function',
            'function': {'name': name, 'arguments': json.dumps(args)}}]}

    def context(self, messages):
        return next(value for m in messages if m.get('role') == 'user' and m.get('content', '').startswith('{')
                    for value in [json.loads(m['content'])] if 'review_progress' in value)

    def approve(self, runtime, messages, tools, role, **kwargs):
        self.assertEqual(audit_tools('review_unit', tools), [])
        self.assertEqual(messages[0]['content'].count(prompt('review_unit')), 1)
        self.assertEqual(kwargs['tool_choice'], 'required')
        properties = tools[0]['function']['parameters']['properties']
        self.assertTrue({'manifest_id', 'criteria_ids', 'chunk_ids', 'review_assessment'}.isdisjoint(properties))
        data = self.context(messages)
        kinds = {e['kind']: e['evidence_handle'] for e in data['delivered_evidence']}
        records = []
        for target in data['review_progress']['remaining']:
            if target == 'limitations':
                records.append({'target': target, 'limitations': []})
            else:
                records.append({'target': target, 'reason': 'The fixture implements bounds and preserves its call contract.',
                    'evidence': [kinds['check' if target == 'verification' else 'code']]})
        return self.call('final_review_decision', {'decision': 'APPROVE', 'feedback': 'Examined the assigned behavior.',
                                                  'assessments': records})

    def run_workflow(self, engine, runtime, manifest, packet):
        return workflow.run(engine, runtime, manifest, packet, final._review)

    def test_many_criteria_finish_without_megasynthesis_and_resume_uses_receipts(self):
        task, engine, rt, manifest, packet = self.fixture(23)
        before = copy.deepcopy(task)
        result = self.run_workflow(engine, rt, manifest, packet)
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(engine.request.call_count, 7)  # six small units + integration
        self.assertEqual(len(result['review_assessment']['criteria']), 23)
        workflow.validate(result, manifest, task)
        task = json.loads(json.dumps(task)); rt.task = task
        count = engine.request.call_count
        self.assertEqual(self.run_workflow(engine, rt, manifest, packet), result)
        self.assertEqual(engine.request.call_count, count)
        for key in ('usage', 'checks', 'limits', 'providers'):
            self.assertEqual(task[key], before[key])
        engine.checks.assert_not_called(); engine.file_tool.assert_not_called()
        state = task['branch_run']['review_workflows'][task['branch_run']['active_review_workflow']]
        self.assertEqual(state['status'], 'complete')
        self.assertIsNone(state['active_unit'])

    def test_cancel_then_handoff_continues_next_unit_without_operator_rework(self):
        task, engine, rt, manifest, packet = self.fixture()
        original = copy.deepcopy(task)
        def response(*args, **kwargs):
            if engine.request.call_count == 2:
                raise InterruptedError('interrupted request')
            return self.approve(*args, **kwargs)
        engine.request.side_effect = response
        with self.assertRaises(InterruptedError): self.run_workflow(engine, rt, manifest, packet)
        state = next(iter(task['branch_run']['review_workflows'].values()))
        self.assertEqual(len(state['results']), 1)
        saved = copy.deepcopy(state['results'])
        rt.task = json.loads(json.dumps(task)); rt.task['providers']['reviewer'] = {'model': 'replacement'}
        engine.request.reset_mock(); engine.request.side_effect = self.approve
        result = self.run_workflow(engine, rt, manifest, packet)
        self.assertEqual(engine.request.call_count, 3)
        self.assertEqual(result['workflow']['units'][0], next(iter(saved.values())))
        self.assertEqual(result['reviewer_model'], 'replacement')
        workflow.validate(result, manifest, rt.task)
        for key in ('usage', 'checks', 'limits'): self.assertEqual(rt.task[key], original[key])

    def test_automatic_handoff_finishes_only_unresolved_unit_and_keeps_failures(self):
        from cheapos import routing, branch_review_recovery
        task, engine, rt, manifest, packet = self.fixture(5)
        task.update(execution={'mode': 'remote'}, route={'base_url': 'https://fixture.invalid'})
        old = {'failed_models': ['reviewer'], 'history': [{'reason': 'legacy format'}]}
        task['branch_run']['final_review_recovery'] = {'manifest': copy.deepcopy(old)}
        before = copy.deepcopy(task)
        def respond(runtime, messages, tools, role, **kw):
            data = self.context(messages)
            unit = data['review_unit']
            if unit['kind'] == 'requirements' and unit['criteria_ids'] == ['item:5'] and runtime.task['providers']['reviewer']['model'] == 'reviewer':
                return self.call('final_review_decision', {'decision': 'APPROVE', 'feedback': 'Unsupported approval'})
            return self.approve(runtime, messages, tools, role, **kw)
        def select(_engine, runtime, role, replace):
            self.assertTrue(replace)
            self.assertEqual(role, 'reviewer')
            self.assertEqual(branch_review_recovery.failed_models(runtime.task), ['reviewer'])
            runtime.task['providers']['reviewer']['model'] = 'replacement'
        engine.request.side_effect = respond
        with patch.object(routing, 'select_remote', side_effect=select) as choose:
            result = self.run_workflow(engine, rt, manifest, packet)
        choose.assert_called_once()
        self.assertEqual(engine.request.call_count, 6)
        self.assertEqual(result['workflow']['units'][0]['reviewer_model'], 'reviewer')
        self.assertEqual(result['reviewer_model'], 'replacement')
        histories = task['branch_run']['final_review_recovery']
        self.assertEqual(histories['manifest'], old)
        recovery = histories['manifest:review-units:1']
        self.assertEqual(recovery['failed_models'], ['reviewer'])
        self.assertEqual(len(recovery['history']), 1)
        self.assertEqual(sum(task['branch_run']['final_review_corrections'].values()), 3)
        self.assertEqual(branch_review_recovery.failed_models(task), ['reviewer'])
        for key in ('usage', 'checks', 'limits'):
            self.assertEqual(task[key], before[key])
        engine.checks.assert_not_called()
        workflow.validate(result, manifest, task)

    def test_oversized_rejected_exchange_is_retained_and_resume_request_is_compact(self):
        task, engine, rt, manifest, packet = self.fixture(1)
        oversized = 'Rejected explanation. ' * 3000
        def respond(*args, **kw):
            result = self.approve(*args, **kw)
            if engine.request.call_count == 1:
                data = json.loads(result['tool_calls'][0]['function']['arguments'])
                data['feedback'] = oversized
                return self.call('final_review_decision', data)
            messages = args[1]
            self.assertLess(len(json.dumps(messages)), 30000)
            continuation = next(json.loads(m['content'])['final_review_continuation'] for m in messages
                                if m.get('role') == 'user' and 'final_review_continuation' in m.get('content', ''))
            refs = continuation['retained_review_history']
            self.assertIn(oversized, json.dumps([json.loads(rt.task['context_evidence'][r]['text']) for r in refs]))
            raise InterruptedError('Persisted bounded continuation')
        engine.request.side_effect = respond
        with self.assertRaises(InterruptedError):
            self.run_workflow(engine, rt, manifest, packet)
        rt.task = json.loads(json.dumps(task))
        engine.request.side_effect = self.approve
        result = self.run_workflow(engine, rt, manifest, packet)
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(sum(rt.task['branch_run']['final_review_corrections'].values()), 1)
        self.assertLess(len(json.dumps(engine.request.call_args.args[1])), 30000)
        self.assertEqual(rt.task['checks'], packet['checks'])

    def test_behavioral_claim_cannot_use_only_check_handle(self):
        task, engine, rt, manifest, packet = self.fixture(1)
        def respond(*args, **kw):
            result = self.approve(*args, **kw)
            if engine.request.call_count == 1:
                data = self.context(args[1])
                check = next(e['evidence_handle'] for e in data['delivered_evidence'] if e['kind'] == 'check')
                params = json.loads(result['tool_calls'][0]['function']['arguments'])
                params['assessments'][0]['evidence'] = [check]
                return self.call('final_review_decision', params)
            return result
        engine.request.side_effect = respond
        result = self.run_workflow(engine, rt, manifest, packet)
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(engine.request.call_count, 2)
        self.assertEqual(sum(task['branch_run']['final_review_corrections'].values()), 1)

    def test_bad_reference_corrects_only_active_unit_and_preserves_original_evidence(self):
        task, engine, rt, manifest, packet = self.fixture(1)
        def response(*args, **kwargs):
            result = self.approve(*args, **kwargs)
            if engine.request.call_count == 1:
                params = json.loads(result['tool_calls'][0]['function']['arguments'])
                params['assessments'][0]['evidence'] = ['e999']
                return self.call('final_review_decision', params)
            return result
        engine.request.side_effect = response
        result = self.run_workflow(engine, rt, manifest, packet)
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(engine.request.call_count, 2)
        self.assertEqual(sum(task['branch_run']['final_review_corrections'].values()), 1)
        engine.checks.assert_not_called()

    def test_integration_rejection_blocks_completion_after_requirements_pass(self):
        task, engine, rt, manifest, packet = self.fixture(5)
        def response(runtime, messages, *args, **kwargs):
            data = self.context(messages)
            if data['review_unit']['kind'] == 'integration':
                return self.call('final_review_decision', {'decision': 'REQUEST_CHANGES',
                    'feedback': 'The caller no longer passes required bounds.', 'defects': [{
                        'criterion': 'item:1', 'location': 'src/caller.py:2', 'expected': 'Pass the bounds',
                        'observed': 'The new call omits both bounds', 'support': 'Caller invokes clamp(value).',
                        'kind': 'static', 'reproduction': ''}]})
            return self.approve(runtime, messages, *args, **kwargs)
        engine.request.side_effect = response
        result = self.run_workflow(engine, rt, manifest, packet)
        self.assertEqual(result['decision'], 'REQUEST_CHANGES')
        state = next(iter(task['branch_run']['review_workflows'].values()))
        self.assertEqual(state['status'], 'changes_requested')
        self.assertEqual(len(state['results']), 2)
        self.assertNotIn('workflow', result)

    def test_changed_directions_or_checks_do_not_reuse_approval(self):
        for field in ('directions', 'checks', 'manifest'):
            with self.subTest(field=field):
                task, engine, rt, manifest, packet = self.fixture(1)
                self.run_workflow(engine, rt, manifest, packet)
                old = copy.deepcopy(task['branch_run']['review_workflows'])
                if field == 'directions': task['steer_guidance'] = 'Also retain keyboard accessibility'
                elif field == 'checks': packet['checks'][0]['command'] = ['python', 'other.py']
                else: manifest['id'] = 'changed'; packet['manifest_id'] = 'changed'
                result = self.run_workflow(engine, rt, manifest, packet)
                self.assertEqual(engine.request.call_count, 2)
                self.assertEqual(len(task['branch_run']['review_workflows']), 2)
                for key, value in old.items(): self.assertEqual(task['branch_run']['review_workflows'][key], value)
                workflow.validate(result, manifest, task)

    def test_tampering_partial_coverage_or_nonindependent_unit_cannot_compose(self):
        task, engine, rt, manifest, packet = self.fixture(5)
        valid = self.run_workflow(engine, rt, manifest, packet)
        for kind in ('missing', 'identity', 'scope', 'assessment', 'aggregate'):
            with self.subTest(kind=kind):
                changed = copy.deepcopy(valid)
                rows = changed['workflow']['units']
                if kind == 'missing': rows.pop(0)
                if kind == 'identity': rows[0]['reviewer_model'] = 'worker'
                if kind == 'scope': rows[0]['unit_id'] = 'other'
                if kind == 'assessment': rows[0]['review_assessment']['criteria']['item:1']['reason'] = 'Altered'
                if kind == 'aggregate': changed['review_assessment']['criteria'].pop('item:1')
                with self.assertRaises(ValueError): workflow.validate(changed, manifest, task)

    def test_mixed_read_and_approval_never_executes_or_approves(self):
        task, engine, rt, manifest, packet = self.fixture(1)
        def response(*args, **kwargs):
            result = self.approve(*args, **kwargs)
            if engine.request.call_count == 1:
                result['tool_calls'] += self.call('read_final_context', {'manifest_id': 'manifest', 'path': 'secret', 'start_line': 1}, 'r')['tool_calls']
            return result
        engine.request.side_effect = response
        result = self.run_workflow(engine, rt, manifest, packet)
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(sum(task['branch_run']['final_review_corrections'].values()), 1)
        engine.file_tool.assert_not_called()

    def test_partial_records_are_provisional_and_constant_schema_does_not_grow(self):
        task, engine, rt, manifest, packet = self.fixture(1)
        from cheapos import review_assessment as evidence, review_progress as progress
        proof = evidence.prepare('scope', packet, ['item:1']); progress.bind(proof, {})
        delivered = review_unit.initial_evidence(proof)
        code = next(x for x in delivered if x['kind'] == 'code')
        record = {'target': 'criterion:1', 'reason': 'Inspected implementation', 'evidence': [code['evidence_handle']]}
        progress.record(proof, **review_unit.expand(proof, record))
        self.assertFalse(progress.display(proof)['ready_for_final_decision'])
        result = review_unit.decision(proof, {'decision': 'APPROVE', 'use_recorded_assessment': True}, {}, 'u')
        with self.assertRaises(ValueError): progress.complete(proof, result)
        # Editing actual source invalidates its existing short reference.
        evidence.add(proof, 'diff', 'code', '+return wrong')
        with self.assertRaises(ValueError): review_unit.expand(proof, record)


if __name__ == '__main__': unittest.main()
