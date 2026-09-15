"""Network-free request boundary tests: no repository or live inference fixture."""
import io
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos.engine import Engine
from cheapos.providers import ProviderError, BudgetError
from cheapos.streaming import read_chat_stream
from cheapos import transport
from cheapos.providers import guard_inference_route, ChatProvider


class TransportTests(unittest.TestCase):
    def test_gateway_placeholder_retries_json_and_remembers_success(self):
        engine,runtime,calls=self.harness();provider=engine.provider_factory()
        def malformed(*args):
            calls.append('sse')
            return {'tool_calls':[{'id':'bad','function':{'name':'malformed_tool_call','arguments':'{}'}}]}, {'prompt_tokens':2,'completion_tokens':3,'cost':.001}
        provider.complete_with_progress=malformed;engine.provider_factory=lambda *args:provider
        engine._request(runtime,[],[],'worker')
        engine._request(runtime,[],[],'worker')
        self.assertEqual(calls,['sse','json','json'])
        self.assertEqual([r['status'] for r in runtime.task['request_metrics']],['failed','responded','responded'])
        self.assertAlmostEqual(runtime.task['usage']['cost'],.003)
        self.assertEqual(runtime.task['request_metrics'][0]['error_code'],'malformed_tool_call')

    def test_saved_placeholder_retry_preserves_handoffs_and_is_consumed_once(self):
        engine,runtime,calls=self.harness();task=runtime.task;cfg=task['providers']['worker']
        task['route']={'recovery':{'worker':{'from':cfg['model'],'reason':transport.MALFORMED_NOTICE}}}
        task['progress_state']={'handoffs':2}
        record={'id':'original','role':'worker','model':cfg['model'],'purpose':'work',
                'dispatched':True,'transport':'sse','status':'responded'}
        task['request_metrics']=[record]
        self.assertTrue(transport.restore_malformed_retry(task,'worker'))
        self.assertEqual(task['progress_state'],{'handoffs':2})
        self.assertEqual(record['status'],'responded')
        runtime.task=json.loads(json.dumps(task))
        engine._request(runtime,[],[],'worker')
        self.assertEqual(calls,['json'])
        self.assertEqual(runtime.task['request_metrics'][-1]['retry_of'],'original')
        self.assertFalse(transport.restore_malformed_retry(runtime.task,'worker'))
        self.assertTrue(transport.json_preference(runtime.task,cfg,'worker',None))

    def harness(self, failure=None, hook=None):
        config = {'model':'example/model','base_url':'http://localhost:1/v1','input_rate':1,'output_rate':1}
        task = {'id':'task','demo':False,'status':'running','providers':{'worker':config},
                'limits':{'dollars':1,'reviewer_tokens':10000,'output_tokens':128},
                'usage':{'cost':0,'uncertain_requests':0,'estimated_requests':0,
                         'worker':{'tokens':0,'cost':0},'reviewer':{'tokens':0,'cost':0}},
                'events':[]}
        runtime = SimpleNamespace(task=task, stop=threading.Event(), guard=Mock())
        calls=[]
        class Provider:
            streams_output=True
            def complete_with_progress(self, messages, tools, maximum, emit, stopped):
                calls.append('sse')
                if hook: hook(runtime)
                raise failure or ProviderError('unsupported',code='streaming_unsupported')
            def complete(self, messages, tools, maximum):
                calls.append('json')
                return {'role':'assistant','content':'done'},{'prompt_tokens':2,'completion_tokens':3,'cost':.001}
            def complete_brief(self, messages, tools, maximum, emit, stopped):
                calls.append(('brief',emit is not None,maximum))
                if emit is not None: raise ProviderError('unsupported',code='streaming_unsupported')
                return self.complete(messages,tools,maximum)
        engine=Engine.__new__(Engine)
        from cheapos.admission import Admission
        engine.lock=threading.RLock();engine.runtimes={}
        engine.admission=Admission(engine)
        engine.store=Mock();engine.gateway=SimpleNamespace(settings={'base_url':'http://localhost:20128/v1'})
        engine.provider_factory=lambda *args:Provider()
        engine.event=lambda t,*args:t['events'].append({'id':str(len(t['events'])), 'detail':args})
        return engine,runtime,calls

    def test_planner_dispatch_uses_saved_reviewer_credentials(self):
        engine,runtime,calls=self.harness()
        provider=engine.provider_factory()
        engine.provider_factory=None
        config=dict(runtime.task['providers']['worker'],gateway='omniroute',base_url='http://localhost:20128/v1',key_env='CHEAPOS_REVIEWER_API_KEY')
        runtime.task['providers']={'reviewer':config}
        engine.config={}
        engine.gateway.api_key='shared-fixture-key'
        engine.gateway.matches=lambda url:False
        with patch('cheapos.engine.gateway_for',return_value=provider) as factory:
            engine._request(runtime,[],[],'planner',purpose='branch_planning')
        self.assertEqual(factory.call_args.args[1],'shared-fixture-key')
        self.assertEqual(factory.call_args.args[0]['credential_role'],'reviewer')
        self.assertTrue(all(r['role']=='planner' for r in runtime.task['request_metrics']))
        self.assertNotIn('shared-fixture-key',json.dumps(runtime.task))

    def test_planner_override_cannot_dispatch_outside_captured_connection(self):
        engine, runtime, calls = self.harness()
        policy = {'version': 1, 'base_url': 'http://localhost:1/v1',
                  'connection_revision': 'a' * 32, 'included_models': []}
        config = {**runtime.task['providers']['worker'], 'gateway': 'omniroute',
                  'access_binding': policy}
        runtime.task.update(access_policy=policy, route={'access_policy': policy})
        runtime.task['usage']['planner'] = {'tokens': 0, 'cost': 0}
        engine.gateway.settings = policy
        engine.gateway.catalog = Mock(return_value={'models': [
            {'id': config['model'], 'free': True, 'tool_calling': True}]})
        factory = Mock(wraps=engine.provider_factory)
        engine.provider_factory = factory
        for change in ({'base_url': 'http://localhost:2/v1'}, {'access_binding': None},
                       {'access_binding': {**policy, 'connection_revision': 'stale'}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                engine.request(runtime, [{'role': 'user', 'content': 'plan'}], [], 'planner',
                               config_override={**config, **change}, purpose='branch_planning')
        factory.assert_not_called()
        self.assertEqual(runtime.task['usage']['cost'], 0)
        engine.request(runtime, [{'role': 'user', 'content': 'plan'}], [], 'planner',
                       config_override=config, purpose='branch_planning')
        self.assertTrue(factory.called)
        self.assertEqual(runtime.task['request_metrics'][-1]['status'], 'responded')

    def test_each_dispatch_is_accounted_without_counting_an_extra_worker_turn(self):
        engine,runtime,calls=self.harness()
        result=engine._request(runtime,[{'role':'user','content':'hi'}],[],'worker')
        self.assertEqual(result['content'],'done'); self.assertEqual(calls,['sse','json'])
        first,second=runtime.task['request_metrics']
        self.assertEqual((first['status'],second['status']),('failed','responded'))
        self.assertEqual(second['retry_of'],first['id'])
        self.assertEqual((first['transport'],second['transport']),('sse','json'))
        self.assertEqual(runtime.task['usage']['uncertain_requests'],1)
        self.assertAlmostEqual(runtime.task['usage']['cost'],first['reservation']['cost']+.001)
        self.assertNotIn('worker_turns',runtime.task)
        self.assertIsNone(runtime.task['stream'])
        # Reload the task as an older saved run: reuse its successful fallback.
        original_retries = dict(runtime.task['transport_retries'])
        runtime.task=json.loads(json.dumps(runtime.task))
        engine._request(runtime,[],[],'worker')
        self.assertEqual(calls,['sse','json','json'])
        self.assertIsNone(runtime.task['request_metrics'][-1]['retry_of'])
        self.assertEqual(runtime.task['transport_retries'],original_retries)
        self.assertEqual(runtime.task['usage']['uncertain_requests'],1)
        # The decision survives pruning the successful request and another reload.
        runtime.task['request_metrics']=[]
        runtime.task=json.loads(json.dumps(runtime.task))
        engine._request(runtime,[],[],'worker')
        self.assertEqual(calls,['sse','json','json','json'])
        self.assertEqual(runtime.task['transport_retries'],original_retries)

    def test_successful_transport_memory_is_route_role_purpose_and_connection_scoped(self):
        engine,runtime,calls=self.harness()
        engine._request(runtime,[],[],'worker')
        config=runtime.task['providers']['worker']
        self.assertIsNotNone(transport.json_preference(runtime.task,config,'worker',None))
        for change,role,purpose in [({'model':'other'},'worker',None),
                ({'base_url':'http://localhost:2/v1'},'worker',None),
                ({},'reviewer',None),({},'worker','probe'),
                ({'access_binding':{'connection_revision':'new'}},'worker',None)]:
            self.assertIsNone(transport.json_preference(runtime.task,{**config,**change},role,purpose))
        # Working JSON later failing remains a provider error, with no extra retry.
        provider=engine.provider_factory()
        provider.complete=Mock(side_effect=ProviderError('unavailable',code='empty_response'))
        engine.provider_factory=lambda *args:provider
        with self.assertRaises(ProviderError) as error:engine._request(runtime,[],[],'worker')
        self.assertEqual(error.exception.code,'empty_response')
        self.assertEqual(provider.complete.call_count,1)

    def test_second_dispatch_obeys_pause_authority_budget_and_request_allowance(self):
        def revoked(runtime): runtime.guard.side_effect=ValueError('revoked')
        def exhausted(runtime): runtime.task['limits']['dollars']=runtime.task['usage']['cost']
        def request_limit(runtime): runtime.branch_ledger=SimpleNamespace(guard=Mock(side_effect=ValueError('requests')))
        for hook in (lambda r:r.stop.set(), revoked, exhausted, request_limit):
            engine,runtime,calls=self.harness(hook=hook)
            with self.assertRaises((InterruptedError,ValueError,BudgetError)):
                engine._request(runtime,[],[],'worker')
            self.assertEqual(calls,['sse'])

    def test_generic_failure_is_not_transport_evidence_and_known_usage_survives(self):
        failure=ProviderError('generic',code='stream_error',usage={'prompt_tokens':4,'completion_tokens':5,'cost':.002})
        engine,runtime,calls=self.harness(failure)
        with self.assertRaises(ProviderError): engine._request(runtime,[],[],'worker')
        self.assertEqual(calls,['sse']);self.assertEqual(runtime.task['usage']['uncertain_requests'],0)
        self.assertEqual(runtime.task['request_metrics'][0]['input_tokens'],4)
        self.assertAlmostEqual(runtime.task['usage']['cost'],.002)

    def test_probe_fallback_keeps_brief_contract(self):
        engine,runtime,calls=self.harness()
        engine._request(runtime,[],[],'worker',purpose='probe')
        self.assertEqual(calls,[('brief',True,128),('brief',False,128),'json'])

    def test_known_compatibility_is_scoped_and_only_explicit_stream_signal_retries(self):
        config={'gateway':'omniroute','model':'openrouter/google/gemini-2.5-flash'}
        self.assertEqual(transport.choice(config,'reviewer',None,[{}],True),'json')
        for role,purpose,tools in [('worker',None,[{}]),('reviewer','probe',[{}]),('reviewer',None,[])]:
            self.assertEqual(transport.choice(config,role,purpose,tools,True),'sse')
        data=('data: '+json.dumps({'error':{'code':'unsupported_streaming'}})+'\n\n').encode()
        with self.assertRaises(ProviderError) as caught:
            read_chat_stream(io.BytesIO(data),lambda *a:None,lambda:False,ProviderError)
        self.assertEqual(caught.exception.code,'streaming_unsupported')

    def test_failed_fallback_retains_both_attempts_and_reviewer_allowance_blocks_retry(self):
        engine,runtime,calls=self.harness()
        provider=engine.provider_factory()
        def fail_json(*args):
            calls.append('json'); raise ProviderError('JSON also failed',code='model_connection')
        provider.complete=fail_json;engine.provider_factory=lambda *args:provider
        with self.assertRaisesRegex(ProviderError,'JSON also failed'):
            engine._request(runtime,[],[],'worker')
        self.assertEqual([r['status'] for r in runtime.task['request_metrics']],['failed','failed'])
        self.assertEqual(runtime.task['usage']['uncertain_requests'],2)
        self.assertIsNone(transport.json_preference(runtime.task,runtime.task['providers']['worker'],'worker',None))
        runtime.task=json.loads(json.dumps(runtime.task))
        with self.assertRaises(ProviderError) as error:engine._request(runtime,[],[],'worker')
        self.assertEqual(error.exception.code,'transport_retry_exhausted')
        self.assertEqual(calls,['sse','json','sse'])
        engine,runtime,calls=self.harness()
        runtime.task['providers']['reviewer']=runtime.task['providers']['worker']
        runtime.task.update(status='reviewing',pending_review={'review_requests':7})
        with self.assertRaises(BudgetError):engine._request(runtime,[],[],'reviewer')
        self.assertEqual(calls,['sse'])
        self.assertEqual(runtime.task['pending_review']['review_requests'],8)


class GatewayOnlyTests(unittest.TestCase):
    """No sockets, repository setup, waits, or inference."""
    def test_only_configured_gateway_and_local_ollama_are_allowed(self):
        base = 'http://127.0.0.1:20128/v1'
        for config in ({'gateway':'omniroute', 'base_url':base},
                       {'gateway':'omniroute', 'base_url':'http://localhost:20128/v1/'},
                       {'base_url':'http://127.0.0.1:11434/v1'}):
            guard_inference_route(config, base)
        for url in ('https://openrouter.ai/api/v1', 'https://other.example/v1',
                    'http://127.0.0.1:20129/v1', 'http://127.0.0.1:20128/v1?redirect=x',
                    'http://user:secret@127.0.0.1:20128/v1', 'http://127.0.0.1:11434/proxy',
                    'http://127.0.0.1:11434/v1?remote=x', 'http://localhost:99999/v1', 'http://localhost:0/v1'):
            for gateway in ('openai','omniroute'):
                with self.subTest(url=url, gateway=gateway), self.assertRaisesRegex(ValueError,'must use the configured OmniRoute'):
                    guard_inference_route({'base_url':url,'gateway':gateway}, base)

    def test_legacy_and_override_remote_requests_never_dispatch_or_reserve(self):
        for mode in ('manual','remote','delegate','local'):
            for role in ('worker','reviewer','planner','coordinator'):
                engine,runtime,_=TransportTests().harness()
                engine.provider_factory=None
                runtime.task['execution']={'mode':mode}
                config=dict(runtime.task['providers']['worker'],base_url='https://openrouter.ai/api/v1',gateway='openai')
                runtime.task['providers']={role:config}
                # Both saved settings and direct overrides must hit the same guard.
                for override in (None, config, dict(config,gateway='omniroute')):
                    with self.subTest(mode=mode,role=role,override=override), patch('cheapos.engine.gateway_for') as provider:
                        with self.assertRaisesRegex(ValueError,'must use the configured OmniRoute'):
                            engine._request(runtime,[],[],role,config_override=override)
                        provider.assert_not_called()
                        self.assertEqual(runtime.task['usage']['cost'],0)
                        self.assertNotIn('in_flight',runtime.task)
                        self.assertFalse(runtime.task['request_metrics'][-1]['dispatched'])

    def test_local_requests_ignore_direct_provider_environment_keys(self):
        with patch.dict('os.environ',{'CHEAPOS_WORKER_API_KEY':'must-not-forward'}):
            provider=ChatProvider({'base_url':'http://127.0.0.1:11434/v1','key_env':'CHEAPOS_WORKER_API_KEY'})
            self.assertEqual(provider.key,'')

    def test_manual_local_cloud_routes_are_verified_before_dispatch(self):
        engine,runtime,_=TransportTests().harness()
        engine.provider_factory=None
        runtime.verified_local=set()
        runtime.task['execution']={'mode':'manual'}
        config=dict(runtime.task['providers']['worker'],base_url='http://127.0.0.1:11434/v1')
        with patch('cheapos.engine.verify_local',side_effect=ValueError('cloud route')), patch('cheapos.engine.gateway_for') as provider:
            with self.assertRaisesRegex(ValueError,'cloud route'):
                engine._request(runtime,[],[],'worker',config_override=config)
            provider.assert_not_called()
            self.assertEqual(runtime.task['usage']['cost'],0)

    def test_startup_does_not_discover_or_infer_through_a_legacy_direct_provider(self):
        from cheapos.startup import StartupManager
        engine,_,_=TransportTests().harness()
        engine.preferences=lambda:{'execution':{'mode':'manual'}}
        startup=StartupManager.__new__(StartupManager)
        startup.engine=engine
        startup.settings={'allow_cloud':True}
        startup._omni=Mock(return_value=[])
        saved={'base_url':'https://openrouter.ai/api/v1','model':'model:free','gateway':'openai'}
        with patch('cheapos.startup.local_candidates',return_value=[]), patch('cheapos.startup.gateway_for') as provider:
            self.assertEqual(list(startup._candidates(saved)),[])
            provider.assert_not_called()


class AutomaticRouteChargeTests(unittest.TestCase):
    """Exercise the real request boundary with the existing in-memory harness."""
    harness = TransportTests.harness

    def automatic(self, outcomes, mode='remote', dollars=.5):
        engine, runtime, _ = self.harness()
        runtime.task['execution'] = {'mode': mode}
        runtime.task['limits']['dollars'] = dollars
        from cheapos.access_policy import bind_provider
        config = {**runtime.task['providers']['worker'], 'gateway': 'omniroute'}
        policy = {'version': 1, 'base_url': config['base_url'], 'connection_revision': 'a' * 32,
                  'included_models': [config['model']]}
        model = {'id': config['model'], 'free': False, 'tool_calling': True}
        runtime.task.update(access_policy=policy, route={'access_policy': policy})
        runtime.task['providers']['worker'] = bind_provider(config, policy, model)
        engine.gateway.settings = policy
        engine.gateway.catalog = Mock(return_value={'models': [model]})
        message = {'tool_calls': [{'id': 'edit', 'function': {'name': 'write_file', 'arguments': '{"path":"example.py","content":"done"}'}}]}
        queue = iter(outcomes)

        def complete(*args):
            outcome = next(queue)
            if isinstance(outcome, Exception):
                raise outcome
            return message, {'prompt_tokens': 2, 'completion_tokens': 3, 'cost': outcome}

        provider = SimpleNamespace(complete=Mock(side_effect=complete))
        engine.provider_factory = lambda *args: provider
        return engine, runtime, provider, message

    def test_subcent_report_returns_tools_and_preserves_exact_accounting(self):
        for mode in ('remote', 'delegate'):
            with self.subTest(mode=mode):
                engine, runtime, provider, message = self.automatic([.00627968], mode)
                result = engine._request(runtime, [], [], 'worker')
                self.assertEqual(result, message)
                self.assertEqual(provider.complete.call_count, 1)
                self.assertAlmostEqual(runtime.task['usage']['cost'], .00627968)
                self.assertAlmostEqual(runtime.task['usage']['worker']['cost'], .00627968)
                self.assertEqual(runtime.task['request_metrics'][0]['reported_cost'], .00627968)
                self.assertEqual(runtime.task['request_metrics'][0]['cost_provenance'], 'provider_reported')
                self.assertEqual(runtime.task['usage']['uncertain_requests'], 0)

    def test_cumulative_cent_stops_response_and_remains_exhausted_after_reload(self):
        engine, runtime, provider, _ = self.automatic([.00627968, .00372032])
        engine._request(runtime, [], [], 'worker')
        with self.assertRaisesRegex(BudgetError, r'\$0\.01 cumulative'):
            engine._request(runtime, [], [], 'worker')
        self.assertAlmostEqual(runtime.task['usage']['cost'], .01)
        self.assertEqual(runtime.task['request_metrics'][-1]['status'], 'failed')
        runtime.task = json.loads(json.dumps(runtime.task))
        with self.assertRaisesRegex(BudgetError, r'\$0\.01 cumulative'):
            engine._request(runtime, [], [], 'worker')
        self.assertEqual(provider.complete.call_count, 2)
        self.assertFalse(runtime.task['request_metrics'][-1]['dispatched'])

    def test_failure_usage_accumulates_toward_cutoff_before_retry(self):
        def failure(cost):
            return ProviderError('Output incomplete', code='output_limit',
                                 usage={'prompt_tokens': 2, 'completion_tokens': 3, 'cost': cost})
        engine, runtime, provider, _ = self.automatic([failure(.006), failure(.004)])
        with self.assertRaises(ProviderError):
            engine._request(runtime, [], [], 'worker')
        with self.assertRaisesRegex(BudgetError, r'\$0\.01 cumulative'):
            engine._request(runtime, [], [], 'worker')
        self.assertAlmostEqual(runtime.task['usage']['cost'], .01)
        with self.assertRaises(BudgetError):
            engine._request(runtime, [], [], 'worker')
        self.assertEqual(provider.complete.call_count, 2)

    def test_tolerance_does_not_override_lower_task_budget_or_missing_usage(self):
        for dollars in (0, .005):
            with self.subTest(dollars=dollars):
                engine, runtime, provider, _ = self.automatic([.00627968], dollars=dollars)
                with self.assertRaises(BudgetError) as error:
                    engine._request(runtime, [], [], 'worker')
                self.assertEqual(error.exception.limit_hit['allowed'], dollars)
                self.assertAlmostEqual(runtime.task['usage']['cost'], .00627968)
                self.assertEqual(provider.complete.call_count, 1)
        error = ProviderError('Incomplete usage', code='output_limit', usage={'cost': .00627968})
        engine, runtime, provider, _ = self.automatic([error])
        with self.assertRaisesRegex(BudgetError, 'omitted complete token usage'):
            engine._request(runtime, [], [], 'worker')
        self.assertAlmostEqual(runtime.task['usage']['cost'], .00627968)
        self.assertEqual(runtime.task['usage']['uncertain_requests'], 1)
        self.assertEqual(provider.complete.call_count, 1)

    def test_manual_and_local_requests_keep_their_existing_task_budget(self):
        for mode in ('manual', 'local'):
            with self.subTest(mode=mode):
                engine, runtime, provider, message = self.automatic([.02], mode)
                self.assertEqual(engine._request(runtime, [], [], 'worker'), message)
                self.assertAlmostEqual(runtime.task['usage']['cost'], .02)
                self.assertEqual(provider.complete.call_count, 1)
