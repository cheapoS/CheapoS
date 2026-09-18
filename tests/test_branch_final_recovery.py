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
        packet={'evidence':'exact evidence '*6000}
        def respond(rt,messages,tools,role,**kwargs):
            sent=json.loads(messages[1]['content'])
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
