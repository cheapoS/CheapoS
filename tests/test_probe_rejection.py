import unittest
from cheapos.route_health import candidate_probe_rejection, probe_identity
from cheapos.providers import ProviderError

class ProbeRejectionTests(unittest.TestCase):
    def test_non_chat_catalog_entries_never_reach_ranking_or_probe(self):
        import json
        import threading
        from types import SimpleNamespace
        from unittest.mock import Mock
        from cheapos.gateways import normalize_models
        from cheapos.routing import _select_remote
        from cheapos.route_health import PROBE_MARKER
        entries = [
            {'id': 'a/image', 'type': 'image', 'capabilities': {'tool_calling': True}},
            {'id': 'b/speech', 'type': 'audio', 'capabilities': {'tool_calling': True}},
            {'id': 'c/vector-embed-1b', 'capabilities': {'tool_calling': True}},
            {'id': 'z/new-coder', 'capabilities': {'tool_calling': True}, 'pricing': {'prompt': '0', 'completion': '0'}},
        ]
        for entry in entries:
            entry['pricing'] = {'prompt': '0', 'completion': '0'}
        models = normalize_models({'data': entries})
        for role in ('planner', 'worker', 'reviewer', 'coordinator'):
            with self.subTest(role=role):
                pool = SimpleNamespace(
                    observation=Mock(return_value={'cooling_down': False}),
                    interleave=Mock(side_effect=lambda endpoint, candidates, *args: candidates),
                    fresh_probe=Mock(return_value=False), claim_probe=Mock(return_value=(True, None)),
                    release_probe=Mock(), record=Mock())
                gateway = SimpleNamespace(settings={'base_url': 'http://localhost:20128/v1'}, pool=pool,
                                          matches=Mock(return_value=True), catalog=Mock(return_value={'status': 'ready', 'models': models}))
                task = {'route': {'base_url': gateway.settings['base_url']}, 'providers': {}, 'events': []}
                runtime = SimpleNamespace(task=task, failed_models=set(), stop=threading.Event(), guard=Mock())
                response = {'tool_calls': [{'function': {'name': 'routing_ready', 'arguments': json.dumps({'marker': PROBE_MARKER})}}]}
                engine = SimpleNamespace(gateway=gateway, event=Mock(), store=SimpleNamespace(save=Mock()),
                                         request=Mock(return_value=response),
                                         parse_call=lambda call: (call['function']['name'], json.loads(call['function']['arguments'])))
                _select_remote(engine, runtime, role)
                self.assertEqual([m['id'] for m in pool.interleave.call_args.args[1]], ['z/new-coder'])
                engine.request.assert_called_once()
                self.assertEqual(engine.request.call_args.kwargs['config_override']['model'], 'z/new-coder')
                self.assertEqual(task['providers'][role]['model'], 'z/new-coder')
                self.assertEqual(task['progress_state']['route_probes'][role], 1)

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
