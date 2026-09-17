"""Tiny state/provider cases: no repositories, subprocesses, sleeps or inference."""
import copy
from decimal import Decimal
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from cheapos import branch_disagreement as disagreement, branch_final, branch_review, branch_runs
from cheapos.engine import ProgressPause


def defect(kind='static'):
    return {'criterion': 'exact values', 'location': 'report.py:12', 'expected': 'Exact decimal values',
            'observed': 'A value is rounded by float conversion', 'kind': kind,
            'support': 'The code path converts amount to float before formatting.',
            'reproduction': 'Format 9007199254740993.01 and compare exact digits' if kind == 'executable' else ''}


class DisagreementTests(unittest.TestCase):
    def test_explicit_decision_and_bounded_final_corrections(self):
        for value in (None, '', False, True, 1, [], {}, 'unknown'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                disagreement.decision({'decision':value,'feedback':'Looks good'})
        self.assertEqual(disagreement.decision({'decision':' approve '}),'APPROVE')
        self.assertEqual(disagreement.decision({'decision':'APPROVE','defects':[]}),'APPROVE')
        self.assertEqual(disagreement.schema()['minItems'],0)
        with self.assertRaisesRegex(ValueError,'return defects: \\[\\]'):
            disagreement.decision({'decision':'APPROVE','defects':[defect()]})
        runtime=SimpleNamespace(task={'branch_run':{}},guard=lambda:None)
        response={'manifest_id':'m','chunk_ids':[],'criteria_ids':[],'feedback':'Looks good'}
        engine=SimpleNamespace(store=SimpleNamespace(save=Mock()),event=Mock(),
            request=Mock(return_value={'tool_calls':[{'id':'d','result':response}]}),
            parse_call=lambda c:('final_review_decision',c['result']))
        for _ in range(2):
            with self.assertRaises(ValueError):branch_final._review(engine,runtime,{'id':'m'}, {}, [], [])
        self.assertEqual(engine.request.call_count,3)
        tools=engine.request.call_args.args[2]
        self.assertEqual(tools[0]['function']['parameters']['properties']['defects']['minItems'],0)

    def test_legacy_findings_normalize_and_cannot_bypass_saved_guard(self):
        finding=defect('executable');finding.pop('kind')
        repair=disagreement.repair({'defects':[finding]},'candidate',[])
        self.assertEqual(repair['defects'][0]['kind'],'executable')
        item={'id':'one','acceptance_criteria':['exact values'],'review_repair':{'defects':[finding]}}
        task={'branch_run':{'items':[item],'current_item_id':'one'},'checks':[]}
        with self.assertRaisesRegex(ValueError,'Demonstrate'):disagreement.before_write(task,'report.py')
        for change in ({'kind':[]},{'reproduction':False},{'kind':None},{'location':'../secret:1'},
                       {'code_location':{'path':'x'}},{'expected_behavior':'conflicting'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                disagreement.validate({'defects':[{**defect(),**change}]},['exact values'])
        ambiguous=defect();ambiguous.pop('kind')
        with self.assertRaises(ValueError):disagreement.validate({'defects':[ambiguous]},['exact values'])

    def test_contract_static_executable_and_historical_decisions(self):
        finding = {'defects': [defect()]}
        self.assertEqual(disagreement.validate(finding, ['exact values']), finding['defects'])
        executable = defect('executable')
        disagreement.validate({'defects': [executable]}, ['exact values'])
        for changed in ({}, {'defects': []}, {'defects': [dict(executable, reproduction='')]},
                        {'defects': [dict(executable, criterion='unknown')]},
                        {'defects': [dict(executable, observed='')]}):
            with self.assertRaises(ValueError): disagreement.validate(changed, ['exact values'])
        historical = {'decision': 'APPROVE', 'feedback': 'Saved before evidence contract'}
        self.assertNotIn('defects', historical)  # No migration fabricates historical proof.

    def test_unsupported_decimal_claim_pauses_across_restart_without_edit(self):
        run = branch_runs.new_run({'items': [{'id': 'one', 'title': 'Report', 'instructions': 'Keep exact values',
                    'acceptance_criteria': ['exact values'], 'required_checks': ['python tests.py']}], 'limits': {'working_seconds': 600}})
        run.update(status='running', expected_feature_tip='tip', current_item_id='one')
        run['items'][0]['status'] = 'working'
        task = {'branch_run': run, 'active_role': 'worker', 'checks': [], 'review_count': 0,
                'providers': {'worker': 'worker', 'reviewer': 'reviewer'}}
        engine = SimpleNamespace(store=SimpleNamespace(save=Mock()), event=Mock(), checks=Mock(),
                    file_tool=Mock(), parse_call=lambda c: ('review_decision', c['result']), request=Mock())
        engine.request.return_value = {'tool_calls': [{'id': 'bad', 'result': {
                    'decision': 'REQUEST_CHANGES', 'candidate_id': 'candidate',
                    'feedback': 'Decimal .2f needs conversion to float.'}}]}
        runtime = SimpleNamespace(task=task, guard=lambda: None, stop=SimpleNamespace(is_set=lambda: False))
        current = {'id': 'candidate', 'checks': [], 'patch': ''}
        with patch.object(branch_review.evidence, 'candidate', return_value=current), \
             patch.object(branch_review.evidence, 'current_checks', return_value=[]), \
             patch.object(branch_review.evidence, 'review_packet', return_value={}):
            with self.assertRaises(ProgressPause): branch_review.checkpoint(engine, runtime, {})
            self.assertEqual(engine.request.call_count, 3)
            task['branch_run'] = json.loads(json.dumps(task['branch_run']))
            with self.assertRaisesRegex(ProgressPause, 'Unsupported'): branch_review.checkpoint(engine, runtime, {})
        self.assertEqual(engine.request.call_count, 3)
        self.assertEqual(task['pending_review']['coaching']['reason'], 'invalid_decision')
        self.assertEqual(task['pending_review']['stop_diagnostic']['reason'], 'invalid_decision')
        self.assertNotIn('review_repair', task['branch_run']['items'][0])
        engine.file_tool.assert_not_called()
        # Concrete counterprobe disproves the proposed float conversion.
        exact = Decimal('9007199254740993.01')
        self.assertEqual(format(exact, '.2f'), '9007199254740993.01')
        self.assertNotEqual(format(float(exact), '.2f'), '9007199254740993.01')
        self.assertEqual(format(Decimal('.10') + Decimal('.20'), '.2f'), '0.30')

    def test_final_unsupported_claim_is_bounded_and_supported_static_stays_actionable(self):
        task = {'branch_run': {}}
        runtime = SimpleNamespace(task=task, guard=lambda: None)
        response = {'decision': 'REQUEST_CHANGES', 'manifest_id': 'm', 'chunk_ids': ['diff:1'],
                    'criteria_ids': [], 'feedback': 'Missing edge handling'}
        engine = SimpleNamespace(store=SimpleNamespace(save=Mock()), event=Mock(),
                    request=Mock(side_effect=lambda *a, **k: {'tool_calls': [{'id': 'review', 'result': copy.deepcopy(response)}]}),
                    parse_call=lambda c: ('final_review_decision', c['result']))
        manifest = {'id': 'm', 'requirements': [{'id': 'exact values'}]}
        with self.assertRaises(ProgressPause): branch_final._review(engine, runtime, manifest, {}, ['diff:1'], [])
        self.assertEqual(engine.request.call_count, 3)
        with self.assertRaises(ProgressPause): branch_final._review(engine, runtime, manifest, {}, ['diff:1'], [])
        self.assertEqual(engine.request.call_count, 3)
        fresh = SimpleNamespace(task={'branch_run': {}}, guard=lambda: None)
        response['defects'] = [defect()]
        result = branch_final._review(engine, fresh, manifest, {}, ['diff:1'], [])
        self.assertEqual(result['decision'], 'REQUEST_CHANGES')
        self.assertEqual(result['defects'], [defect()])

    def test_identical_actionable_claim_cannot_repeat_repairs_forever(self):
        task = {'branch_run': {}, 'checks': []}
        item = {}
        result = disagreement.repair({'defects': [defect()]}, 'candidate', [])
        for _ in range(3): disagreement.attach(task, item, result)
        restored = json.loads(json.dumps(task))
        with self.assertRaisesRegex(ProgressPause, 'same review disagreement'):
            disagreement.attach(restored, item, result)

    def test_executable_gate_requires_current_failed_check_and_preserves_counterprobe(self):
        item = {'id': 'one','acceptance_criteria':['exact values']}
        task = {'branch_run': {'current_item_id': 'one', 'items': [item]}, 'checks': []}
        disagreement.attach(task, item, disagreement.repair({'defects': [defect('executable')]}, 'candidate', []))
        with patch('cheapos.verification.evidence_identity', return_value='current'):
            disagreement.before_write(task, 'tests/test_precision.py')
            for path in ('report.py', '../test_report.py'):
                with self.assertRaisesRegex(ValueError, 'Demonstrate'): disagreement.before_write(task, path)
            record = {'passed': True, 'outcome': 'passed', 'exit_code': 0, 'command': ['python', 'tests.py'], 'input_identity': 'current'}
            task['checks'].append(record)
            with self.assertRaises(ValueError): disagreement.before_write(task, 'report.py')
            record.update(passed=False, outcome='test_failure', exit_code=1, input_identity='stale')
            with self.assertRaises(ValueError): disagreement.before_write(task, 'report.py')
            record['input_identity'] = 'current'
            disagreement.before_write(task, 'report.py')
        self.assertEqual(item['review_repair']['probe_observed']['input_identity'], 'current')
        self.assertIn('Preserve original assertions', item['review_repair']['repair_instruction'])
        self.assertIn('not execution consent', item['review_repair']['repair_instruction'])


class ReviewCoachingTests(unittest.TestCase):
    def test_approval_confirmation_is_corrected_without_dropping_a_defect_or_rerunning_checks(self):
        task,engine,runtime=self.fixture()
        approval={'decision':'APPROVE','candidate_id':'candidate','feedback':'Exact values are preserved.',
                  'criteria_outcomes':{'exact values':{'passed':True,'evidence':'Source and supplied checks.'}}}
        def respond(rt,messages,tools,role):
            offered=next(t for t in tools if t['function']['name']=='review_decision')
            self.assertEqual(offered['function']['parameters']['properties']['defects']['minItems'],0)
            if engine.request.call_count==1:
                confirmation={**defect(),'observed':'Exact values are preserved; this confirms the requirement.'}
                return {'tool_calls':[{'id':'bad','name':'review_decision','result':{**approval,'defects':[confirmation]}}]}
            branch_review.evidence.ready_receipt.assert_not_called()
            self.assertIn('return defects: []',messages[-1]['content'])
            self.assertIn('criteria_outcomes evidence',messages[-1]['content'])
            return {'tool_calls':[{'id':'corrected','name':'review_decision','result':{**approval,'defects':[]}}]}
        engine.request.side_effect=respond
        self.assertEqual(branch_review.checkpoint(engine,runtime,{})['decision'],'APPROVE')
        self.assertEqual(engine.request.call_count,2)
        self.assertEqual(task['branch_run']['review_disagreements']['candidate']['unsupported_attempts'],1)
        branch_review.evidence.ready_receipt.assert_called_once()
        self.assertEqual(branch_review.evidence.ready_receipt.call_args.args[2]['defects'],[])
        engine.checks.assert_not_called();engine.file_tool.assert_not_called()

    def test_last_saved_request_requires_decision_without_renewing_allowance(self):
        task,engine,runtime=self.fixture()
        task['pending_review']={'branch_candidate_id':'candidate','review_requests':7,
            'messages':[{'role':'user','content':'Previously inspected exact values implementation.'}]}
        def respond(rt,messages,tools,role):
            self.assertEqual([t['function']['name'] for t in tools],['review_decision'])
            self.assertIn('Previously inspected',json.dumps(messages))
            self.assertIn('Do not invent evidence',messages[-1]['content'])
            self.assertEqual(task['pending_review']['review_requests'],7)
            task['pending_review']['review_requests']+=1
            return {'tool_calls':[{'id':'decision','name':'review_decision','result':{'decision':'APPROVE',
                'candidate_id':'candidate','feedback':'Source and checks meet criteria',
                'criteria_outcomes':{'exact values':{'passed':True,'evidence':'Source and checks'}}}}]}
        engine.request.side_effect=respond
        self.assertEqual(branch_review.checkpoint(engine,runtime,{})['decision'],'APPROVE')
        engine.file_tool.assert_not_called()
        branch_review.evidence.ready_receipt.assert_called_once()

    def fixture(self):
        from contextlib import ExitStack
        run = branch_runs.new_run({'items':[{'id':'one','title':'Read report','instructions':'Verify exact values',
            'acceptance_criteria':['exact values'],'required_checks':['python tests.py']}], 'limits':{'working_seconds':600}})
        run.update(status='running', expected_feature_tip='tip', current_item_id='one')
        run['items'][0]['status']='working'
        task={'branch_run':run,'active_role':'worker','checks':[],'review_count':0,'checkpoints':[],
              'events':[],'providers':{'worker':{'model':'worker'},'reviewer':{'model':'reviewer'}}}
        engine=SimpleNamespace(store=SimpleNamespace(save=Mock()),event=lambda t,k,title,d:t['events'].append({'kind':k,'title':title,'detail':d}),
            checks=Mock(),file_tool=Mock(return_value={'content':'Same exact values'}),
            parse_call=lambda c:(c['name'],c.get('result',{})),request=Mock())
        runtime=SimpleNamespace(task=task,guard=Mock(),stop=SimpleNamespace(is_set=lambda:False))
        stack=ExitStack();self.addCleanup(stack.close)
        for name,value in [('candidate',{'id':'candidate','checks':[],'patch':'saved diff'}),('current_checks',[]),
                           ('review_packet',{'candidate_id':'candidate','diff':'saved diff'}),('ready_receipt','receipt'),('revalidate',None)]:
            stack.enter_context(patch.object(branch_review.evidence,name,return_value=value))
        return task,engine,runtime

    def test_nudge_after_repeated_reads_converges_through_normal_receipt_path(self):
        task,engine,runtime=self.fixture();seen=[]
        def respond(runtime,messages,tools,role):
            seen.append(copy.deepcopy(messages))
            if len(seen)<3:return {'tool_calls':[{'id':'read','name':'read_file','result':{'path':'report.py'}}]}
            guidance=json.loads(messages[-1]['content'])
            self.assertEqual(guidance['candidate_id'],'candidate')
            self.assertIn('counterevidence',guidance['instruction'])
            self.assertIn('passing tests alone are not proof',guidance['instruction'])
            self.assertEqual(len([e for e in task['events'] if e['kind']=='review_coaching']),1)
            self.assertTrue(engine.store.save.called)
            return {'tool_calls':[{'id':'decision','name':'review_decision','result':{'decision':'APPROVE','candidate_id':'candidate',
                'feedback':'Evidence meets exact values','criteria_outcomes':{'exact values':{'passed':True,'evidence':'Source and checks'}}}}]}
        engine.request.side_effect=respond
        self.assertEqual(branch_review.checkpoint(engine,runtime,{})['decision'],'APPROVE')
        self.assertEqual(len(seen),3);branch_review.evidence.ready_receipt.assert_called_once()
        self.assertNotIn('pending_review',task);engine.checks.assert_not_called()

    def test_ignored_coaching_stops_with_specific_saved_diagnostic_without_resume_renewal(self):
        from cheapos import branch_pause
        task,engine,runtime=self.fixture()
        engine.request.return_value={'tool_calls':[{'id':'read','name':'read_file','result':{'path':'report.py'}}]}
        with self.assertRaises(ProgressPause) as failure:branch_review.checkpoint(engine,runtime,{})
        detail=branch_pause.classify(failure.exception,task)
        self.assertIn('same unchanged evidence three times',detail['explanation'])
        self.assertIn('already requested a focused reassessment',detail['explanation'])
        self.assertEqual(detail['next_action'],'inspect');self.assertEqual(detail['stage'],'reviewing')
        self.assertEqual(engine.request.call_count,3)
        restored=json.loads(json.dumps(task));runtime.task=restored
        # Mirrors the engine wrapper which retains only progress_limit and saved task state.
        restored['error_code']='progress_limit'
        detail=branch_pause.classify(ValueError('outer wrapper'),restored)
        self.assertIn('same unchanged evidence',detail['explanation'])
        with self.assertRaises(ProgressPause):branch_review.checkpoint(engine,runtime,{})
        self.assertEqual(engine.request.call_count,3)
        self.assertEqual(len([e for e in restored['events'] if e['kind']=='review_coaching']),1)
        self.assertNotIn('ready_receipt',restored['branch_run']['items'][0])

    def test_repeated_tool_error_does_not_claim_the_same_file_was_read_successfully(self):
        task,engine,runtime=self.fixture()
        engine.file_tool.return_value={'error':'Requested directory is missing'}
        engine.request.return_value={'tool_calls':[{'id':'read','name':'list_files','result':{'path':'missing'}}]}
        with self.assertRaisesRegex(ProgressPause,'same failed tool action'):branch_review.checkpoint(engine,runtime,{})
        self.assertEqual(task['pending_review']['coaching']['reason'],'repeated_tool_error')
        self.assertEqual(engine.request.call_count,3)

    def test_empty_responses_receive_guidance_but_never_count_as_approval(self):
        task,engine,runtime=self.fixture();engine.request.return_value={'content':'Still considering it.'}
        with self.assertRaisesRegex(ProgressPause,'no usable review action'):branch_review.checkpoint(engine,runtime,{})
        self.assertEqual(engine.request.call_count,3)
        self.assertEqual(task['pending_review']['stop_diagnostic']['reason'],'missing_decision')
        branch_review.evidence.ready_receipt.assert_not_called()


if __name__ == '__main__': unittest.main()
