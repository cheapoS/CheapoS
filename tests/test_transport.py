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


class TransportTests(unittest.TestCase):
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
        engine.store=Mock();engine.gateway=SimpleNamespace(settings={})
        engine.provider_factory=lambda *args:Provider()
        engine.event=lambda t,*args:t['events'].append({'id':str(len(t['events'])), 'detail':args})
        return engine,runtime,calls

    def test_planner_dispatch_uses_saved_reviewer_credentials(self):
        engine,runtime,calls=self.harness()
        provider=engine.provider_factory()
        engine.provider_factory=None
        config=dict(runtime.task['providers']['worker'],base_url='https://provider.example/v1',key_env='CHEAPOS_REVIEWER_API_KEY')
        runtime.task['providers']={'reviewer':config}
        engine.config={}
        engine.secrets={('reviewer',config['base_url']):'reviewer-fixture-key'}
        engine.gateway.matches=lambda url:False
        with patch('cheapos.engine.gateway_for',return_value=provider) as factory:
            engine._request(runtime,[],[],'planner',purpose='branch_planning')
        self.assertEqual(factory.call_args.args[1],'reviewer-fixture-key')
        self.assertEqual(factory.call_args.args[0]['credential_role'],'reviewer')
        self.assertTrue(all(r['role']=='planner' for r in runtime.task['request_metrics']))
        self.assertNotIn('reviewer-fixture-key',json.dumps(runtime.task))

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
        # Durable allowance stays consumed across a new invocation.
        with self.assertRaisesRegex(ProviderError,'already used'):
            engine._request(runtime,[],[],'worker')
        self.assertEqual(calls,['sse','json','sse'])

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
        engine,runtime,calls=self.harness()
        runtime.task['providers']['reviewer']=runtime.task['providers']['worker']
        runtime.task.update(status='reviewing',pending_review={'review_requests':7})
        with self.assertRaises(BudgetError):engine._request(runtime,[],[],'reviewer')
        self.assertEqual(calls,['sse'])
        self.assertEqual(runtime.task['pending_review']['review_requests'],8)
