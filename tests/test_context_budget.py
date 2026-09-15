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
