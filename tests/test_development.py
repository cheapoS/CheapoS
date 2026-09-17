"""Development opt-in and finite routing selection without model requests."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from cheapos import route_schedule
from cheapos.development import enabled
from cheapos.branch_authorization import digest
from cheapos.providers import ProviderError
from cheapos.routing import execution_from, select_remote, RoutingPause, PROBE_MARKER


class DevelopmentTests(unittest.TestCase):
    def test_defaults_and_approved_run_require_explicit_bound_receipt(self):
        self.assertFalse(execution_from({})['development_mode'])
        with self.assertRaises(ValueError):execution_from({'development_mode':'true'})
        task={'execution':{'development_mode':True}}
        self.assertTrue(enabled(task))
        plan={'items':['saved']}
        task['branch_run']={'authorization_ref':'auth','authorization':{'contract':{'plan':plan,'model_policy':{'execution':{}}}}}
        self.assertFalse(enabled(task))
        task['branch_run']['development_authorization']={'enabled':True,'authorization_ref':'auth','plan_digest':digest(plan)}
        self.assertTrue(enabled(task))
        task['branch_run']['authorization']['contract']['plan']={'items':['changed']}
        self.assertFalse(enabled(task))
        task['branch_run']['authorization']['contract']['model_policy']['execution']['development_mode']=True
        self.assertTrue(enabled(task))
        task['execution']['development_mode']=False
        self.assertFalse(enabled(task))

    def test_more_than_four_probes_remains_finite_and_preserves_history(self):
        models=[{'id':f'provider{n}/model','free':True,'tool_calling':True} for n in range(6)]
        policy={'version':1,'base_url':'http://127.0.0.1:20128/v1','connection_revision':'a'*32,'included_models':[]}
        def run(development):
            task={'execution':{'mode':'remote','development_mode':development},'providers':{'worker':None,'reviewer':None},'events':[],
                  'route':{'base_url':policy['base_url'],'access_policy':policy,'failures':[{'model':'previous','error':'retained'}]},'access_policy':policy,
                  'progress_state':{'route_probes':{'worker':4}}}
            pool=SimpleNamespace(observation=lambda *a:{'cooling_down':False},rank=lambda *a:0,fresh_probe=lambda *a:False,claim_probe=lambda *a:(True,None),release_probe=Mock(),record=Mock())
            gateway=SimpleNamespace(settings=policy,matches=lambda _:True,catalog=lambda **k:{'status':'ready','models':models},pool=pool)
            engine=SimpleNamespace(gateway=gateway,event=Mock(),store=SimpleNamespace(save=Mock()),request=Mock(return_value={'tool_calls':[{'id':'probe'}]}),parse_call=lambda _:('routing_ready',{'marker':PROBE_MARKER}))
            runtime=SimpleNamespace(task=task,failed_models=set())
            with patch('cheapos.route_schedule.time.time',return_value=1000) as clock:
                select_remote(engine,runtime)
                self.assertEqual(task['providers']['worker']['model'],'provider0/model')
                self.assertEqual(task['progress_state']['route_probes']['worker'],5)
                if development:
                    self.assertEqual(task['route']['failure_history'][0]['model'],'previous')
                task['providers']['worker']=None
                engine.request.reset_mock()
                engine.request.side_effect=ProviderError('Invalid tool output',code='unsupported_tool')
                clock.return_value += route_schedule.ROUND_SECONDS
                with self.assertRaises(RoutingPause) as paused:select_remote(engine,runtime)
                self.assertEqual(paused.exception.scope,'probe_capacity')
                self.assertEqual(engine.request.call_count,route_schedule.BATCH_SIZE)
                clock.return_value = paused.exception.retry_at
                with self.assertRaises(RoutingPause) as exhausted:select_remote(engine,runtime)
                self.assertIn('No eligible independent model remains',str(exhausted.exception))
                self.assertIsNone(exhausted.exception.retry_at)
            self.assertEqual(engine.request.call_count,len(models))
            self.assertEqual(task['progress_state']['route_probes']['worker'],11)
            attempted=[call.kwargs['config_override']['model'] for call in engine.request.call_args_list]
            self.assertEqual(attempted,[model['id'] for model in models])
            if development:
                failures=task['route']['failure_history'] + task['route']['failures']
                self.assertEqual([failure['model'] for failure in failures],['previous'] + attempted)
        for development in (False, True):
            with self.subTest(development=development):
                run(development)

    def test_review_retries_keep_claims_and_require_real_decision(self):
        from cheapos import branch_disagreement, branch_review, review_disputes
        from cheapos.engine import ProgressPause
        from cheapos.branch_pause import PauseError
        from test_branch_disagreement import defect
        task={'execution':{'development_mode':True},'branch_run':{'review_disagreements':{'candidate':{'unsupported_attempts':9}}},'pending_review':{'stop_diagnostic':{'reason':'invalid_decision'}},'checks':[]}
        original=copy.deepcopy(task['pending_review'])
        branch_disagreement.ensure_available(task,'candidate')
        branch_review._stop(None,task,'invalid_decision')
        self.assertEqual(task['pending_review'],original)
        item={'id':'one','acceptance_criteria':['exact values']}
        for n in range(5):
            branch_disagreement.attach(task,item,{'candidate_id':str(n),'defects':[defect()]})
        records=task['branch_run']['dispute_ledger']['findings']
        self.assertEqual(next(iter(records.values()))['attempts'],5)
        self.assertEqual(next(iter(records.values()))['status'],'requested')
        self.assertEqual(next(iter(task['branch_run']['repair_claims'].values())),5)
        with self.assertRaises(ValueError):branch_disagreement.decision({'decision':'APPROVE','defects':[defect()]})
        task['execution']['development_mode']=False
        with self.assertRaises(ProgressPause):branch_disagreement.ensure_available(task,'candidate')
        with self.assertRaises(ProgressPause):branch_disagreement.attach(task,item,{'candidate_id':'6','defects':[defect()]})
        task['execution']['development_mode']=True
        task['branch_run']['dispute_ledger']['findings']={str(n):{} for n in range(96)}
        with self.assertRaises(PauseError):review_disputes.register(task,item,{'candidate_id':'7','defects':[defect()]})

    def test_operator_worker_choice_stays_pinned(self):
        from cheapos.model_pool import automatic
        task={'execution':{'mode':'remote'},'route':{'base_url':'gateway'},'providers':{'worker':{'model':'chosen'}},'operator_worker_model':'chosen'}
        self.assertFalse(automatic(task,'worker'))
        self.assertTrue(automatic(task,'reviewer'))
        task['providers']['worker']['model']='another'
        self.assertTrue(automatic(task,'worker'))

    def test_final_review_exceeds_old_caps_without_implying_approval(self):
        from cheapos import branch_final
        from unittest.mock import patch
        task={'execution':{'development_mode':True},'branch_run':{}}
        runtime=SimpleNamespace(task=task,guard=Mock())
        result={'manifest_id':'m','chunk_ids':[],'criteria_ids':[],'decision':'APPROVE','feedback':'Evidence reviewed'}
        read={'manifest_id':'m','path':'a.py','start_line':1,'end_line':2}
        messages=[{'tool_calls':[{'id':str(n),'name':'final_review_decision','result':dict(result,decision='invalid')}]} for n in range(4)]
        messages += [{'tool_calls':[{'id':str(n),'name':'read_final_context','result':read}]} for n in range(7)]
        messages += [{'tool_calls':[{'id':'done','name':'final_review_decision','result':result}]}]
        engine=SimpleNamespace(store=SimpleNamespace(save=Mock()),event=Mock(),request=Mock(side_effect=messages),parse_call=lambda c:(c['name'],c['result']))
        with patch.object(branch_final.review_context,'read',return_value={'path':'a.py','available':True,'content':'saved source'}) as read_context:
            reviewed=branch_final._review(engine,runtime,{'id':'m'}, {}, [], [])
        self.assertEqual(reviewed['decision'],'APPROVE')
        self.assertEqual(engine.request.call_count,12)
        self.assertEqual(next(iter(task['branch_run']['final_review_corrections'].values())),4)
        self.assertEqual(next(iter(task['branch_run']['final_context_reads'].values()))['count'],7)
        read_context.assert_called_once()
        self.assertIn('This exact context is already available',str(engine.request.call_args.args[1]))
