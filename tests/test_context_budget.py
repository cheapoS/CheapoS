import unittest
from types import SimpleNamespace
from cheapos.context_budget import decision, payload_bytes, context_rejection

class ContextBudgetTests(unittest.TestCase):
    def setUp(self):
        self.task={'limits':{'output_tokens':8192},'request_metrics':[]}
        self.config={'model':'route/model','base_url':'http://localhost:20128/v1'}
        self.messages=[{'role':'user','content':'source code '*12000}]

    def test_unknown_capacity_never_imposes_old_character_cutoff(self):
        result=decision(self.task,self.messages,[],self.config)
        self.assertFalse(result['compact'])
        self.assertIsNone(result['capacity_tokens'])
        self.assertEqual(result['capacity_source'],'unknown')

    def test_known_capacity_counts_tools_and_output_reserve(self):
        result=decision(self.task,self.messages,[],self.config,{'context_length':200000})
        self.assertFalse(result['compact'])
        result=decision(self.task,self.messages,[],self.config,{'context_length':32000})
        self.assertTrue(result['compact'])
        self.assertEqual(result['output_reserve_tokens'],8192)
        with_tools=decision(self.task,self.messages,[{'description':'x'*9000}],self.config,{'context_length':32000})
        self.assertGreater(with_tools['estimated_input_tokens'],result['estimated_input_tokens'])

    def test_usage_calibration_is_endpoint_and_model_scoped(self):
        self.task['request_metrics']=[{'requested_model':'route/model','context_base_url':self.config['base_url'],'context_payload_bytes':10000,'input_tokens':2000}]
        calibrated=decision(self.task,self.messages,[],self.config)
        self.assertEqual(calibrated['estimate_source'],'route_usage_calibrated')
        other=decision(self.task,self.messages,[],{**self.config,'base_url':'http://other'})
        self.assertEqual(other['estimate_source'],'utf8_estimate')

    def test_only_explicit_context_errors_trigger_retry(self):
        self.assertTrue(context_rejection(Exception('maximum context length exceeded')))
        self.assertFalse(context_rejection(Exception('rate limit exceeded')))
        self.assertFalse(context_rejection(Exception('invalid tool arguments')))

    def test_http_rejection_repairs_each_role_before_routing(self):
        import io, json
        from urllib.error import HTTPError
        from unittest.mock import Mock
        from cheapos.providers import http_failure
        from cheapos.engine import Engine
        for role in ('worker','planner','reviewer'):
            error=http_failure(HTTPError('http://gateway',400,'bad',{},io.BytesIO(json.dumps({'error':{'code':'context_length_exceeded','message':'PRIVATE'}}).encode())), {'gateway':'omniroute'})
            self.assertEqual(error.code,'context_length_exceeded');self.assertNotIn('PRIVATE',str(error))
            task={'limits':{'output_tokens':2048}}
            engine=SimpleNamespace(_request_route_once=Mock(side_effect=[error,{'content':'done'}]),event=Mock(),store=Mock())
            messages=[{'role':'system','content':'Exact constraints'}, {'role':'user','content':'Exact criteria'}, {'role':'assistant','content':'old reasoning '*2000}]
            result=Engine._request_routed(engine,SimpleNamespace(task=task),messages,[],role)
            self.assertEqual(result,{'content':'done'})
            repaired=engine._request_route_once.call_args.args[1]
            self.assertLess(payload_bytes(repaired,[]),payload_bytes(messages,[]))
            self.assertEqual(repaired[:2],messages[:2])
            self.assertEqual(len(task['context_evidence']),1)
            self.assertGreater(len(messages[-1]['content']),2000)

    def test_irreducible_request_uses_capacity_selection_and_respects_pin(self):
        from unittest.mock import Mock, patch
        from cheapos.engine import Engine
        from cheapos.providers import ProviderError
        config={'model':'small','base_url':'gateway'}
        task={'limits':{'output_tokens':2048},'providers':{'planner':config}}
        error=ProviderError('Context capacity exceeded',code='context_length_exceeded')
        gateway=SimpleNamespace(catalog=Mock(return_value={'models':[{'id':'small','context_length':4096}]}))
        engine=SimpleNamespace(_request_route_once=Mock(side_effect=[error,{'content':'proposal'}]),connection_for=lambda _:gateway,event=Mock(),store=Mock())
        runtime=SimpleNamespace(task=task)
        messages=[{'role':'user','content':'Exact retained scope '*1000}]
        def select(e,rt,role,replace):
            self.assertGreater(rt.task['context_route_minimum'][role],4096)
            self.assertTrue(replace)
            rt.task['providers'][role]={'model':'larger','base_url':'gateway'}
        with patch('cheapos.engine.automatic',return_value=True),patch('cheapos.engine.select_remote',side_effect=select) as choose:
            self.assertEqual(Engine._request_routed(engine,runtime,messages,[],'planner'),{'content':'proposal'})
            choose.assert_called_once()
        self.assertNotIn('planner',task['context_route_minimum'])
        engine._request_route_once=Mock(side_effect=error)
        with patch('cheapos.engine.select_remote') as choose,self.assertRaises(ProviderError):
            Engine._request_routed(engine,runtime,messages,[],'planner',config_override=config)
        choose.assert_not_called()
        self.assertEqual(engine._request_route_once.call_count,1)
