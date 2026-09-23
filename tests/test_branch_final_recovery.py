"""Deterministic final-review continuation; no Git, sleeps or model requests."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_final as final, branch_review_recovery, routing
from cheapos.providers import BudgetError
from tests.test_review_assessment import assessment


class FinalRecoveryTests(unittest.TestCase):
    def test_oversized_rejection_remains_retrievable_through_continuation_and_resume(self):
        from cheapos import context_evidence
        for resume in (False, True):
            with self.subTest(resume=resume):
                task, engine, runtime = self.fixture(); task['review_contract_version'] = 1
                original = copy.deepcopy(task)
                packet = {'diff': '+return max(lower, min(value, upper))', 'checks': task['checks']}
                manifest = {'id': 'm', 'requirements': [{'id': 'one:1'}]}
                oversized = self.approval()['tool_calls'][0]['result']
                oversized['criteria_ids'] = ['one:1']
                oversized['feedback'] = 'rejected-long-verdict ' * 4000
                def finish(rt, messages, tools, role, **kw):
                    self.assertLess(len(json.dumps(messages)), 80000)
                    update = json.loads(messages[2]['content'])['final_review_continuation']
                    self.assertIn('feedback must be', update['latest_feedback']['validation']['error'])
                    refs = update['retained_review_history']
                    retained = [json.loads(rt.task['context_evidence'][ref]['text']) for ref in refs]
                    self.assertIn(oversized['feedback'], json.dumps(retained))
                    self.assertTrue(context_evidence.read(rt.task, refs[0])['historical'])
                    state = next(iter(rt.task['branch_run']['final_review_packets'].values()))
                    self.assertTrue(state['evidence_review']['excerpts'])
                    self.assertEqual(list(rt.task['branch_run']['final_review_corrections'].values()), [1])
                    if resume and engine.request.call_count == 3:
                        raise InterruptedError('Saved oversized correction')
                    result = self.approval()['tool_calls'][0]['result']
                    result.update(criteria_ids=['one:1'], review_assessment=assessment(['one:1']))
                    return self.call('final_review_decision', result)
                def respond(rt, messages, tools, role, **kw):
                    if engine.request.call_count == 1:
                        return self.call('read_review_evidence', {'source': 'diff'})
                    if engine.request.call_count == 2:
                        return self.call('final_review_decision', copy.deepcopy(oversized))
                    return finish(rt, messages, tools, role, **kw)
                engine.request.side_effect = respond
                if resume:
                    with self.assertRaises(InterruptedError):
                        final._review(engine, runtime, manifest, packet, ['diff:1'], ['one:1'])
                    runtime.task = json.loads(json.dumps(task))
                    runtime.task['providers']['reviewer'] = {'model': 'replacement'}
                    engine.request.reset_mock(side_effect=True); engine.request.side_effect = finish
                result = final._review(engine, runtime, manifest, packet, ['diff:1'], ['one:1'])
                self.assertEqual(result['decision'], 'APPROVE')
                self.assertEqual(engine.request.call_count, 1 if resume else 3)
                for key in ('usage', 'checks', 'limits'):
                    self.assertEqual(runtime.task[key], original[key])
                engine.checks.assert_not_called(); engine.file_tool.assert_not_called()

    def test_large_correction_preview_retains_full_diagnostics_without_wire_bloat(self):
        from cheapos import branch_final_recovery as recovery, context_evidence
        task, engine, _ = self.fixture()
        state = {}; messages = [{'role': 'system', 'content': 'rules'}, {'role': 'user', 'content': 'candidate'}]
        feedback = {'error': 'Repeated diagnostic. ' * 5000, 'attempt': 9, 'code': 'review_evidence_missing'}
        recovery.remember_feedback(task, state, feedback)
        preview = state['latest_feedback']
        self.assertLess(len(json.dumps(preview)), 8000)
        retained = json.loads(task['context_evidence'][preview['context_reference']]['text'])
        self.assertEqual(retained['validation'], feedback)
        before = copy.deepcopy(task)
        first = recovery.request_context(engine, task, state, messages)
        second = recovery.request_context(engine, task, state, messages)
        self.assertEqual(first, second)
        self.assertEqual(len(messages), 2)  # No accumulating policy/data messages.
        self.assertEqual(task, before)
        self.assertTrue(context_evidence.read(task, preview['context_reference'])['historical'])

    def test_saved_named_check_refresh_finishes_without_resetting_review(self):
        task, engine, runtime = self.fixture(); task['review_contract_version'] = 1
        bound = self.bound_check(task)
        criterion = 'The structural validator check passes'
        task['branch_run']['plan']['items'] = [{'id': 'one', 'acceptance_criteria': [criterion],
                                               'required_checks': [bound['command']]}]
        packet = {'checks': [bound], 'diff': '+return max(lower, min(value, upper))',
                  'requirements': [{'id': 'one:1', 'item_id': 'one', 'criterion': criterion}]}
        manifest = {'id': 'm', 'requirements': packet['requirements']}
        engine.request.side_effect = [self.call('read_review_evidence', {'source': 'diff'}),
                                      InterruptedError('pause')]
        with patch.object(final, 'criterion_check_specs', return_value={}):
            with self.assertRaises(InterruptedError):
                final._review(engine, runtime, manifest, packet, ['diff:1'], ['one:1'])
        saved = copy.deepcopy(task)
        runtime.task = json.loads(json.dumps(task))
        runtime.task['providers']['reviewer'] = {'model': 'replacement'}
        def finish(rt, messages, tools, role, **kw):
            state = next(iter(rt.task['branch_run']['final_review_packets'].values()))
            proof = state['evidence_review']
            old = next(iter(saved['branch_run']['final_review_packets'].values()))
            self.assertEqual(proof['excerpts'], old['evidence_review']['excerpts'])
            source, = proof['criterion_checks']['one:1']
            schema = tools[0]['function']['parameters']['properties']['review_assessment']
            self.assertIn(source, schema['properties']['criteria']['properties']['one:1']['description'])
            self.assertEqual(sum(t['function']['name'] == 'read_review_evidence' for t in tools), 1)
            self.assertTrue(any('return max' in m.get('content', '') for m in messages if m['role'] == 'tool'))
            result = self.approval()['tool_calls'][0]['result']
            result.update(criteria_ids=['one:1'], review_assessment=assessment(['one:1']))
            result['review_assessment']['criteria']['one:1'] = {
                'reason': 'The approved validator command passed on this candidate.',
                'citations': [{'source': source, 'quote': '"passed": true'}]}
            return self.call('final_review_decision', result)
        engine.request.reset_mock(side_effect=True); engine.request.side_effect = finish
        result = final._review(engine, runtime, manifest, packet, ['diff:1'], ['one:1'])
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(result['reviewer_model'], 'replacement')
        self.assertEqual(engine.request.call_count, 1)
        after = next(iter(runtime.task['branch_run']['final_review_packets'].values()))
        before = next(iter(saved['branch_run']['final_review_packets'].values()))
        self.assertEqual(after['binding'], before['binding'])
        self.assertNotIn('final_review_packet_history', runtime.task['branch_run'])
        for key in ('checks', 'limits', 'usage'): self.assertEqual(runtime.task[key], saved[key])
        for key in ('items', 'final_review_corrections'):
            self.assertEqual(runtime.task['branch_run'][key], saved['branch_run'][key])
        engine.checks.assert_not_called(); engine.file_tool.assert_not_called()

    def test_required_tool_choice_survives_correction_and_resume_with_saved_evidence(self):
        task, engine, runtime = self.fixture()
        before = copy.deepcopy(task)
        engine.request.side_effect = [{'role': 'assistant', 'content': 'Still reviewing.'},
                                      InterruptedError('pause at next request')]
        with self.assertRaises(InterruptedError): self.review(engine, runtime)
        self.assertTrue(all(call.kwargs['tool_choice'] == 'required' for call in engine.request.call_args_list))
        runtime.task = json.loads(json.dumps(task))
        engine.request.reset_mock(side_effect=True)
        engine.request.return_value = self.approval()
        result = self.review(engine, runtime)
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(engine.request.call_args.kwargs['tool_choice'], 'required')
        delivered = engine.request.call_args.args[1]
        self.assertTrue(any('Return an offered evidence reader' in m.get('content', '') for m in delivered))
        for key in ('checks', 'usage', 'providers', 'limits'):
            self.assertEqual(runtime.task[key], before[key])
        engine.checks.assert_not_called()
        engine.file_tool.assert_not_called()

    def test_paged_synthesis_resumes_command_claim_with_retained_receipt_and_code(self):
        task, engine, runtime = self.fixture(); task['review_contract_version'] = 1
        bound = self.bound_check(task)
        original = {'checks': [bound], 'requirements': [{'id': 'one:1', 'criterion': 'python -m unittest passes'}]}
        summary = {'diff': '+return max(lower, min(value, upper))',
                   'check_output_sources': final.check_sources(original)}
        manifest = {'id': 'm', 'requirements': original['requirements']}
        def initial(rt, messages, tools, role, **kw):
            if engine.request.call_count == 2:
                raise InterruptedError('Saved review interrupted')
            contract = json.loads(messages[1]['content'])['review_evidence']
            source, = contract['criterion_checks']['one:1']
            schema = tools[0]['function']['parameters']['properties']['review_assessment']
            self.assertIn(source, schema['properties']['criteria']['properties']['one:1']['description'])
            return self.call('read_review_evidence', {'source': source})
        engine.request.side_effect = initial
        with self.assertRaises(InterruptedError):
            final._review(engine, runtime, manifest, summary, ['diff:1'], ['one:1'], check_packet=original)
        saved = next(iter(task['branch_run']['final_review_packets'].values()))
        saved['evidence_review'].pop('criterion_checks')  # older saved contract
        runtime.task = json.loads(json.dumps(task))
        def finish(rt, messages, tools, role, **kw):
            excerpt = json.loads(messages[-1]['content'])
            claim = {'reason': 'The exact captured command passed.', 'citations': [excerpt['citation']]}
            result = self.approval()['tool_calls'][0]['result']
            result.update(criteria_ids=['one:1'], review_assessment=assessment(['one:1'], checks=False))
            result['review_assessment']['criteria']['one:1'] = claim
            result['review_assessment']['verification'] = copy.deepcopy(claim)
            return self.call('final_review_decision', result)
        engine.request.reset_mock(side_effect=True); engine.request.side_effect = finish
        result = final._review(engine, runtime, manifest, summary, ['diff:1'], ['one:1'], check_packet=original)
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(engine.request.call_count, 1)
        self.assertEqual(runtime.task['checks'], task['checks'])
        self.assertEqual(runtime.task['usage'], task['usage'])
        engine.checks.assert_not_called(); engine.file_tool.assert_not_called()

    def fixture(self):
        task={'branch_run':{'current_item_id':None,'plan':{'uncapped_work':True},
                            'items':[{'id':'one','status':'committed','commit':'saved'}]},
              'execution':{'mode':'remote'},'route':{'base_url':'gateway'},
              'providers':{'worker':{'model':'worker'},'reviewer':{'model':'reviewer'}},
              'usage':{'cost':0,'reviewer':{'tokens':100}},'limits':{'dollars':0},
              'checks':[{'passed':True,'candidate_id':'candidate'}]}
        runtime=SimpleNamespace(task=task,guard=Mock(),stop=SimpleNamespace(is_set=lambda:False))
        engine=SimpleNamespace(store=SimpleNamespace(save=Mock()),event=Mock(),request=Mock(),
            checks=Mock(),file_tool=Mock(),parse_call=lambda c:(c['name'],c['result']))
        return task,engine,runtime

    def call(self, name, result):
        return {'role':'assistant','tool_calls':[{'id':'response','name':name,'result':result}]}

    def approval(self, invalid=False):
        return self.call('final_review_decision',{'decision':'invalid' if invalid else 'APPROVE',
            'manifest_id':'m','chunk_ids':['diff:1'],'criteria_ids':[],'feedback':'Inspected exact evidence.'})

    def review(self, engine, runtime, evidence='exact source'):
        return final._review(engine,runtime,{'id':'m','requirements':[{'id':'one:1'}]},
                             {'evidence':evidence},['diff:1'],[])

    def test_new_direction_discards_inflight_approval_and_rebinds_retained_review(self):
        from cheapos.engine import OperatorRedirect
        task, engine, runtime = self.fixture()
        before = copy.deepcopy(task)
        interrupted = False
        def guard():
            if interrupted: raise OperatorRedirect('New guidance')
        runtime.guard.side_effect = guard
        def stale_response(*args, **kwargs):
            nonlocal interrupted
            task['steer_guidance'] = 'lets make sure css changes needed are also included'
            interrupted = True
            return self.approval()
        engine.request.side_effect = stale_response
        with self.assertRaises(OperatorRedirect): self.review(engine, runtime)
        old_packet = copy.deepcopy(next(iter(task['branch_run']['final_review_packets'].values())))
        self.assertNotIn('result', old_packet)
        self.assertFalse(any(c.args[1] == 'review' for c in engine.event.call_args_list))
        interrupted = False
        engine.request.side_effect = None
        decision = self.approval()['tool_calls'][0]['result']
        decision.update(decision='REQUEST_CHANGES', defects=[{
            'criterion': 'one:1', 'location': 'styles.css:1', 'kind': 'static',
            'expected': 'The new menu headings have matching styles.',
            'observed': 'The headings use an undefined class.',
            'support': 'The supplied stylesheet has no menu-header rule.', 'reproduction': ''}])
        engine.request.return_value = self.call('final_review_decision', decision)
        result = self.review(engine, runtime)
        self.assertEqual(result['decision'], 'REQUEST_CHANGES')
        self.assertEqual(result['defects'][0]['location'], 'styles.css:1')
        messages = engine.request.call_args.args[1]
        self.assertTrue(any(task['steer_guidance'] in m.get('content', '') for m in messages))
        self.assertIn(old_packet, task['branch_run']['final_review_packet_history'])
        self.assertEqual(engine.request.call_count, 2)
        for key in ('checks', 'limits', 'usage'): self.assertEqual(task[key], before[key])
        engine.checks.assert_not_called()

    def select(self, engine, runtime, role, replace):
        self.assertEqual((role,replace),('reviewer',True))
        self.assertIn('reviewer',branch_review_recovery.failed_models(runtime.task))
        runtime.task['providers']['reviewer']={'model':'replacement'}

    def bound_check(self, task):
        task['id'] = 'task'
        record = {'run_id': 'a' * 32, 'command': ['python', '-m', 'unittest'],
                  'passed': True, 'exit_code': 0, 'output': 'saved preview',
                  'raw_output': {'bytes': 30, 'truncated': False},
                  'verification_identity': 'current-input', 'input_identity': 'current-input'}
        task['checks'] = [record]
        return {'candidate_id': 'current', 'command': record['command'], 'record': copy.deepcopy(record)}

    def test_final_reviewer_reads_bound_check_output_and_finishes_without_rerun(self):
        task, engine, runtime = self.fixture(); task['review_contract_version'] = 1
        bound = self.bound_check(task); before = copy.deepcopy(task)
        packet = {'diff': '+return max(lower, min(value, upper))', 'checks': [bound]}
        def respond(rt, messages, tools, role, **kw):
            names = [t['function']['name'] for t in tools]
            self.assertIn('read_check_output', names)
            self.assertIn('read_review_evidence', names)
            self.assertNotIn('run_checks', names)
            if engine.request.call_count == 1:
                sources = json.loads(messages[1]['content'])['check_output_sources']
                return self.call('read_check_output', {'run_id': sources[0]['run_id']})
            excerpt = json.loads(messages[-1]['content'])
            self.assertEqual(excerpt['candidate_id'], 'current')
            result = self.approval()['tool_calls'][0]['result']
            result.update(criteria_ids=['one:1'], review_assessment=assessment(['one:1']))
            result['review_assessment']['verification'] = {
                'reason': 'Retained output names the passing bounds check.',
                'citations': [{'source': excerpt['evidence_id'], 'quote': 'test_bounds ... ok'}]}
            return self.call('final_review_decision', result)
        engine.request.side_effect = respond
        with patch('cheapos.check_output.read', return_value={'run_id': 'a' * 32, 'output': 'test_bounds ... ok\nOK', 'next_offset': 21, 'has_more': False}) as read:
            result = final._review(engine, runtime, {'id': 'm', 'requirements': [{'id': 'one:1'}]}, packet, ['diff:1'], ['one:1'])
        read.assert_called_once_with(engine.store, 'task', run_id='a' * 32)
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(engine.request.call_count, 2)
        self.assertEqual(task['branch_run']['final_review_corrections'], {})
        for key in ('checks', 'limits', 'usage'): self.assertEqual(task[key], before[key])
        engine.checks.assert_not_called(); engine.file_tool.assert_not_called()
        refs = next(iter(task['branch_run']['final_review_packets'].values()))['context_references']
        self.assertTrue(all('output' not in ref for ref in refs))

    def test_check_reader_rejects_changed_unrelated_and_task_command_records(self):
        task, engine, runtime = self.fixture()
        bound = self.bound_check(task)
        sources = final.check_sources({'checks': [bound]})
        with patch('cheapos.check_output.read') as read:
            task['command_runs'] = [{'run_id': 'b' * 32, 'passed': True}]
            task['checks'].append({'run_id': 'c' * 32, 'passed': True})
            for run_id in ('b' * 32, 'c' * 32, '../secret', None):
                with self.assertRaises(ValueError):
                    final.read_check_output(engine, task, sources, {'run_id': run_id})
            task['checks'][0]['input_identity'] = 'different-input'
            with self.assertRaises(ValueError):
                final.read_check_output(engine, task, sources, {'run_id': 'a' * 32})
            read.assert_not_called()

    def test_expired_output_returns_a_limitation_without_registering_evidence(self):
        from cheapos import review_assessment
        task, engine, runtime = self.fixture()
        bound = self.bound_check(task)
        packet = {'checks': [bound]}
        proof = review_assessment.prepare('candidate', packet, ['one:1'])
        before = copy.deepcopy(proof)
        with patch('cheapos.check_output.read', side_effect=ValueError('Raw output expired')):
            result = final.read_check_output(engine, task, final.check_sources(packet), {'run_id': 'a' * 32})
        self.assertFalse(result['available'])
        self.assertIn('saved check preview', result['guidance'])
        review_assessment.observation(proof, 'read_check_output', {'run_id': 'a' * 32}, result)
        self.assertEqual(proof, before)
        engine.checks.assert_not_called()

    def test_review_evidence_reader_survives_restart_and_model_handoff(self):
        task, engine, runtime = self.fixture(); task['review_contract_version'] = 1
        engine.request.side_effect = [self.call('read_final_context', {'manifest_id': 'm', 'path': 'code.py', 'start_line': 1}), InterruptedError('Stopped')]
        context = Mock(return_value={'content': '1: exact retained code', 'path': 'code.py'})
        with self.assertRaises(InterruptedError):
            final._review(engine, runtime, {'id': 'm'}, {'evidence': 'exact source'}, ['diff:1'], [], context_reader=context)
        runtime.task = json.loads(json.dumps(task))
        runtime.task['providers']['reviewer'] = {'model': 'replacement'}
        source = next(s for s in next(iter(runtime.task['branch_run']['final_review_packets'].values()))['evidence_review']['sources'] if s.startswith('read:'))
        calls = []
        def respond(rt, messages, tools, role, **kw):
            calls.append(1)
            if len(calls) == 1:
                return self.call('read_review_evidence', {'source': source, 'search': 'exact retained code'})
            excerpt = json.loads(messages[-1]['content'])
            self.assertEqual(excerpt['evidence_id'], source)
            reply = self.approval()
            reply['tool_calls'][0]['result']['review_assessment'] = assessment(['packet'], source=source, quote='exact retained code', checks=False)
            return reply
        engine.request.side_effect = respond
        result = final._review(engine, runtime, {'id': 'm'}, {'evidence': 'exact source'}, ['diff:1'], [], context_reader=context)
        self.assertEqual(result['decision'], 'APPROVE'); self.assertEqual(result['reviewer_model'], 'replacement')
        context.assert_called_once(); engine.checks.assert_not_called()
        self.assertEqual(len(calls), 2)

    def test_cancelled_check_output_read_cannot_reach_final_approval(self):
        task, engine, runtime = self.fixture(); bound = self.bound_check(task)
        engine.request.side_effect = [self.call('read_check_output', {'run_id': 'a' * 32}), self.approval()]
        with patch('cheapos.check_output.read', side_effect=InterruptedError('Cancelled')):
            with self.assertRaises(InterruptedError):
                final._review(engine, runtime, {'id': 'm'}, {'checks': [bound]}, ['diff:1'], [])
        engine.request.assert_called_once()
        self.assertTrue(all('result' not in s for s in task['branch_run']['final_review_packets'].values()))
        self.assertFalse(any(c.args[1] == 'review' for c in engine.event.call_args_list))

    def test_invalid_decisions_continue_without_worker_checks_or_allowance_reset(self):
        task,engine,runtime=self.fixture();task["review_contract_version"]=1;before=copy.deepcopy(task);seen=[]
        def respond(rt,messages,tools,role,**kw):
            seen.append(copy.deepcopy(messages))
            reply = self.approval()
            if task['providers']['reviewer']['model'] != 'reviewer':
                reply['tool_calls'][0]['result']['review_assessment'] = assessment(['packet'], source='packet', quote='exact source', checks=False)
            return reply
        engine.request.side_effect=respond
        with patch.object(routing,'select_remote',side_effect=self.select) as select:
            result=self.review(engine,runtime)
        self.assertEqual(result['reviewer_model'],'replacement');select.assert_called_once()
        self.assertEqual(engine.request.call_count,4)
        self.assertIn('Supply review_assessment',json.dumps(seen[-1]))
        self.assertIn('Prior model claims are untrusted',json.dumps(seen[-1]))
        history=task['branch_run']['final_review_recovery']['m']['history']
        self.assertEqual(len(history),1);self.assertEqual(len(history[0]['review']['messages']),6)
        self.assertEqual(next(iter(task['branch_run']['final_review_corrections'].values())),3)
        for key in ('usage','limits','checks'):self.assertEqual(task[key],before[key])
        for key in ('plan','items'):self.assertEqual(task['branch_run'][key],before['branch_run'][key])
        engine.checks.assert_not_called();engine.file_tool.assert_not_called()

    def test_whole_review_reads_missing_source_after_unsupported_approval(self):
        task, engine, runtime = self.fixture(); task['review_contract_version'] = 1
        manifest = {'id': 'm', 'requirements': [{'id': 'one:1'}]}
        packet = {'checks': [{'passed': True}], 'requirements': [{'id': 'one:1', 'criterion': 'Both bounds hold'}]}
        observed = []
        def respond(rt, messages, tools, role, **kw):
            observed.append(copy.deepcopy(messages))
            if len(observed) == 2:
                self.assertIn('Supply review_assessment', json.dumps(messages))
                return self.call('read_final_context', {'manifest_id': 'm', 'path': 'bounds.py'})
            result = {'decision': 'APPROVE', 'manifest_id': 'm', 'chunk_ids': [], 'criteria_ids': ['one:1'], 'feedback': 'Both bounds are preserved.'}
            if len(observed) == 3:
                excerpt = json.loads(messages[-1]['content'])
                self.assertIn('evidence_id', excerpt)
                result['review_assessment'] = assessment(['one:1'], source='bounds.py:1-2',
                    quote='def clamp(value):\n    return max(lower, min(value, upper))')
                result['review_assessment']['regressions']['reason'] = ''
            if len(observed) == 4:
                correction = json.loads(messages[-1]['content'])
                self.assertEqual(correction['code'], 'review_evidence_missing')
                self.assertTrue(any(i['field'] == 'review_assessment.regressions.reason' for i in correction['issues']))
                source = next(i['matching_source_ids'][0] for i in correction['issues'] if i.get('matching_source_ids'))
                result['review_assessment'] = assessment(['one:1'], source=source,
                    quote='def clamp(value):\n    return max(lower, min(value, upper))')
            return self.call('final_review_decision', result)
        engine.request.side_effect = respond
        result = final._review(engine, runtime, manifest, packet, [], ['one:1'],
                               context_reader=lambda args: {'path': 'bounds.py',
                                   'content': '1: def clamp(value):\n2:     return max(lower, min(value, upper))'})
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(len(observed), 4)
        engine.checks.assert_not_called()

    def test_final_image_inspection_uses_independent_reviewer_and_records_evidence(self):
        task, engine, runtime = self.fixture(); task['review_contract_version'] = 1
        task['status'] = 'running'; task['active_role'] = 'worker'
        def respond(rt, messages, tools, role, **kw):
            self.assertIn('inspect_image', [tool['function']['name'] for tool in tools])
            if engine.request.call_count == 1:
                return self.call('inspect_image', {'path': 'screenshot.png', 'query': 'Is the label clipped?'})
            reply = self.approval()
            excerpt = json.loads(messages[-1]['content'])
            reply['tool_calls'][0]['result']['review_assessment'] = assessment(['packet'], source=excerpt['evidence_id'], quote='Label is readable.', checks=False)
            return reply
        engine.request.side_effect = respond
        with patch('cheapos.vision.inspect_image_tool', return_value={'status': 'success', 'analysis': 'Label is readable.', 'image_digest': 'image'}) as inspect:
            result = self.review(engine, runtime)
        self.assertEqual(inspect.call_args.kwargs['role'], 'reviewer')
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertIn('image', [v['kind'] for v in result['_review_evidence']['excerpts'].values()])

    def test_large_evidence_catalog_is_retrievable_without_stopping_review(self):
        from cheapos import context_evidence
        task, engine, runtime = self.fixture(); task['review_contract_version'] = 1
        def respond(rt, messages, tools, role, **kw):
            envelope = json.loads(messages[1]['content'])
            self.assertLess(len(messages[1]['content']), 60000)
            reference = envelope['complete_packet_reference']
            self.assertIn('sentinel', task['context_evidence'][reference]['text'])
            reply = self.approval()
            reply['tool_calls'][0]['result']['review_assessment'] = assessment(['packet'], source='packet', quote='sentinel', checks=False)
            return reply
        engine.request.side_effect = respond
        self.review(engine, runtime, evidence='sentinel' + 'x' * 60000)
        engine.request.assert_called_once()

    def test_identity_replacement_request_rejection_still_reaches_final_approval(self):
        from cheapos import reviewer_recovery
        from cheapos.providers import ProviderError
        task,engine,runtime=self.fixture();before=copy.deepcopy(task)
        seen=[]
        def routed(rt,messages,tools,role,override=None,purpose=None,**kwargs):
            seen.append(copy.deepcopy(messages))
            self.assertEqual(purpose,'branch_final')
            if override is None:raise ProviderError('unknown identity',code='review_identity_unknown')
            if override['model']=='rejected':raise ProviderError('model rejected request',code='http_400')
            return self.approval()
        engine._request_routed=Mock(side_effect=routed)
        engine.request=lambda *a,**kw:reviewer_recovery.request(engine,*a,**kw)
        with patch.object(reviewer_recovery,'candidates',return_value=[{'id':'rejected'},{'id':'independent'}]), \
             patch.object(reviewer_recovery,'qualify',return_value=True), \
             patch.object(reviewer_recovery,'config',side_effect=lambda e,t,m:{'model':m}):
            result=self.review(engine,runtime)
        self.assertEqual(result['decision'],'APPROVE');self.assertEqual(result['reviewer_model'],'independent')
        self.assertEqual(engine._request_routed.call_count,3);self.assertEqual(seen,[seen[0]]*3)
        for key in ('checks','usage','limits'):self.assertEqual(task[key],before[key])
        self.assertEqual(task['branch_run']['items'],before['branch_run']['items'])
        engine.checks.assert_not_called();engine.file_tool.assert_not_called()

    def test_provider_handoff_after_six_chunks_keeps_reviews_and_finishes_next_chunk(self):
        import io
        import tempfile
        from urllib.error import HTTPError
        from cheapos import reviewer_recovery
        from cheapos.model_pool import FreeModelPool
        from cheapos.providers import ProviderError, http_failure
        from cheapos.served_identity import ensure_independent, metadata
        task,engine,runtime=self.fixture();before=copy.deepcopy(task)
        endpoint='http://localhost:1/v1';original='openrouter/reviewer:free'
        task['providers']['reviewer']={'model':original,'provider':'openrouter',
            'base_url':endpoint,'gateway':'omniroute','input_rate':0,'output_rate':0}
        task['reviewer_identity_recovery']={'attempted':[original],'selected':original}
        models=[{'id':name,'provider':provider,'free':True,'tool_calling':True}
                for name,provider in ((original,'openrouter'),('oc/reviewer','opencode'),
                                      ('oc/sibling','opencode'),('groq/reviewer','groq'))]
        calls=[];chunk=[1]
        def routed(rt,messages,tools,role,override=None,purpose=None,**kwargs):
            cfg=override;calls.append((chunk[0],cfg['model']))
            if chunk[0]==7 and cfg['model']==original:
                raise ProviderError('Timed out',code='model_connection')
            if cfg['model'].startswith('oc/'):
                body=json.dumps({'error':{'message':"[403]: Error from provider (Console): OpenCode's free tier can only be used from within OpenCode"}}).encode()
                raise http_failure(HTTPError(endpoint,403,'denied',{},io.BytesIO(body)),cfg)
            ensure_independent(rt.task,{'role':'reviewer',**metadata(cfg['model'],cfg['model'])})
            result=self.approval()['tool_calls'][0]['result']
            result['chunk_ids']=[f'diff:{chunk[0]}']
            return self.call('final_review_decision',result)
        engine._request_routed=Mock(side_effect=routed)
        engine.request=lambda *a,**kw:reviewer_recovery.request(engine,*a,**kw)
        def review():
            return final._review(engine,runtime,{'id':'m','requirements':[{'id':'one:1'}]},
                {'evidence':f'exact source {chunk[0]}'},[f'diff:{chunk[0]}'],[])
        with tempfile.TemporaryDirectory() as directory:
            pool=FreeModelPool(directory)
            # These fixtures test full-request outages after tool qualification.
            pool.interleave=lambda endpoint,candidates,role,**kw:candidates  # Deterministic fault sequence.
            from cheapos.route_health import probe_identity
            for model in models:
                pool.record(endpoint,model['id'],'reviewer',probe=True,
                            probe_identity=probe_identity(endpoint,model,None))
            engine.gateway=SimpleNamespace(settings={'base_url':endpoint},pool=pool,
                catalog=lambda **kw:{'models':models})
            engine.connection_for=lambda cfg:engine.gateway
            for n in range(1,7):
                chunk[0]=n;self.assertEqual(review()['decision'],'APPROVE')
            saved=copy.deepcopy(task['branch_run']['final_review_packets'])
            runtime.task=json.loads(json.dumps(task))
            chunk[0]=7;result=review()
            self.assertEqual(result['decision'],'APPROVE')
            self.assertEqual(result['reviewer_model'],'groq/reviewer')
            for key,value in saved.items():
                self.assertEqual(runtime.task['branch_run']['final_review_packets'][key],value)
            for n in range(1,8):
                chunk[0]=n;self.assertEqual(review()['decision'],'APPROVE')
            self.assertTrue(pool.observation(endpoint,'oc/sibling')['cooling_down'])
            self.assertFalse(pool.observation(endpoint,'groq/reviewer')['cooling_down'])
        self.assertEqual(calls,[(n,original) for n in range(1,8)]+[(7,'oc/reviewer'),(7,'groq/reviewer')])
        for key in ('checks','usage','limits'):self.assertEqual(runtime.task[key],before[key])
        engine.checks.assert_not_called();engine.file_tool.assert_not_called()

    def test_format_handoff_dispatches_new_reviewer_before_stale_identity_choices(self):
        from cheapos import reviewer_recovery
        from cheapos.providers import ProviderError
        task,engine,runtime=self.fixture();before=copy.deepcopy(task)
        task['reviewer_identity_recovery']={'attempted':['reviewer'], 'selected':'reviewer'}
        dispatched=[]
        def routed(rt,messages,tools,role,override=None,purpose=None,**kwargs):
            name=override['model'];dispatched.append(name)
            if name=='denied':raise ProviderError('access denied',code='http_403')
            return self.approval(invalid=name=='reviewer')
        engine._request_routed=Mock(side_effect=routed)
        engine.request=lambda *a,**kw:reviewer_recovery.request(engine,*a,**kw)
        with patch.object(reviewer_recovery,'candidates',return_value=[{'id':'denied'},{'id':'reviewer'},{'id':'replacement'}]), \
             patch.object(reviewer_recovery,'qualify',return_value=True), \
             patch.object(reviewer_recovery,'config',side_effect=lambda e,t,m:{'model':m}), \
             patch.object(routing,'select_remote',side_effect=self.select) as select:
            result=self.review(engine,runtime)
            runtime.task=json.loads(json.dumps(task))
            self.assertEqual(self.review(engine,runtime),result)
        self.assertEqual(dispatched,['reviewer']*3+['replacement'])
        self.assertEqual(result['decision'],'APPROVE');self.assertEqual(result['reviewer_model'],'replacement')
        select.assert_called_once()
        self.assertEqual(task['reviewer_identity_recovery']['selected'],'replacement')
        self.assertIn('reviewer',task['reviewer_identity_recovery']['attempted'])
        self.assertEqual(len(task['branch_run']['final_review_recovery']['m']['history']),1)
        for key in ('checks','usage','limits'):self.assertEqual(task[key],before[key])
        engine.checks.assert_not_called();engine.file_tool.assert_not_called()

    def test_final_review_continues_after_bad_gateway_cooldown_and_premium_model_refusal(self):
        import tempfile
        from cheapos import reviewer_recovery
        from cheapos.model_pool import FreeModelPool
        from cheapos.providers import ProviderError
        from cheapos.served_identity import ensure_independent, metadata
        from tests.test_upstream_access import rejection, KEY_REQUIRED
        task,engine,runtime=self.fixture();before=copy.deepcopy(task)
        endpoint='http://localhost:1/v1';original='openrouter/reviewer:free'
        task['providers']['reviewer']={'model':original,'provider':'openrouter',
            'base_url':endpoint,'gateway':'omniroute','input_rate':0,'output_rate':0}
        task['reviewer_identity_recovery']={'attempted':[original],'selected':original}
        models=[{'id':name,'provider':provider,'free':True,'tool_calling':True}
                for name,provider in ((original,'openrouter'),('antigravity/reviewer','antigravity'),
                    ('antigravity/sibling','antigravity'),('oc/union-alpha','opencode'),('oc/free','opencode'))]
        calls=[];chunk=[1]
        def routed(rt,messages,tools,role,override=None,purpose=None,**kwargs):
            name=override['model'];calls.append((chunk[0],name))
            if chunk[0]==2:
                if name==original:raise ProviderError('Bad gateway',code='http_502')
                if name.startswith('antigravity/'):
                    raise ProviderError('Cooldown',code='gateway_cooldown',scope='provider',retry_after=300)
                if name=='oc/union-alpha':raise rejection('[402]: '+KEY_REQUIRED,name,402)
            ensure_independent(rt.task,{'role':'reviewer',**metadata(name,name)})
            result=self.approval()['tool_calls'][0]['result'];result['chunk_ids']=[f'diff:{chunk[0]}']
            return self.call('final_review_decision',result)
        engine._request_routed=Mock(side_effect=routed)
        engine.request=lambda *a,**kw:reviewer_recovery.request(engine,*a,**kw)
        def review():
            return final._review(engine,runtime,{'id':'m','requirements':[{'id':'one:1'}]},
                {'evidence':f'exact source {chunk[0]}'},[f'diff:{chunk[0]}'],[])
        with tempfile.TemporaryDirectory() as directory:
            pool=FreeModelPool(directory)
            engine.gateway=SimpleNamespace(settings={'base_url':endpoint},pool=pool,
                catalog=lambda **kw:{'models':models})
            pool.interleave=lambda endpoint,candidates,role,**kw:candidates  # Deterministic fault sequence.
            from cheapos.route_health import probe_identity
            for model in models:
                pool.record(endpoint,model['id'],'reviewer',probe=True,
                            probe_identity=probe_identity(endpoint,model,None))
            engine.connection_for=lambda cfg:engine.gateway
            self.assertEqual(review()['decision'],'APPROVE')
            runtime.task=json.loads(json.dumps(task))
            chunk[0]=2;self.assertEqual(review()['decision'],'APPROVE')
            chunk[0]=1;self.assertEqual(review()['decision'],'APPROVE')
            self.assertTrue(pool.observation(endpoint,'oc/union-alpha')['cooling_down'])
            self.assertFalse(pool.observation(endpoint,'oc/free')['cooling_down'])
        self.assertEqual(calls,[(1,original),(2,original),(2,'antigravity/reviewer'),
                                (2,'oc/union-alpha'),(2,'oc/free')])
        for key in ('checks','usage','limits'):self.assertEqual(runtime.task[key],before[key])
        self.assertEqual(runtime.task['branch_run']['items'],before['branch_run']['items'])
        engine.checks.assert_not_called();engine.file_tool.assert_not_called()

    def test_exact_function_namespace_decision_uses_normal_coverage_validation(self):
        from cheapos.engine import Engine
        from tests.test_branch_disagreement import defect
        task,engine,runtime=self.fixture();engine.parse_call=Engine.parse_call
        result=self.approval()['tool_calls'][0]['result']
        def call(name,args):
            return {'role':'assistant','tool_calls':[{'id':'call','function':{'name':name,'arguments':json.dumps(args)}}]}
        wrong_tool=call('other.final_review_decision',result)
        wrong_coverage=call('functions.final_review_decision',{**result,'manifest_id':'wrong'})
        valid=call('functions.final_review_decision',{**result,'decision':'REQUEST_CHANGES','defects':[{**defect(),'criterion':'one:1'}]})
        engine.request.side_effect=[wrong_tool,wrong_coverage,valid]
        reviewed=self.review(engine,runtime)
        self.assertEqual(reviewed['decision'],'REQUEST_CHANGES')
        self.assertEqual(len(reviewed['defects']),1)
        self.assertEqual(next(iter(task['branch_run']['final_review_corrections'].values())),2)
        self.assertEqual(valid['tool_calls'][0]['function']['name'],'functions.final_review_decision')
        self.assertNotIn('readiness',task['branch_run']);engine.file_tool.assert_not_called()

    def test_exact_function_namespace_approval_does_not_need_format_retry(self):
        from cheapos.engine import Engine
        task,engine,runtime=self.fixture();engine.parse_call=Engine.parse_call
        args=self.approval()['tool_calls'][0]['result']
        engine.request.return_value={'role':'assistant','tool_calls':[{'id':'call','function':{
            'name':'functions.final_review_decision','arguments':json.dumps(args)}}]}
        reviewed=final._review(engine,runtime,{'id':'m','requirements':[{'id':'one:1'}]},
            {'evidence':'exact source','scope':{'chunk_index':3,'chunk_total':10}},['diff:1'],[])
        self.assertEqual(reviewed['decision'],'APPROVE')
        self.assertEqual(engine.event.call_args.args[2],'Final review chunk 3 of 10 completed')
        engine.request.assert_called_once()
        self.assertEqual(task['branch_run']['final_review_corrections'],{})

    def test_large_pages_resume_with_independent_saved_coverage(self):
        task,engine,runtime=self.fixture()
        bound = self.bound_check(task)
        packet={'evidence':'exact evidence '*6000, 'checks': [bound]}
        def respond(rt,messages,tools,role,**kwargs):
            sent=json.loads(messages[1]['content'])
            self.assertEqual(sent['check_output_sources'], final.check_sources(packet))
            result=self.approval()['tool_calls'][0]['result']
            if 'page_index' in sent: result['chunk_ids']=[]
            return self.call('final_review_decision',result)
        engine.request.side_effect=respond
        manifest={'id':'m','requirements':[{'id':'one:1'}]}
        result=final.review_paged(engine,runtime,manifest,packet,['diff:1'],[])
        count=engine.request.call_count
        self.assertGreater(count,2)
        self.assertEqual(len(task['branch_run']['final_review_packets']),count)
        runtime.task=json.loads(json.dumps(task))
        self.assertEqual(final.review_paged(engine,runtime,manifest,packet,['diff:1'],[]),result)
        self.assertEqual(engine.request.call_count,count)
        engine.checks.assert_not_called()

    def test_repeated_evidence_reads_still_handoff_and_finish(self):
        task, engine, runtime = self.fixture(); task['review_contract_version'] = 1
        read = self.call('read_review_evidence', {'source': 'packet'})
        approval = self.approval()
        approval['tool_calls'][0]['result']['review_assessment'] = assessment(['packet'], source='packet', quote='exact source', checks=False)
        engine.request.side_effect = [read] * 4 + [approval]
        with patch.object(routing, 'select_remote', side_effect=self.select) as select:
            result = self.review(engine, runtime)
        select.assert_called_once()
        self.assertEqual(result['reviewer_model'], 'replacement')
        self.assertEqual(engine.request.call_count, 5)
        engine.checks.assert_not_called()

    def test_legacy_exhaustion_selects_before_dispatch_and_keeps_real_defect(self):
        task,engine,runtime=self.fixture()
        key=final._hash({'manifest_id':'m','chunk_ids':['diff:1'],'criteria_ids':[]})
        task['branch_run']['final_review_corrections']={key:3}
        from tests.test_branch_disagreement import defect
        finding={**defect(),'criterion':'one:1'}
        result=self.approval()['tool_calls'][0]['result']
        result.update(decision='REQUEST_CHANGES',defects=[finding])
        engine.request.return_value=self.call('final_review_decision',result)
        runtime.task=json.loads(json.dumps(task))
        with patch.object(routing,'select_remote',side_effect=self.select) as select:
            reviewed=self.review(engine,runtime)
        self.assertEqual(reviewed['defects'],[finding]);select.assert_called_once()
        engine.request.assert_called_once()
        self.assertNotIn('readiness',runtime.task['branch_run'])

    def test_new_context_can_exceed_six_reads_and_exact_repeats_reuse_source(self):
        task,engine,runtime=self.fixture()
        read=lambda n:self.call('read_final_context',{'manifest_id':'m','path':'file.py','start_line':n})
        engine.request.side_effect=[read(n) for n in range(1,9)]+[read(8)]*3+[self.approval()]
        def excerpt(run,manifest,args):
            return {'path':'file.py','available':True,'start_line':args['start_line'],'content':'source'}
        with patch.object(final.review_context,'read',side_effect=excerpt) as source, \
             patch.object(routing,'select_remote',side_effect=self.select) as select:
            result=self.review(engine,runtime)
        self.assertEqual(source.call_count,8);select.assert_called_once()
        self.assertEqual(len(result['context_references']),8)
        self.assertEqual(next(iter(task['branch_run']['final_context_reads'].values()))['count'],11)
        self.assertEqual(engine.request.call_count,12)

    def test_pool_exhaustion_survives_resume_without_replaying_failed_reviewers(self):
        task,engine,runtime=self.fixture();engine.request.return_value=self.approval(True)
        def select(e,rt,role,replace):
            failed=branch_review_recovery.failed_models(rt.task)
            if len(failed)==2:raise routing.RoutingPause('No unused authorized reviewer')
            rt.task['providers']['reviewer']={'model':'replacement'}
        with patch.object(routing,'select_remote',side_effect=select):
            for _ in range(2):
                with self.assertRaises(routing.RoutingPause):self.review(engine,runtime)
                runtime.task=json.loads(json.dumps(runtime.task))
        self.assertEqual(engine.request.call_count,6)
        recovery=runtime.task['branch_run']['final_review_recovery']['m']
        self.assertEqual(recovery['failed_models'],['reviewer','replacement'])
        self.assertEqual(recovery['selection']['from'],'replacement')

    def test_restart_after_selection_does_not_probe_or_restart_work_again(self):
        task,engine,runtime=self.fixture();engine.request.return_value=self.approval(True)
        def interrupted(e,rt,role,replace):
            self.select(e,rt,role,replace)
            raise InterruptedError('Stopped after saving selected route')
        with patch.object(routing,'select_remote',side_effect=interrupted):
            with self.assertRaises(InterruptedError):self.review(engine,runtime)
        runtime.task=json.loads(json.dumps(task));engine.request.return_value=self.approval()
        with patch.object(routing,'select_remote') as select:self.review(engine,runtime)
        select.assert_not_called();self.assertEqual(engine.request.call_count,4)
        self.assertEqual(len(runtime.task['branch_run']['final_review_recovery']['m']['history']),1)

    def test_manual_pin_holds_until_operator_changes_reviewer(self):
        task,engine,runtime=self.fixture();task['operator_reviewer_model']='reviewer'
        engine.request.return_value=self.approval(True)
        with patch.object(routing,'select_remote') as select:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError,'choose another reviewer'):self.review(engine,runtime)
            self.assertEqual(engine.request.call_count,3)
            task['operator_reviewer_model']='chosen';task['providers']['reviewer']['model']='chosen'
            task['branch_run']['final_review_recovery']={'m':{'failed_models':['chosen'],'history':[]}}
            with self.assertRaisesRegex(ValueError,'already failed'):self.review(engine,runtime)
            self.assertEqual(engine.request.call_count,3)
            task['providers']['reviewer']['model']='unused';task['operator_reviewer_model']='unused'
            engine.request.return_value=self.approval()
            self.assertEqual(self.review(engine,runtime)['reviewer_model'],'unused')
        select.assert_not_called()

    def test_stop_budget_permission_and_unknown_worker_identity_block_handoff(self):
        from cheapos.branch_pause import PauseError
        for boundary in ('stop','budget','permission','identity'):
            with self.subTest(boundary=boundary):
                task,engine,runtime=self.fixture()
                key=final._hash({'manifest_id':'m','chunk_ids':['diff:1'],'criteria_ids':[]})
                task['branch_run']['final_review_corrections']={key:3}
                expected=ValueError
                if boundary=='stop':runtime.stop.is_set=lambda:True;expected=InterruptedError
                if boundary=='budget':runtime.guard.side_effect=BudgetError('Limit');expected=BudgetError
                if boundary=='permission':task['pending_approval']={'command':'tests'}
                if boundary=='identity':expected=PauseError
                with patch.object(routing,'select_remote') as select, \
                     patch('cheapos.reviewer_recovery.unknown_workers',return_value=['unknown'] if boundary=='identity' else []), \
                     self.assertRaises(expected):self.review(engine,runtime)
                select.assert_not_called();engine.request.assert_not_called()

    def test_completed_packet_is_reused_only_for_identical_evidence_and_direction(self):
        task,engine,runtime=self.fixture();engine.request.return_value=self.approval()
        original=self.review(engine,runtime)
        runtime.task=json.loads(json.dumps(task))
        self.assertEqual(self.review(engine,runtime),original);engine.request.assert_called_once()
        self.review(engine,runtime,'different check evidence');self.assertEqual(engine.request.call_count,2)
        runtime.task['steer_guidance']='Check the authorized requirement carefully.'
        self.review(engine,runtime,'different check evidence');self.assertEqual(engine.request.call_count,3)
        runtime.stop.is_set=lambda:True
        with self.assertRaises(InterruptedError):self.review(engine,runtime,'different check evidence')
        self.assertEqual(engine.request.call_count,3)

    def test_evidence_contract_reuses_saved_defects_without_requesting_approval(self):
        task, engine, runtime = self.fixture(); task['review_contract_version'] = 1
        reply = self.approval()
        reply['tool_calls'][0]['result'].update(decision='REQUEST_CHANGES', feedback='Current source violates the requirement.',
            defects=[{'criterion': 'one:1', 'location': 'code.py:1', 'kind': 'static',
                      'expected': 'Preserve the lower bound', 'observed': 'Lower bound is absent',
                      'support': 'The candidate returns value without applying the lower bound.', 'reproduction': ''}])
        engine.request.return_value = reply
        original = self.review(engine, runtime)
        runtime.task = json.loads(json.dumps(task))
        self.assertEqual(self.review(engine, runtime), original)
        self.assertEqual(original['decision'], 'REQUEST_CHANGES')
        engine.request.assert_called_once()

    def test_handoff_cannot_accept_worker_as_reviewer(self):
        task,engine,runtime=self.fixture()
        engine.request.side_effect=[self.approval(True)]*3+[self.approval()]
        def select(e,rt,role,replace):rt.task['providers']['reviewer']['model']='worker'
        with patch.object(routing,'select_remote',side_effect=select), \
             self.assertRaisesRegex(ValueError,'not independent'):self.review(engine,runtime)
        self.assertFalse(any(p.get('result') for p in task['branch_run']['final_review_packets'].values()))
