"""Deterministic direct setup cases, without sockets, credentials or inference."""
import json
import tempfile
import unittest
from unittest.mock import patch

from cheapos.connections import Connections
from cheapos.omniroute import OmniRouteManager, validate_settings
from cheapos.providers import guard_inference_route, ProviderError
from cheapos import access_policy
from cheapos.settings_adapter import _capture_policy


class DirectConnectionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.default = OmniRouteManager(self.temp.name, use_environment=False)
        self.connections = Connections(self.temp.name, self.default)
        self.identity = self.connections.add({'name': 'Fixture API', 'gateway_type': 'direct',
                                              'base_url': 'https://api.example/api/v1', 'api_key': 'fixture-key'})
        self.manager = self.connections.managers[self.identity]

    def test_saved_connection_is_manual_by_default_and_keys_are_not_serialized(self):
        self.assertFalse(self.manager.settings['automatic'])
        self.assertFalse(self.manager.settings['auto_start'])
        self.assertNotIn(self.identity, [e['connection_id'] for e in self.connections.capture()])
        self.assertIn(self.identity, [e['connection_id'] for e in self.connections.capture(include=[self.identity])])
        self.assertNotIn('fixture-key', self.manager.path.read_text())
        restored = Connections(self.temp.name, OmniRouteManager(self.temp.name, use_environment=False))
        self.assertFalse(restored.managers[self.identity].settings['automatic'])
        self.assertEqual(restored.managers[self.identity].api_key, '')

    def test_remote_urls_require_explicit_direct_adapter_and_https(self):
        for url in ['http://api.example/v1', 'https://key@api.example/v1', 'https://api.example/v1?key=x', 'https://api.example/v1#x']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_settings({'gateway_type': 'direct', 'base_url': url})
        with self.assertRaises(ValueError):
            validate_settings({'gateway_type': 'compatible', 'base_url': 'https://api.example/v1'})

    def test_inference_stays_bound_to_saved_connection(self):
        config = {'gateway': 'omniroute', 'gateway_type': 'direct', 'connection_id': self.identity,
                  'base_url': self.manager.settings['base_url']}
        guard_inference_route(config, config['base_url'])
        for changed in [dict(config, base_url='https://other.example/v1'), dict(config, connection_id=None), dict(config, gateway='openai')]:
            with self.assertRaises(ValueError):
                guard_inference_route(changed, config['base_url'])
        self.assertTrue(self.manager.matches('https://api.example:443/api/v1'))

    def test_manual_model_fallback_never_invents_price_or_tools(self):
        self.manager.configure({'manual_models': ['vendor/model']})
        with patch('cheapos.omniroute.OpenAICompatibleGateway.list_models', side_effect=ProviderError('404', code='catalog_unavailable')):
            models = self.manager._probe()
        self.assertEqual(models[0]['id'], 'vendor/model')
        self.assertFalse(models[0]['free'])
        self.assertIsNone(models[0]['input_rate'])
        self.assertIsNone(models[0]['tool_calling'])
        self.assertFalse(access_policy.eligible(models[0], access_policy.snapshot(self.manager.settings)))
        with patch('cheapos.omniroute.OpenAICompatibleGateway.list_models', side_effect=ProviderError('auth', code='client_key_rejected')):
            with self.assertRaises(ProviderError):
                self.manager._probe()

    def test_direct_request_uses_own_key_and_preserves_paired_history(self):
        import io
        from email.message import Message
        from cheapos.engine import Engine
        from cheapos.providers import ChatProvider
        engine = Engine.__new__(Engine)
        engine.connections = self.connections
        engine.gateway = self.default
        config = {'gateway':'omniroute', 'gateway_type':'direct', 'connection_id':self.identity,
                  'base_url':self.manager.settings['base_url'], 'model':'vendor/model', 'pacing_interval':0}
        messages = [{'role':'user','content':'Continue'},
                    {'role':'assistant','content':None,'tool_calls':[{'id':'read-1','type':'function','function':{'name':'read_file','arguments':'{}'}}]},
                    {'role':'tool','tool_call_id':'read-1','content':'retained evidence'}]
        response = io.BytesIO(json.dumps({'model':'vendor/model', 'choices':[{'message':{'role':'assistant','content':'Done'}}],
                                         'usage':{'prompt_tokens':3,'completion_tokens':1}}).encode())
        response.headers = Message()
        with patch('cheapos.providers.build_opener') as opener:
            opener.return_value.open.return_value = response
            result = ChatProvider(engine.gateway_config(config), engine.provider_key('worker',config)).complete(messages, [], 16)
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.example/api/v1/chat/completions')
        self.assertEqual(request.get_header('Authorization'), 'Bearer fixture-key')
        self.assertEqual(json.loads(request.data)['messages'], messages)
        self.assertEqual(result[0]['content'], 'Done')
        self.assertEqual(result[1]['prompt_tokens'], 3)
        self.assertEqual(result[1]['_served_identity']['served_model'], 'vendor/model')

    def test_changed_endpoint_drops_credentials_and_access(self):
        revision = self.manager.settings['connection_revision']
        self.manager.configure({'included_models': ['vendor/model'], 'expected_connection_revision': revision})
        self.manager.configure({'base_url': 'https://other.example/v1'})
        self.assertEqual(self.manager.api_key, '')
        self.assertEqual(self.manager.settings['included_models'], [])
        self.assertNotEqual(self.manager.settings['connection_revision'], revision)

    def test_pinned_role_can_capture_direct_connection_without_enabling_auto(self):
        from types import SimpleNamespace
        self.manager.models = [{'id':'vendor/model', 'free':True, 'tool_calling':True, 'input_rate':0, 'output_rate':0}]
        engine = SimpleNamespace(connections=self.connections)
        snapshot = {'values': {'execution': {'mode':'remote'}, 'roles':{
            'worker': {'strategy':'only', 'connection_id':self.identity, 'model':'vendor/model'},
            'planner': {'strategy':'automatic'}, 'reviewer': {'strategy':'automatic'}}}}
        result = _capture_policy(engine, snapshot)
        self.assertEqual(result['providers']['worker']['gateway_type'], 'direct')
        self.assertFalse(next(e for e in result['gateway_connections'] if e['connection_id']==self.identity)['automatic'])
        self.assertFalse(self.manager.settings['automatic'])

if __name__ == '__main__':
    unittest.main()
