"""Pure operator recovery contracts; no repositories, providers or waits."""
import copy
import threading
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from cheapos import branch_runs
from cheapos.branch_authorization import ProposalRegistry, contract_builder, digest
from cheapos.branch_operator import control, recover, continue_saved, revision_token
from cheapos.development import enabled


class BranchOperatorTests(unittest.TestCase):
    def setUp(self):
        plan={'items':[{'id':'one','title':'One','instructions':'Original','acceptance_criteria':['Works'],'required_checks':['python3 test.py']}],
              'limits':{'dollars':0,'working_seconds':90},'final_checks':['python3 test.py']}
        run=branch_runs.new_run(plan,run_id='task',original_request='Work',project={'source':'/repo'})
        run.update(status='paused',current_item_id='one',expected_feature_tip='tip',workspace_mapping={'source':'/repo'},authorization_workspace={},check_scope=[])
        run['model_policy']={'execution':{'mode':'manual'},'providers':{'worker':{'model':'worker'},'reviewer':{'model':'reviewer'}}}
        registry=ProposalRegistry()
        contract=contract_builder(run,{},run['model_policy'],[])
        proposal=registry.prepare('task',contract);auth=registry.authorize('task',proposal['proposal_id'],True,contract)
        run.update(authorization=auth,authorization_ref=auth['id'])
        self.task={'id':'task','source':'/repo','status':'paused','execution':{'mode':'manual'},'branch_run':run,
                   'providers':copy.deepcopy(run['model_policy']['providers']),'usage':{'cost':0,'worker':{'tokens':13}},'events':[]}
        self.saved=copy.deepcopy(self.task)
        self.engine=SimpleNamespace(lock=threading.RLock(),admission=SimpleNamespace(require_idle=lambda _:None),require_active_task=lambda _:None,
            store=SimpleNamespace(get=lambda _:copy.deepcopy(self.saved),save=self.save),gateway=SimpleNamespace(settings={}))
        self.engine.event=lambda task,*args:self.save(task)
        self.controller=SimpleNamespace(engine=self.engine,proposals=registry,validate_authority=lambda task,run:registry.validate(run['authorization'],contract_builder(run,{},run['model_policy'],[])),
            resume=Mock(return_value={'needs_consent':True,'proposal_id':'consent','scopes':[['python3','test.py']]}),message=Mock(side_effect=lambda task_id,values:self.engine.store.get(task_id)))

    def save(self, task):self.saved=copy.deepcopy(task)

    def test_opt_in_requires_explicit_approval_and_retains_usage_scope(self):
        with self.assertRaises(ValueError):control(self.controller,'task',{'action':'enable'})
        self.saved['operator_bounded_work']=True
        task=control(self.controller,'task',{'action':'enable','approved':True})
        self.assertFalse(task['operator_bounded_work'])
        self.assertTrue(enabled(task));self.assertEqual(task['usage'],self.task['usage'])
        self.assertEqual(task['branch_run']['authorization'],self.task['branch_run']['authorization'])
        task['branch_run']['authorization_ref']='different'
        self.assertFalse(enabled(task))

    def test_legacy_controls_sync_captured_setup_after_explicit_authority_change(self):
        import sys
        self.saved['settings_snapshot']={'revision':1,'values':{}}
        seen=[]
        helper=SimpleNamespace(sync_saved=lambda task:seen.append((task['execution'].get('development_mode'),task['branch_run']['authorization_ref'])))
        with patch.dict(sys.modules,{'cheapos.task_settings':helper}):
            control(self.controller,'task',{'action':'enable','approved':True})
            before=self.saved['branch_run']['authorization_ref']
            with patch('cheapos.branch_workspace.validate_owned'):
                recover(self.controller,'task',{'action':'revise','approved':True,'revision_token':revision_token(self.saved['branch_run'],self.saved),'instructions':'Refined original scope','resume':False})
        self.assertEqual(len(seen),2)
        self.assertTrue(seen[0][0]);self.assertNotEqual(seen[1][1],before)

    def test_saved_guidance_reports_consent_and_precise_blocker_without_dispatch(self):
        task=continue_saved(self.controller,'task')
        self.assertEqual(task['operator_continue']['status'],'needs_consent')
        self.assertEqual(task['operator_continue']['proposal_id'],'consent')
        self.controller.resume.side_effect=ValueError('Project identity changed')
        task=continue_saved(self.controller,'task')
        self.assertIn('Project identity changed',task['operator_continue']['reason'])
        self.assertEqual(task['usage'],self.task['usage'])

    def test_revision_reauthorizes_only_current_instructions_preserving_original_evidence(self):
        control(self.controller,'task',{'action':'enable','approved':True})
        original=copy.deepcopy(self.saved)
        with patch('cheapos.branch_workspace.validate_owned'):
            task=recover(self.controller,'task',{'action':'revise','approved':True,'revision_token':revision_token(self.saved['branch_run'],self.saved),'instructions':'Revised instructions'})
        run=task['branch_run']
        self.assertEqual(run['plan']['items'][0]['instructions'],'Revised instructions')
        self.assertEqual(run['operator_revision_history'][0]['item']['instructions'],'Original')
        self.assertEqual(run['plan']['limits'],original['branch_run']['plan']['limits'])
        self.assertEqual(run['plan']['items'][0]['required_checks'],original['branch_run']['plan']['items'][0]['required_checks'])
        self.assertEqual(task['usage'],original['usage']);self.assertTrue(enabled(task))
        self.assertNotEqual(run['authorization_ref'],original['branch_run']['authorization_ref'])
        self.controller.validate_authority(task,run)
        run['plan']['items'][0]['required_checks']=['echo bypass']
        with self.assertRaises(ValueError):self.controller.validate_authority(task,run)

    def test_no_arbitrary_fields_or_committed_item_revision(self):
        control(self.controller,'task',{'action':'enable','approved':True})
        with self.assertRaises(ValueError):recover(self.controller,'task',{'action':'revise','approved':True,'revision_token':revision_token(self.saved['branch_run'],self.saved),'instructions':'x','limits':{'dollars':100}})
        self.saved['branch_run']['items'][0]['commit_receipt']={'id':'committed'}
        with patch('cheapos.branch_workspace.validate_owned'):
            with self.assertRaisesRegex(ValueError,'uncommitted'):recover(self.controller,'task',{'action':'revise','approved':True,'revision_token':revision_token(self.saved['branch_run'],self.saved),'instructions':'x'})

    def test_model_replacement_requires_eligible_same_gateway_distinct_reviewer(self):
        self.engine.gateway.settings={'base_url':'http://127.0.0.1:20128/v1'}
        self.engine.gateway.catalog=lambda **kwargs:{'status':'ready','models':[
            {'id':'free-worker','free':True,'tool_calling':True},
            {'id':'reviewer','free':True,'tool_calling':True},
            {'id':'paid','input_rate':2,'output_rate':3,'tool_calling':True}]}
        self.saved['providers']['worker'].update(gateway='omniroute',base_url='http://127.0.0.1:20128/v1')
        control(self.controller,'task',{'action':'enable','approved':True})
        before=copy.deepcopy(self.saved)
        with patch('cheapos.branch_workspace.validate_owned'):
            for model in ('paid','reviewer'):
                with self.assertRaisesRegex(ValueError,'eligible'):recover(self.controller,'task',{'action':'model','approved':True,'revision_token':revision_token(self.saved['branch_run'],self.saved),'model':model})
            task=recover(self.controller,'task',{'action':'model','approved':True,'revision_token':revision_token(self.saved['branch_run'],self.saved),'model':'free-worker'})
        self.assertEqual(task['providers']['worker']['model'],'free-worker')
        self.assertEqual(task['providers']['reviewer'],before['providers']['reviewer'])
        self.assertEqual(task['branch_run']['limits'],before['branch_run']['limits'])
        self.assertEqual(task['usage'],before['usage'])
        from cheapos.branch_controller import BranchController
        self.controller.model_policy=lambda:{'changed':'global settings are not the explicit amendment'}
        contract=BranchController.contract(self.controller,task)
        self.controller.proposals.validate(task['branch_run']['authorization'],contract)

    def test_development_final_repairs_continue_past_three_with_valid_original_scope(self):
        from cheapos import branch_completion as completion
        control(self.controller,'task',{'action':'enable','approved':True})
        task=copy.deepcopy(self.saved);run=task['branch_run']
        for count in range(4):
            repair=completion._repair_item(run,'Correct the original failure',['one:1'])
            completion._append_repair(self.engine,task,repair,'operator','explicit-'+str(count),{'request':'Correct'},['one:1'])
        self.assertEqual(len(run['amendments']),4)
        projected=completion.authorization_run(run)
        self.assertEqual(projected['plan'],run['authorization']['contract']['plan'])
        run['development_authorization']['enabled']=False
        with self.assertRaises(ValueError):completion.authorization_run(run)

    def test_chat_correction_automatically_attempts_resume_and_retains_consent_requirement(self):
        from cheapos.branch_controller import BranchController
        control(self.controller,'task',{'action':'enable','approved':True})
        self.engine.runtimes={};self.engine.archive_operator_state=Mock()
        task=BranchController.message(self.controller,'task',{'message':'Use the existing parser fixture and repair the failing assertion.'})
        self.controller.resume.assert_called_once_with('task',{})
        self.assertIn('existing parser',task['branch_run']['guidance'][-1]['message'])
        self.assertEqual(task['operator_continue']['status'],'needs_consent')
        self.assertEqual(task['usage']['worker']['tokens'],13)
        self.engine.archive_operator_state.assert_called_once()

    def test_takeover_explicitly_regrants_captured_commands_and_continues(self):
        self.saved['branch_run']['check_scope']=[{'command':['python3','test.py']}]
        self.controller.validate_authority=Mock()
        self.controller.scopes=SimpleNamespace(prepare=Mock(return_value={'command':['python3','test.py'],'identity':'current'}),consent=Mock())
        from cheapos.uploads import save_upload
        with tempfile.TemporaryDirectory() as directory:
            self.engine.store.root=directory
            record=save_upload(directory,'correction.png',b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR')
            with self.assertRaisesRegex(ValueError,'Attachments must be a list'):
                recover(self.controller,'task',{'action':'takeover','approved':True,'message':'Apply my correction now','attachments':'bad'})
            self.assertFalse(enabled(self.saved))
            task=recover(self.controller,'task',{'action':'takeover','approved':True,'message':'Apply my correction now','attachments':[record]})
        self.assertTrue(enabled(task))
        self.controller.scopes.consent.assert_called_once()
        self.assertEqual(self.controller.scopes.consent.call_args.args[1]['identity'],'current')
        self.controller.message.assert_called_once_with('task',{'message':'Apply my correction now','attachments':[record]})

    def test_final_review_redirect_reenters_same_runtime_without_pausing(self):
        from cheapos.branch_controller import BranchController
        from cheapos.engine import OperatorRedirect
        task=copy.deepcopy(self.saved);task['branch_run']['status']='running';task['branch_run']['items'][0]['status']='satisfied_without_change'
        runtime=SimpleNamespace(task=task,stop=threading.Event(),guard=Mock())
        self.engine.apply_operator_direction=Mock()
        self.engine.gateway.pool=Mock()
        self.controller.commit_item=Mock()
        with patch('cheapos.branch_budget.Ledger') as ledger, patch('cheapos.branch_controller.work.validate_owned'), \
             patch('cheapos.branch_completion.finalize',side_effect=[OperatorRedirect('new direction'),True]) as final, \
             patch('cheapos.model_pool.observe_task'),patch('cheapos.model_pool.observe_completions'):
            BranchController.execute(self.controller,runtime)
        self.assertEqual(final.call_count,2)
        self.engine.apply_operator_direction.assert_called_once_with(runtime)
        self.assertNotEqual(task['branch_run']['pause_reason'],'operator')
        self.assertFalse(runtime.stop.is_set())

    def test_final_reviewer_receives_latest_direction_without_synthetic_approval(self):
        from cheapos import branch_final
        task=copy.deepcopy(self.saved);task['branch_run']['guidance']=[{'message':'Use the regression evidence and check the actual requirement.'}]
        runtime=SimpleNamespace(task=task,guard=Mock())
        engine=SimpleNamespace(event=Mock(),store=SimpleNamespace(save=Mock()),
                               request=Mock(side_effect=RuntimeError('fixture stops before inference')))
        with self.assertRaisesRegex(RuntimeError,'fixture stops'):
            branch_final._review(engine,runtime,{'id':'candidate','requirements':[]},{},[],[])
        messages=engine.request.call_args.args[1]
        self.assertIn('regression evidence',messages[-1]['content'])
        self.assertIn('not approval',messages[-1]['content'])

    def test_revision_keeps_committed_sibling_and_rejection_does_not_change_saved_state(self):
        sibling={'id':'two','title':'Two','instructions':'Keep this completed work','acceptance_criteria':['Done'],'required_checks':['python3 test.py'],'dependencies':[]}
        run=self.saved['branch_run'];run['plan']['items'].append(copy.deepcopy(sibling))
        committed={**sibling,'status':'committed','commit_receipt':{'id':'saved-receipt','new_tip':'tip'},'evidence':{'passed':True}}
        run['items'].append(copy.deepcopy(committed));run['plan_digest']=digest(run['plan'])
        contract=contract_builder(run,{},run['model_policy'],[])
        proposal=self.controller.proposals.prepare('task',contract)
        auth=self.controller.proposals.authorize('task',proposal['proposal_id'],True,contract)
        run.update(authorization=auth,authorization_ref=auth['id'])
        control(self.controller,'task',{'action':'enable','approved':True})
        before=copy.deepcopy(self.saved)
        with patch('cheapos.branch_workspace.validate_owned'):
            with self.assertRaises(ValueError):recover(self.controller,'task',{'action':'revise','approved':True,'revision_token':revision_token(run,self.saved),'instructions':'x'*4001})
            self.assertEqual(self.saved,before)
            task=recover(self.controller,'task',{'action':'revise','approved':True,'revision_token':revision_token(self.saved['branch_run'],self.saved),'instructions':'Repair only current item'})
        self.assertEqual(task['branch_run']['items'][1],committed)

    def test_development_preference_does_not_change_existing_policy_snapshot(self):
        from cheapos.branch_controller import policy_for_saved
        for saved_execution in ({'mode':'manual'}, {'mode':'manual','development_mode':False}, {'mode':'manual','development_mode':True}):
            saved={'execution':saved_execution}
            for current in (False,True):
                policy={'execution':{'mode':'manual','development_mode':current}}
                self.assertEqual(policy_for_saved(policy,saved),saved)
                policy['execution']['mode']='remote'
                self.assertEqual(policy_for_saved(policy,saved)['execution']['mode'],'remote')

    def test_check_revision_preserves_history_and_requires_broad_consent(self):
        self.controller.scopes=SimpleNamespace(prepare=lambda task,c:{'command':c},consent=Mock())
        original=copy.deepcopy(self.saved)
        values={'action':'checks','approved':True,'revision_token':revision_token(self.saved['branch_run'],self.saved),
                'required_checks':['python3 -m unittest tests.test_http'],
                'final_checks':['python3 -m unittest discover -v tests']}
        with patch('cheapos.branch_workspace.validate_owned'):
            with self.assertRaisesRegex(ValueError,'Full-suite'):recover(self.controller,'task',values)
            self.assertEqual(self.saved,original)
            values['final_checks']=['python3 -m unittest tests.test_http']
            values['resume']=False
            task=recover(self.controller,'task',values)
        self.assertEqual(task['branch_run']['plan']['final_checks'],values['final_checks'])
        self.assertEqual(task['usage'],original['usage'])
        self.assertEqual(task['branch_run']['operator_revision_history'][-1]['authorization'],original['branch_run']['authorization'])
        self.assertEqual(task['full_suite_approval'],[])
        self.controller.message.assert_not_called()
        self.assertEqual(task['operator_continue']['status'],'ready')
        run=task['branch_run']
        self.controller.proposals.validate(run['authorization'],contract_builder(run,run['authorization_workspace'],run['model_policy'],run['check_scope']))

    def test_reviewer_only_amendment_preserves_checkpoint_item_and_messages_without_development(self):
        endpoint='http://127.0.0.1:20128/v1'
        self.engine.gateway.settings={'base_url':endpoint}
        self.engine.gateway.catalog=lambda **kwargs:{'models':[{'id':'fresh-reviewer','free':True,'tool_calling':True}]}
        self.saved['providers']['reviewer'].update(gateway='omniroute',base_url=endpoint)
        self.saved['pending_checkpoint']={'candidate_id':'candidate','checks':['saved']}
        self.saved['pending_review']={'id':'old-review','identity_scope':{'candidate_id':'candidate'}}
        self.saved['messages']=[{'role':'assistant','content':'Preserved work'}]
        item=self.saved['branch_run']['items'][0];item.update(status='reviewing',revision=4,evidence={'checks':'retained'})
        before=copy.deepcopy(self.saved)
        with patch('cheapos.branch_workspace.validate_owned'),patch('cheapos.reviewer_recovery.unknown_workers',return_value=[]),patch('cheapos.reviewer_recovery.candidates',return_value=[{'id':'fresh-reviewer'}]):
            task=recover(self.controller,'task',{'action':'reviewer','approved':True,'revision_token':revision_token(self.saved['branch_run'],self.saved),'model':'fresh-reviewer','resume':False})
        self.assertFalse(enabled(task))
        self.assertEqual(task['pending_checkpoint'],before['pending_checkpoint'])
        self.assertEqual(task['messages'],before['messages'])
        self.assertEqual(task['branch_run']['items'][0],before['branch_run']['items'][0])
        self.assertNotIn('pending_review',task)
        self.assertEqual(task['operator_review_history'][-1],before['pending_review'])
        self.assertEqual(task['providers']['reviewer']['model'],'fresh-reviewer')
        self.assertNotEqual(revision_token(task['branch_run'],task),revision_token(before['branch_run'],before))
        self.controller.message.assert_not_called()
