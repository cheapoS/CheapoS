"""Legacy route evidence checks without network, Git or model calls."""
import unittest
from cheapos.request_health import historical_route_metadata


class HistoricalRouteTests(unittest.TestCase):
    def setUp(self):
        self.scope = dict(base_url='http://private.invalid/v1', connection_revision='saved-revision',
                          model='future-provider/publisher/model', role='worker')
        self.record = dict(requested_model=self.scope['model'], served_model='publisher/model',
                           role='worker', dispatch_scope=self.scope, context_base_url=self.scope['base_url'])
        self.connection = dict(base_url=self.scope['base_url'], connection_revision='saved-revision',
                               gateway_type='omniroute')

    def test_exact_dispatch_match_uses_requested_route_not_served_publisher(self):
        self.assertEqual(historical_route_metadata(self.record, [self.connection]),
                         dict(request_gateway='omniroute', request_provider='future-provider'))
        self.assertNotIn('request_provider', self.record)

    def test_missing_conflicting_and_ambiguous_evidence_stays_unknown(self):
        cases = [
            ({**self.record, 'dispatch_scope': None}, [self.connection]),
            ({**self.record, 'requested_model': 'other/model'}, [self.connection]),
            ({**self.record, 'role': 'reviewer'}, [self.connection]),
            ({**self.record, 'context_base_url': 'http://other.invalid/v1'}, [self.connection]),
            ({**self.record, 'dispatch_scope': {**self.scope, 'connection_revision': ''}}, [self.connection]),
            (self.record, []),
            (self.record, None),
            (self.record, [self.connection, self.connection]),
            (self.record, [{**self.connection, 'connection_revision': 'new-revision'}]),
            (self.record, [{**self.connection, 'base_url': 'http://other.invalid/v1'}]),
            (self.record, [{**self.connection, 'gateway_type': 'openai-compatible'}]),
            (self.record, [{k: v for k, v in self.connection.items() if k != 'gateway_type'}]),
        ]
        for record, connections in cases:
            with self.subTest(record=record, connections=connections):
                self.assertEqual(historical_route_metadata(record, connections), {})

    def test_explicit_route_fields_and_local_access_are_not_guessed(self):
        for field in ('request_provider', 'request_gateway'):
            for value in ('unknown', 'explicit-route'):
                self.assertEqual(historical_route_metadata({**self.record, field: value}, [self.connection]), {})
        self.assertEqual(historical_route_metadata({'access_class': 'local'}, []),
                         dict(request_gateway='local', request_provider='local'))
        self.assertEqual(historical_route_metadata({'category': 'local', 'requested_model': 'gemma4:31b'}, []), {})
        self.assertEqual(historical_route_metadata({'access_class': 'local', 'dispatch_scope': self.scope}, []), {})
