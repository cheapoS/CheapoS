"""Deterministic final-review continuation; no Git, sleeps or model requests."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_final as final, branch_review_recovery, routing
from cheapos.providers import BudgetError


class FinalRecoveryTests(unittest.TestCase):
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

    def select(self, engine, runtime, role, replace):
        self.assertEqual((role,replace),('reviewer',True))
        self.assertIn('reviewer',branch_review_recovery.failed_models(runtime.task))
        runtime.task['providers']['reviewer']={'model':'replacement'}

    def test_invalid_decisions_continue_without_worker_checks_or_allowance_reset(self):
        task,engine,runtime=self.fixture();before=copy.deepcopy(task);seen=[]
        def respond(rt,messages,tools,role,**kw):
            seen.append(copy.deepcopy(messages))
            return self.approval(task['providers']['reviewer']['model']=='reviewer')
        engine.request.side_effect=respond
        with patch.object(routing,'select_remote',side_effect=self.select) as select:
            result=self.review(engine,runtime)
        self.assertEqual(result['reviewer_model'],'replacement');select.assert_called_once()
        self.assertEqual(engine.request.call_count,4)
        self.assertIn('Return an explicit valid review decision',json.dumps(seen[-1]))
        self.assertIn('Prior model claims are untrusted',json.dumps(seen[-1]))
        history=task['branch_run']['final_review_recovery']['m']['history']
        self.assertEqual(len(history),1);self.assertEqual(len(history[0]['review']['messages']),6)
        self.assertEqual(next(iter(task['branch_run']['final_review_corrections'].values())),3)
        for key in ('usage','limits','checks'):self.assertEqual(task[key],before[key])
        for key in ('plan','items'):self.assertEqual(task['branch_run'][key],before['branch_run'][key])
        engine.checks.assert_not_called();engine.file_tool.assert_not_called()

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

    def test_handoff_cannot_accept_worker_as_reviewer(self):
        task,engine,runtime=self.fixture()
        engine.request.side_effect=[self.approval(True)]*3+[self.approval()]
        def select(e,rt,role,replace):rt.task['providers']['reviewer']['model']='worker'
        with patch.object(routing,'select_remote',side_effect=select), \
             self.assertRaisesRegex(ValueError,'not independent'):self.review(engine,runtime)
        self.assertFalse(any(p.get('result') for p in task['branch_run']['final_review_packets'].values()))
