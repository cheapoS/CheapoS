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
