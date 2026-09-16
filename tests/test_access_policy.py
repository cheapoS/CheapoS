from cheapos.routing import PROBE_MARKER
"""Access classification/scope cases without Git, inference or process fixtures."""
import copy
import json
import io
from urllib.error import HTTPError
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from types import SimpleNamespace

from cheapos import access_policy as access, routing
from cheapos.omniroute import OmniRouteManager
from cheapos.providers import validate_provider, http_failure
from cheapos.gateways import normalize_models
from cheapos.engine import request_worker_turns


class AccessTests(unittest.TestCase):
    def policy(self):
        return {'version': 1, 'base_url': 'http://127.0.0.1:20128/v1',
                'connection_revision': 'a'*32, 'included_models': ['account/model']}

    def test_planner_binding_is_captured_at_creation_and_enforced(self):
        policy = self.policy()
        for included in (False, True):
            model = {'id': 'account/model' if included else 'free', 'free': not included, 'tool_calling': True}
            config = {'gateway': 'omniroute', 'base_url': policy['base_url'], 'model': model['id']}
            task = {'conversational': True}
            routing.setup_task(task, {'mode': 'remote'}, {'reviewer': config}, SimpleNamespace(settings=policy))
            planner = task['providers']['planner']
            access.guard(task, planner, policy, [model], role='planner')
            for change in ({'base_url': 'http://127.0.0.1:20129/v1'}, {'access_binding': None},
                           {'access_binding': {**policy, 'connection_revision': 'stale'}}):
                with self.subTest(included=included, change=change), self.assertRaises(ValueError):
                    access.guard(task, {**planner, **change}, policy, [model], role='planner')
            with self.assertRaises(ValueError):
                access.guard(task, planner, policy, [{**model, 'tool_calling': False}], role='planner')
            with self.assertRaises(ValueError):
                access.guard(task, planner, {**policy, 'included_models': []}, [model], role='planner')
        access.guard({}, {'model': 'paid', 'input_rate': 10}, policy, role='planner')

    def test_classification_never_rewrites_catalog_pricing(self):
        models = normalize_models({'data': [
            {'id':'unknown'}, {'id':'account/model','pricing':{'prompt':'.00001','completion':'.00002'}},
            {'id':'free','pricing':{'prompt':'0','completion':'0'}}, {'id':'local','owned_by':'ollama'},
            {'id':'one-sided','pricing':{'prompt':'0'}}]})
        original = copy.deepcopy(models)
        self.assertEqual({m['id']:access.classify(m,self.policy()) for m in models},
                         {'unknown':'unknown','account/model':'included','free':'public_free','local':'local','one-sided':'unknown'})
        self.assertEqual(models,original)
        included = next(m for m in models if m['id']=='account/model')
        self.assertFalse(included['free'])
        self.assertEqual(included['input_rate'],10)
        self.assertFalse(access.eligible(included,self.policy()))  # No advertised tools.

    def test_settings_refresh_persistence_and_connection_revocation(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = OmniRouteManager(directory)
            revision = manager.settings['connection_revision']
            manager.configure({'included_models':['account/model'],'expected_connection_revision':revision})
            manager.configure({'auto_start':False})
            self.assertEqual(manager.settings['included_models'],['account/model'])
            self.assertEqual(OmniRouteManager(directory).settings,manager.settings)
            manager.models = [{'id':'account/model','free':False,'tool_calling':True}]
            self.assertEqual(manager.catalog()['models'][0]['access_class'],'included')
            with self.assertRaises(ValueError): manager.configure({'included_models':['other'],'expected_connection_revision':'stale'})
            manager.configure({'api_key':'synthetic-client-key'})
            self.assertNotEqual(manager.settings['connection_revision'],revision)
            self.assertEqual(manager.settings['included_models'],[])
            self.assertNotIn('synthetic-client-key',(Path(directory)/'gateway.json').read_text())
            revision=manager.settings['connection_revision']
            manager.configure({'included_models':['account/model'],'expected_connection_revision':revision})
            manager.configure({'base_url':'http://127.0.0.1:20129/v1'})
            self.assertEqual(manager.settings['included_models'],[])
            self.assertNotEqual(manager.settings['connection_revision'],revision)

    def test_exact_scope_excludes_alias_expansion_new_models_and_stale_bindings(self):
        for ids in (['auto/anything'],['provider/*'],[' provider/model'],['provider/?'],['a\nb'],['openrouter/deepseek/deepseek-chat']):
            with self.assertRaises(ValueError): access.model_ids(ids)
        model={'id':'account/model','free':False,'tool_calling':True}
        self.assertTrue(access.eligible(model,self.policy()))
        for changed in ({'id':'account/new'},{'id':'auto/best-free'},{'local':True},{'provider':'combo'},{'tool_calling':False}):
            self.assertFalse(access.eligible({**model,**changed},self.policy()))
        config=validate_provider({'base_url':self.policy()['base_url'],'gateway':'omniroute','model':'account/model','access':'included'},'worker')
        config=access.bind_provider(config,self.policy(),model)
        self.assertEqual(config['pricing_source'],'operator_included')
        self.assertEqual((config['input_rate'],config['output_rate']),(0,0))
        task={'access_policy':self.policy(),'route':{'access_policy':self.policy()}}
        settings={**self.policy()}
        access.guard(task,config,settings,[model])
        for changed in ({'connection_revision':'b'*32},{'base_url':'http://127.0.0.1:2/v1'},{'included_models':['account/model','new']}):
            with self.assertRaises(ValueError): access.guard(task,config,{**settings,**changed},[model])
        with self.assertRaises(ValueError): access.guard(task,{**config,'model':'unknown'},settings,[model])
        with self.assertRaises(ValueError): access.guard(task,{k:v for k,v in config.items() if k!='access'},settings,[model])
        with self.assertRaises(ValueError): access.guard(task,config,settings,[])
        access.guard({}, {'model':'legacy'}, settings)  # Old tasks are not migrated.

    def test_remote_selection_uses_included_scope_before_probe(self):
        policy=self.policy(); models=[{'id':'unknown','free':False,'tool_calling':True},
                                    {'id':'account/model','free':False,'tool_calling':True}]
        task={'conversational':True,'providers':{'worker':None,'reviewer':None},'events':[],
              'route':{'base_url':policy['base_url'],'access_policy':policy},'access_policy':policy}
        pool=SimpleNamespace(observation=lambda *a:{'cooling_down':False,'tool_check_passed':True,'tool_check_at':time.time(),'tool_connection_revision':'old'},rank=lambda *a:0,record=Mock())
        gateway=SimpleNamespace(settings=policy,matches=lambda u:True,catalog=lambda **k:{'status':'ready','models':models},pool=pool)
        engine=SimpleNamespace(gateway=gateway,event=Mock(),store=SimpleNamespace(save=Mock()),
                               request=Mock(return_value={'tool_calls':[{'id':'probe'}]}),parse_call=lambda c:('routing_ready',{'marker': PROBE_MARKER}))
        cache={'valid':False}
        pool.fresh_probe=lambda *a:cache['valid']
        pool.claim_probe=lambda *a:(True,None)
        pool.release_probe=Mock()
        pool.record.side_effect=lambda *a,**kw:cache.update(valid=True)
        runtime=SimpleNamespace(task=task,failed_models=set())
        routing.select_remote(engine,runtime)
        self.assertEqual(engine.request.call_count,1)
        config=engine.request.call_args.kwargs['config_override']
        access.guard(task,config,policy,models)
        self.assertEqual(config['model'],'account/model')
        self.assertEqual(task['providers']['worker']['access'],'included')
        self.assertEqual(pool.record.call_args.kwargs['connection_revision'],policy['connection_revision'])
        task['providers']['worker']=None
        pool.observation=lambda *a:{'cooling_down':False,'tool_check_passed':True,'tool_check_at':time.time(),'tool_connection_revision':policy['connection_revision']}
        routing.select_remote(engine,runtime)
        self.assertEqual(engine.request.call_count,1)  # Matching scoped probe can be reused.

    def test_planning_model_does_not_reserve_independent_reviewer(self):
        policy = self.policy()
        for planner_id in ('B', 'C'):
            task = {'providers': {'worker': None, 'reviewer': None, 'planner': {'model': planner_id}},
                    'events': [], 'route': {'base_url': policy['base_url'], 'access_policy': policy,
                                           'preferred': {'worker': 'A', 'reviewer': 'B'}}}
            models = [{'id': name, 'free': True, 'tool_calling': True} for name in ('A', 'B')]
            pool = SimpleNamespace(observation=lambda *a: {'cooling_down': False},
                                   rank=lambda base, model, role, preferred, revision: model['id'] != preferred,
                                   fresh_probe=lambda *a: True)
            gateway = SimpleNamespace(settings=policy, matches=lambda url: True, pool=pool,
                                      catalog=lambda **k: {'status': 'ready', 'models': models})
            engine = SimpleNamespace(gateway=gateway, event=Mock(), store=SimpleNamespace(save=Mock()), request=Mock())
            runtime = SimpleNamespace(task=task, failed_models=set())
            routing.select_remote(engine, runtime, 'worker')
            routing.select_remote(engine, runtime, 'reviewer')
            self.assertEqual(task['providers']['worker']['model'], 'A')
            self.assertEqual(task['providers']['reviewer']['model'], 'B')
            task['events'] = [{'kind': 'tool', 'title': 'write file', 'detail': {'model': 'B'}}]
            with self.assertRaises(routing.RoutingPause):
                routing.select_remote(engine, runtime, 'reviewer', replace=True)
            engine.request.assert_not_called()

    def test_proposal_binds_connection_scope_without_rewriting_legacy_contracts(self):
        from cheapos.branch_controller import BranchController
        from cheapos.branch_authorization import ProposalRegistry
        from cheapos.branch_runs import new_run
        controller=BranchController.__new__(BranchController)
        controller.engine=SimpleNamespace(preferences=lambda:{'execution':{'mode':'manual'}},config={},
                                          gateway=SimpleNamespace(settings=self.policy()))
        run=new_run({'items':[{'id':'one','title':'One','instructions':'Do one','acceptance_criteria':['Works']}], 'limits':{'dollars':0}})
        run.update(authorization_workspace={},check_scope=[],model_policy=controller.model_policy())
        task={'branch_run':run}
        contract=controller.contract(task)
        registry=ProposalRegistry();proposal=registry.prepare('task',contract)
        controller.engine.gateway.settings={**self.policy(),'connection_revision':'b'*32}
        with self.assertRaises(ValueError):registry.authorize('task',proposal['proposal_id'],True,controller.contract(task))
        run['model_policy'].pop('gateway_access')
        self.assertNotIn('gateway_access',controller.contract(task)['model_policy'])

    def test_quota_scope_needs_shared_metadata_and_unknown_reset_stays_unknown(self):
        for code, expected in ((None, 'model'), ('model_cooldown', 'model'), ('provider_cooldown', 'provider')):
            response=HTTPError('http://localhost/v1',429,'quota',{},io.BytesIO(json.dumps({'error':{'code':code,'message':'private account'}}).encode()))
            error=http_failure(response,{'gateway':'omniroute'})
            self.assertEqual(error.scope,expected)
            self.assertIsNone(error.retry_after)
            self.assertIn('unknown',str(error))
            self.assertNotIn('private',str(error))

    def test_included_probe_title_matches_legacy_turn_accounting(self):
        # Both probe labels must have exactly the same recovery accounting effect.
        def count(label):
            return request_worker_turns({'conversational':True,'worker_turns':1,'events':[
                {'kind':'routing','title':label}, {'kind':'model','title':'Requesting worker: example'}]})
        self.assertEqual(count('Checking included worker'),count('Checking a free worker'))


if __name__=='__main__':unittest.main()
