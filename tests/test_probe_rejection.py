import unittest
from cheapos.route_health import candidate_probe_rejection, probe_identity
from cheapos.providers import ProviderError

class ProbeRejectionTests(unittest.TestCase):
    def test_rejected_candidate_can_be_skipped_without_hiding_shared_errors(self):
        for code in ('http_400','http_422'):
            self.assertTrue(candidate_probe_rejection(ProviderError('rejected',code=code)))
            self.assertTrue(candidate_probe_rejection(ProviderError('rejected',code=code,scope='model')))
            for scope in ('request','connection','account'):
                self.assertFalse(candidate_probe_rejection(ProviderError('rejected',code=code,scope=scope)))
        for code in ('http_401','http_403','http_429','invalid_request'):
            self.assertFalse(candidate_probe_rejection(ProviderError('rejected',code=code)))
        self.assertFalse(candidate_probe_rejection(ValueError('local bad arguments')))

    def test_changed_connection_or_capabilities_allows_new_probe(self):
        model={'id':'candidate','tool_calling':True}
        original=probe_identity('http://localhost:20128/v1',model,'revision1')
        self.assertNotEqual(original,probe_identity('http://localhost:20128/v1',model,'revision2'))
        self.assertNotEqual(original,probe_identity('http://localhost:20128/v1',{**model,'context_length':100000},'revision1'))

    def test_rejected_candidate_probe_is_persisted_and_cooled_down(self):
        import tempfile
        from cheapos.model_pool import FreeModelPool
        with tempfile.TemporaryDirectory() as directory:
            pool = FreeModelPool(directory)
            endpoint = 'http://localhost:20128/v1'
            err = ProviderError("Model 'dead-model' is not available in active catalog", code='http_400')
            pool.record(endpoint, 'provider/dead-model', 'worker', error=err,
                        failure_context={'caller_error': False, 'candidate_rejected': True})
            obs = pool.observation(endpoint, 'provider/dead-model')
            self.assertTrue(obs['cooling_down'])
            self.assertTrue(obs.get('probe_rejected'))
            self.assertEqual(obs.get('failures', 0), 0)
            self.assertEqual(obs.get('availability_failures'), 1)

            # Persists across pool reloads
            reloaded = FreeModelPool(directory)
            obs2 = reloaded.observation(endpoint, 'provider/dead-model')
            self.assertTrue(obs2['cooling_down'])
            self.assertTrue(obs2.get('probe_rejected'))

    def test_verified_tool_check_passed_is_prioritized_over_unverified(self):
        import tempfile
        import time
        from unittest.mock import patch
        from cheapos.model_pool import FreeModelPool
        with tempfile.TemporaryDirectory() as directory:
            pool = FreeModelPool(directory)
            endpoint = 'http://localhost:20128/v1'
            models = [
                {'id': 'unverified-coder', 'context_length': 32000},
                {'id': 'verified-coder', 'context_length': 32000, 'tool_calling': True},
            ]
            pool.record(endpoint, 'verified-coder', 'worker', probe=True)
            with patch('cheapos.model_pool.time.time', return_value=time.time() + 400):
                self.assertFalse(pool.fresh_probe(endpoint, 'verified-coder', None, 'id'))
                r_verified = pool.rank(endpoint, models[1], 'worker')
                r_unverified = pool.rank(endpoint, models[0], 'worker')
                self.assertLess(r_verified, r_unverified)
