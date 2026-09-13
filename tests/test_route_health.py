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
