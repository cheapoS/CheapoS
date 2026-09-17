"""Tiny injected-clock/state checks; no Git, inference, waits or HTTP server."""
import tempfile
import json
import unittest
from unittest.mock import patch
from cheapos import route_health as health
from cheapos.model_pool import FreeModelPool
from cheapos.providers import ProviderError

URL='http://localhost:20128/v1'
MODEL={'id':'provider/model','tool_calling':True,'context_length':10000}


class RouteHealthTests(unittest.TestCase):
    def test_local_budget_is_not_a_bad_model_response_or_retryable_outage(self):
        from cheapos.providers import BudgetError
        result = health.classify(BudgetError('Not enough task allowance'))
        self.assertEqual(result['category'], 'local_budget')
        self.assertFalse(result['retry'])
        self.assertFalse(result['quality_impact'])

    def test_cooldown_prefers_another_provider_over_a_preferred_cached_sibling(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from cheapos.routing import select_remote
        from cheapos.engine import Engine
        for alternative_fails in (False, True):
            with self.subTest(alternative_fails=alternative_fails), tempfile.TemporaryDirectory() as directory:
                models = [dict(MODEL, id=name, free=True) for name in
                          ('openrouter/gemma-a', 'openrouter/gemma-b', 'nvidia/coder')]
                models += [dict(MODEL, id='paid/coder', free=False),
                           dict(MODEL, id='local/coder', free=True, local=True)]
                task = {'providers': {'planner': {'model': 'openrouter/gemma-a'}}, 'events': [],
                        'route': {'base_url': URL, 'preferred': {'planner': 'openrouter/gemma-b'},
                                  'recovery': {'planner': {'from': 'openrouter/gemma-a', 'error_code': 'gateway_cooldown'}}}}
                pool = FreeModelPool(directory)
                pool.record(URL, models[0]['id'], 'planner', error=ProviderError('', code='gateway_cooldown', scope='model', retry_after=120))
                pool.record(URL, models[1]['id'], 'planner', probe=True, probe_identity=health.probe_identity(URL, models[1], None))
                gateway = SimpleNamespace(settings={}, pool=pool, matches=lambda url: True,
                                          catalog=lambda **kw: {'status': 'ready', 'models': models})
                response = {'tool_calls': [{'id': 'probe', 'function': {'name': 'routing_ready',
                             'arguments': json.dumps({'marker': health.PROBE_MARKER})}}]}
                def request(*args, **kwargs):
                    self.assertEqual(kwargs['config_override']['model'], 'nvidia/coder')
                    if alternative_fails: raise ProviderError('', code='http_503')
                    return response
                engine = SimpleNamespace(gateway=gateway, event=Mock(), store=Mock(), parse_call=Engine.parse_call,
                                         request=Mock(side_effect=request))
                select_remote(engine, SimpleNamespace(task=task, failed_models=set()), 'planner', replace=True)
                engine.request.assert_called_once()
                self.assertEqual(task['providers']['planner']['model'], 'openrouter/gemma-b' if alternative_fails else 'nvidia/coder')
                self.assertFalse(pool.observation(URL, 'openrouter/gemma-b')['cooling_down'])
                self.assertEqual(pool.observation(URL, 'openrouter/gemma-a').get('failures', 0), 0)

    def test_model_cooldown_during_probe_rotates_provider_before_second_sibling(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from cheapos.routing import select_remote
        from cheapos.engine import Engine
        with tempfile.TemporaryDirectory() as directory:
            models = [dict(MODEL, id=name, free=True) for name in
                      ('openrouter/gemma-a', 'openrouter/gemma-b', 'nvidia/coder')]
            pool = FreeModelPool(directory)
            # Both preferred and previously validated routes would normally rank first.
            pool.record(URL, models[1]['id'], 'worker', probe=True,
                        probe_identity=health.probe_identity(URL, models[1], None))
            task = {'providers': {}, 'events': [], 'route': {'base_url': URL, 'preferred': {'worker': models[0]['id']}}}
            gateway = SimpleNamespace(settings={}, pool=pool, matches=lambda url: True,
                                      catalog=lambda **kw: {'status': 'ready', 'models': models})
            calls = []
            def request(*args, **kwargs):
                name = kwargs['config_override']['model']; calls.append(name)
                if name.startswith('openrouter/'):
                    raise ProviderError('', code='gateway_cooldown', scope='model', retry_after=120)
                return {'tool_calls': [{'id': 'probe', 'function': {'name': 'routing_ready',
                        'arguments': json.dumps({'marker': health.PROBE_MARKER})}}]}
            engine = SimpleNamespace(gateway=gateway, event=Mock(), store=Mock(), parse_call=Engine.parse_call, request=request)
            select_remote(engine, SimpleNamespace(task=task, failed_models=set()), 'worker')
            self.assertEqual(calls, ['openrouter/gemma-a', 'nvidia/coder'])
            self.assertEqual(task['providers']['worker']['model'], 'nvidia/coder')

    def test_outage_selection_skips_provider_and_preserves_free_independent_selection(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from cheapos.routing import select_remote
        from cheapos.engine import Engine
        models=[dict(MODEL,id=name,free=free) for name,free in [
            ('down/one',True),('down/two',True),('paid/one',False),('author/one',True),('next/one',True)]]
        task={'providers':{'worker':{'model':'author/one'},'reviewer':{'model':'down/one'}},'events':[],
              'route':{'base_url':URL,'availability_recovery':{'reviewer':{'providers':['down'],'handoffs':0}}}}
        with tempfile.TemporaryDirectory() as directory:
            pool=FreeModelPool(directory)
            pool.record(URL,'down/one','reviewer',error=ProviderError('Cooling',code='gateway_cooldown',scope='provider',retry_after=120))
            gateway=SimpleNamespace(settings={},pool=pool,matches=lambda url:True,
                catalog=lambda **kw:{'status':'ready','models':models})
            response={'tool_calls':[{'id':'probe','function':{'name':'routing_ready',
                'arguments':json.dumps({'marker':health.PROBE_MARKER})}}]}
            engine=SimpleNamespace(gateway=gateway,event=Mock(),store=Mock(),parse_call=Engine.parse_call,
                                   request=Mock(return_value=response))
            runtime=SimpleNamespace(task=task,failed_models=set())
            select_remote(engine,runtime,'reviewer',replace=True)
            self.assertEqual(task['providers']['reviewer']['model'],'next/one')
            self.assertEqual(engine.request.call_count,1)
            self.assertEqual(task['progress_state']['route_probes']['reviewer'],1)

    def test_only_matching_review_outages_leave_decision_turns_available(self):
        from cheapos.provider_recovery import review_turns
        pending={'branch_candidate_id':'current','review_requests':8}
        failed={'id':'outage','role':'reviewer','purpose':'work','status':'failed',
                'dispatched':True,'error_code':'gateway_cooldown','review_candidate_id':'current'}
        task={'request_metrics':[failed]}
        self.assertEqual(review_turns(task,pending),7)
        for change in ({'review_candidate_id':'older'},{'role':'worker'},{'purpose':'probe'},
                       {'error_code':'invalid_tool_envelope'},{'status':'responded'},{'dispatched':False}):
            task['request_metrics']=[{**failed,**change}]
            self.assertEqual(review_turns(task,pending),8)
        # Historical saved candidate outages can be identified without editing usage.
        task.update(branch_run={'current_item_id':'one'},events=[{'kind':'checkpoint','time':'2026-09-14T10:00',
                    'detail':{'candidate_id':'current'}}])
        task['request_metrics']=[{**failed,'review_candidate_id':None,'branch_item_id':'one','requested_at':'2026-09-14T10:01'}]
        self.assertEqual(review_turns(task,pending),7)
        self.assertEqual(pending['review_requests'],8)

    def test_http_success_without_exact_required_tool_marker_is_not_capability_proof(self):
        from cheapos.engine import Engine
        def response(arguments):
            return {'tool_calls':[{'id':'probe','function':{'name':'routing_ready','arguments':json.dumps(arguments)}}]}
        for message in ({'content':'OK'},response({}),response({'marker':'wrong'}),response({'marker':health.PROBE_MARKER,'extra':True})):
            with self.assertRaises(ProviderError):health.validate_probe(message,Engine.parse_call)
        health.validate_probe(response({'marker':health.PROBE_MARKER}),Engine.parse_call)

    def test_failure_categories_scopes_and_actions_are_sanitized(self):
        cases=[('http_401','credential_access','connection',False),('http_400','malformed_request','request',False),
               ('review_identity_conflict','capability_mismatch','request',False),('review_identity_unknown','capability_mismatch','request',False),
               ('http_404','unavailable_route','model',False),('http_429','rate_limit_quota','model',False),
               ('probe_failed','capability_mismatch','model',True),('model_timeout','transient_provider','model',False),
               ('invalid_response_json','invalid_response','model',True)]
        for code,category,scope,impact in cases:
            result=health.classify(ProviderError('private account data',code=code))
            self.assertEqual((result['category'],result['scope'],result['quality_impact']),(category,scope,impact))
            self.assertNotIn('private',str(result))
        self.assertEqual(health.classify(ProviderError('',code='http_404'),{'endpoint_invalid':True})['category'],'malformed_request')
        self.assertEqual(health.classify(InterruptedError())['category'],'cancelled')

    def test_version_configuration_metadata_and_cooldown_invalidate_probe(self):
        identity=health.probe_identity(URL,MODEL,'connection')
        self.assertEqual(identity,health.probe_identity(URL.replace('localhost','127.0.0.1'),MODEL,'connection'))
        for endpoint,model,revision in ((URL+'x',MODEL,'connection'),(URL,{**MODEL,'id':'other'},'connection'),
                                      (URL,MODEL,'changed'),(URL,{**MODEL,'context_length':20000},'connection')):
            self.assertNotEqual(identity,health.probe_identity(endpoint,model,revision))
        with tempfile.TemporaryDirectory() as directory, patch('cheapos.model_pool.time.time',return_value=1000):
            pool=FreeModelPool(directory)
            pool.record(URL,MODEL['id'],'worker',probe=True,connection_revision='connection',probe_identity=identity)
            self.assertTrue(pool.fresh_probe(URL,MODEL['id'],'connection',identity,now=1100))
            self.assertFalse(pool.fresh_probe(URL,MODEL['id'],'connection',identity,now=1300))
            self.assertFalse(pool.fresh_probe(URL,MODEL['id'],'connection','different',now=1100))
            with patch.object(health,'PROBE_VERSION',99):
                self.assertFalse(pool.fresh_probe(URL,MODEL['id'],'connection',identity,now=1100))
            pool.record(URL,MODEL['id'],'worker',connection_revision='connection',error=ProviderError('',code='gateway_cooldown',scope='model',retry_after=120))
            self.assertFalse(pool.fresh_probe(URL,MODEL['id'],'connection',identity,now=1100))

    def test_inflight_identity_sharing_capacity_and_release_are_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            pool=FreeModelPool(directory)
            owner,event=pool.claim_probe('same');self.assertTrue(owner)
            self.assertEqual(pool.claim_probe('same'),(False,event))
            for key in ('two','three','four'):self.assertTrue(pool.claim_probe(key)[0])
            self.assertEqual(pool.claim_probe('five'),(False,None))
            pool.release_probe('same',object());self.assertFalse(event.is_set())
            pool.release_probe('same',event);self.assertTrue(event.is_set())
            self.assertTrue(pool.claim_probe('five')[0])

    def test_credentials_only_block_connection_and_caller_cancel_do_not_harm_quality(self):
        with tempfile.TemporaryDirectory() as directory:
            pool=FreeModelPool(directory)
            pool.record(URL,'provider/a','worker',error=ProviderError('secret',code='http_401'),connection_revision='one')
            self.assertTrue(pool.observation(URL,'provider/b','one')['cooling_down'])
            self.assertFalse(pool.observation(URL,'provider/b','two')['cooling_down'])
            pool.record(URL,'provider/b','worker',error=ProviderError('',code='http_400'),connection_revision='two')
            self.assertEqual(pool.observation(URL,'provider/b','two').get('failures',0),0)
            before=dict(pool.records)
            pool.record(URL,'provider/b','worker',error=InterruptedError(),connection_revision='two')
            self.assertEqual(pool.records,before)
            self.assertNotIn('secret',str(pool.records))
            bare=type('QuotaError',(),{'code':'http_429'})()
            pool.record(URL,'provider/c','worker',error=bare,connection_revision='two')
            self.assertFalse(pool.observation(URL,'provider/c','two')['retry_known'])
            pool.record(URL,'provider/d','worker',error=ValueError('private caller data'),connection_revision='two',failure_context={'caller_error':True})
            self.assertEqual(pool.observation(URL,'provider/d','two').get('failures',0),0)

    def test_metadata_drift_is_labeled_without_rewriting_access_or_prices(self):
        old=[{**MODEL,'input_rate':3}]
        current=[{**MODEL,'context_length':20000,'input_rate':3}]
        result=health.metadata_facts(current,old,123)
        self.assertEqual(result[0]['metadata_evidence'],{'source':'gateway_catalog','observed_at':123,'changes':['context_length'],'stale':False})
        self.assertEqual(result[0]['input_rate'],3)
        self.assertNotIn('metadata_evidence',current[0])


if __name__=='__main__':unittest.main()
