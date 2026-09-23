"""Recovery qualification with a local health cache; no providers or waits."""
import copy
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import reviewer_recovery as recovery, route_health, routing
from cheapos.engine import Engine
from cheapos.model_pool import FreeModelPool
from cheapos.providers import ProviderError
from cheapos.served_identity import ensure_independent, metadata


class QualificationTests(unittest.TestCase):
    def fixture(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        pool = FreeModelPool(directory.name)
        models = [{'id': name, 'free': True, 'tool_calling': True} for name in ('nvidia/unknown', 'groq/reviewer')]
        cfg = {'model': 'old', 'gateway': 'omniroute', 'base_url': 'http://localhost:20128/v1',
               'input_rate': 0, 'output_rate': 0}
        task = {'execution': {'mode': 'remote'}, 'served_identity_version': 1, 'route': {'base_url': cfg['base_url']},
                'providers': {'worker': {'model': 'worker'}, 'reviewer': cfg},
                'reviewer_identity_recovery': {'attempted': ['old']},
                'checks': [{'passed': True}], 'pending_review': {'messages': ['saved']},
                'usage': {'cost': 0}, 'limits': {'cost': 0},
                'request_metrics': [{'role': 'worker', 'dispatched': True, **metadata('worker', 'actual/worker')}]}
        gateway = SimpleNamespace(settings={'base_url': cfg['base_url']}, pool=pool,
                                  catalog=lambda **kw: {'status': 'ready', 'models': models})
        engine = SimpleNamespace(gateway=gateway, connection_for=lambda cfg: gateway,
            store=Mock(), event=Mock(), request=Mock(), _request_routed=Mock(), parse_call=Engine.parse_call)
        runtime = SimpleNamespace(task=task, guard=Mock(), stop=SimpleNamespace(is_set=lambda: False))
        return engine, runtime, models

    def marker(self):
        return {'tool_calls': [{'id': 'probe', 'function': {'name': 'routing_ready',
                                'arguments': json.dumps({'marker': route_health.PROBE_MARKER})}}]}

    def test_bad_catalog_claim_gets_only_probe_then_valid_reviewer_finishes(self):
        engine, runtime, models = self.fixture(); before = copy.deepcopy(runtime.task)
        models.insert(0, {'id': 'nvidia/known-detector', 'free': True, 'tool_calling': True, 'chat_completion': False})
        engine.gateway.pool.interleave = lambda endpoint, candidates, role, **kw: candidates
        engine.request.side_effect = [{'content': 'Classification response, no tools'}, self.marker()]
        messages = [{'role': 'user', 'content': 'Saved candidate and check evidence'}]
        tools = [{'type': 'function', 'function': {'name': 'review_decision'}}]
        def review(rt, delivered, offered, role, cfg, purpose, **kwargs):
            self.assertIs(delivered, messages); self.assertIs(offered, tools)
            self.assertEqual(cfg['model'], 'groq/reviewer')
            ensure_independent(rt.task, {'role': 'reviewer', **metadata(cfg['model'], 'actual/reviewer')})
            return {'decision': 'APPROVE', 'feedback': 'Reviewed the saved evidence.'}
        engine._request_routed.side_effect = review
        self.assertEqual(recovery.request(engine, runtime, messages, tools, 'reviewer')['decision'], 'APPROVE')
        engine._request_routed.assert_called_once()
        self.assertEqual([c.kwargs['config_override']['model'] for c in engine.request.call_args_list], ['nvidia/unknown', 'groq/reviewer'])
        self.assertTrue(all(c.kwargs['purpose'] == 'probe' and c.args[1] == routing.PROBE_MESSAGES for c in engine.request.call_args_list))
        self.assertEqual(runtime.task['progress_state']['route_probes']['reviewer'], 2)
        for key in ('checks', 'pending_review', 'limits', 'usage'):
            self.assertEqual(runtime.task[key], before[key])
        # Resume keeps failed qualification and reuses the current scoped proof.
        runtime.task = json.loads(json.dumps(runtime.task))
        self.assertEqual(recovery.request(engine, runtime, messages, tools, 'reviewer')['decision'], 'APPROVE')
        self.assertEqual(engine.request.call_count, 2)
        self.assertEqual(engine._request_routed.call_count, 2)

    def test_cached_qualification_is_ranked_first_and_bound_to_metadata(self):
        engine, runtime, models = self.fixture(); pool = engine.gateway.pool
        endpoint = runtime.task['providers']['reviewer']['base_url']; model = models[1]
        pool.record(endpoint, model['id'], 'reviewer', probe=True,
                    probe_identity=route_health.probe_identity(endpoint, model, None))
        candidates = recovery.candidates(engine, runtime.task)
        self.assertEqual(candidates[0]['id'], model['id'])
        cfg = recovery.config(engine, runtime.task, model['id'])
        self.assertTrue(recovery.qualify(engine, runtime, cfg, model))
        engine.request.assert_not_called()
        model['context_length'] = 10000
        engine.request.return_value = self.marker()
        self.assertTrue(recovery.qualify(engine, runtime, cfg, model))
        engine.request.assert_called_once()

    def test_real_recovery_response_reuses_probe_after_expired_failure_and_restart(self):
        engine, runtime, models = self.fixture()
        models.pop(0)
        model = models[0]; pool = engine.gateway.pool
        endpoint = runtime.task['providers']['reviewer']['base_url']
        with patch('cheapos.model_pool.time.time', return_value=1):
            pool.record(endpoint, model['id'], 'reviewer', error=ProviderError('Bad response', code='invalid_response'))
        engine.request.return_value = self.marker()
        def response(*args, **kwargs):
            if engine._request_routed.call_count == 1:
                # Qualification alone must retain the actual failure.
                self.assertTrue(pool.observation(endpoint, model['id'])['last_error'])
            return {'content': 'Inspecting the saved evidence.'}
        engine._request_routed.side_effect = response
        with patch('cheapos.model_pool.time.time', return_value=1000):
            recovery.request(engine, runtime, [], [], 'reviewer')
            health = pool.observation(endpoint, model['id'])
            self.assertFalse(health['last_error'])
            self.assertEqual(health['reviewer_responses'], 1)
            engine.gateway.pool = FreeModelPool(pool.path.parent)
            runtime.task = json.loads(json.dumps(runtime.task))
            recovery.request(engine, runtime, [], [], 'reviewer')
        self.assertEqual(engine.request.call_count, 1)
        self.assertEqual(engine._request_routed.call_count, 2)
        self.assertEqual(runtime.task['progress_state']['route_probes']['reviewer'], 1)

    def test_cancelled_probe_never_dispatches_task_or_leaves_inflight_claim(self):
        engine, runtime, models = self.fixture()
        engine.request.side_effect = InterruptedError('Operator pause')
        with self.assertRaises(InterruptedError):
            recovery.request(engine, runtime, [], [], 'reviewer')
        engine._request_routed.assert_not_called()
        self.assertFalse(engine.gateway.pool.inflight_probes)
        self.assertFalse(any(r.get('tool_check_passed') for r in engine.gateway.pool.records.values()))

    def test_shared_request_error_does_not_sweep_candidates(self):
        engine, runtime, models = self.fixture()
        engine.request.side_effect = ProviderError('Malformed shared request', code='http_400', scope='request')
        with self.assertRaises(ProviderError):
            recovery.request(engine, runtime, [], [], 'reviewer')
        engine.request.assert_called_once(); engine._request_routed.assert_not_called()
