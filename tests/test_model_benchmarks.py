"""Catalog and ranking cases with synthetic metadata; no inference or servers."""
import tempfile
import unittest
from datetime import datetime

from cheapos import access_policy, model_benchmarks, route_health
from cheapos.gateways import normalize_models, refresh_openrouter_free_models
from cheapos.model_pool import FreeModelPool
from cheapos.omniroute import OmniRouteManager


def benchmark(coding=50, agentic=40):
    return {'source': 'Artificial Analysis', 'coding': coding, 'agentic': agentic}


class BenchmarkTests(unittest.TestCase):
    def test_normalization_retains_source_refresh_and_only_valid_indices(self):
        for bad in (None, True, '57', -1, float('inf'), float('nan'), {}, 10**400):
            with self.subTest(bad=repr(bad)[:20]):
                result = normalize_models({'data': [{'id': 'new:free', 'benchmarks': {
                    'artificial_analysis': {'coding_index': 57.1, 'agentic_index': bad,
                                            'intelligence_index': 0, 'unknown_index': 99}}}]}, openrouter=True)[0]
                b = result['benchmarks']
                self.assertEqual((b['coding'], b['intelligence']), (57.1, 0))
                self.assertNotIn('agentic', b)
                self.assertNotIn('unknown', b)
                self.assertEqual((b['source'], b['catalog']), ('Artificial Analysis', 'OpenRouter'))
                self.assertIsNotNone(datetime.fromisoformat(b['refreshed_at']).tzinfo)
        for raw in (None, [], 'bad', {}, {'artificial_analysis': []}, {'other': {'coding_index': 99}}):
            self.assertIsNone(normalize_models({'data': [{'id': 'new', 'benchmarks': raw}]})[0]['benchmarks'])

    def test_refresh_keeps_exact_route_metadata_and_does_not_grant_access(self):
        def item(name, **extra):
            return {'id': name, 'pricing': {'prompt': '0', 'completion': '0'},
                    'supported_parameters': ['tools'], **extra}
        raw = {'artificial_analysis': {'coding_index': 60, 'agentic_index': 0}}
        upstream = {'data': [item('vendor/new:free', benchmarks=raw), item('vendor/unscored:free'),
                            item('nvidia/paid:free', benchmarks=raw, pricing={'prompt': '0', 'completion': '.001'}),
                            item('vendor/text:free', benchmarks=raw, supported_parameters=[])]}
        old = [{'id': 'another/new', 'benchmarks': None}, {'id': 'openrouter/removed:free'}]
        models = {m['id']: m for m in refresh_openrouter_free_models(old, upstream)}
        self.assertNotIn('openrouter/removed:free', models)
        self.assertNotIn('openrouter/nvidia/paid:free', models)
        self.assertIsNone(models['another/new']['benchmarks'])
        self.assertTrue(access_policy.eligible(models['openrouter/vendor/unscored:free']))
        self.assertIsNone(models['openrouter/vendor/unscored:free']['benchmarks'])
        self.assertFalse(access_policy.eligible(models['openrouter/vendor/text:free']))
        scored = models['openrouter/vendor/new:free']
        self.assertEqual(scored['benchmarks']['catalog'], 'OpenRouter')
        self.assertEqual(scored['benchmarks']['agentic'], 0)
        # A fresh catalog without scores must clear old benchmark data.
        refreshed = refresh_openrouter_free_models(list(models.values()), {'data': [item('vendor/new:free')]})
        self.assertIsNone(next(m for m in refreshed if m['id'] == scored['id'])['benchmarks'])

    def test_catalog_projection_preserves_refresh_time_without_renewing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = OmniRouteManager(directory)
            try:
                manager.models = normalize_models({'data': [{'id': 'fixture', 'benchmarks': {
                    'artificial_analysis': {'coding_index': 23}}}]})
                expected = manager.models[0]['benchmarks'].copy()
                for _ in range(2):
                    self.assertEqual(manager.catalog()['models'][0]['benchmarks'], expected)
                self.assertEqual(expected['catalog'], 'Gateway catalog')
            finally:
                manager.shutdown()

    def test_role_priors_keep_unscored_models_and_ignore_stale_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            pool = FreeModelPool(directory); url = 'http://localhost:1234/v1'
            models = [{'id': 'new', 'benchmarks': benchmark(80, 10)},
                      {'id': 'planner', 'benchmarks': benchmark(10, 80)},
                      {'id': 'z-code-pro'}, {'id': 'zero', 'benchmarks': benchmark(0, 0)}]
            for role, expected in [('worker', 'new'), ('reviewer', 'new'), ('planner', 'planner')]:
                ordered = pool.interleave(url, models, role)
                self.assertEqual(ordered[0]['id'], expected)
                self.assertCountEqual(ordered, models)
            self.assertEqual(model_benchmarks.preference({'benchmarks': benchmark(0)}, 'worker'), (0, 0))
            self.assertEqual(model_benchmarks.preference({'benchmarks': benchmark(99), 'metadata_evidence': {'stale': True}}, 'worker'), (1, 0))

    def test_preferences_compatibility_and_observed_outcomes_beat_benchmarks(self):
        with tempfile.TemporaryDirectory() as directory:
            pool = FreeModelPool(directory); url = 'http://localhost:1234/v1'; revision = 'saved'
            models = [{'id': 'a/high', 'benchmarks': benchmark(99, 99)}, {'id': 'z/unscored'}]
            def first(role='worker', preferred=None):
                return pool.interleave(url, models, role, preferred, revision)[0]['id']
            self.assertEqual(first(), 'a/high')
            self.assertEqual(first(preferred='z/unscored'), 'z/unscored')
            pool.record(url, 'z/unscored', 'worker', probe=True, connection_revision=revision,
                        probe_identity=route_health.probe_identity(url, models[1], revision))
            self.assertEqual(first(), 'z/unscored')
            for role in ('worker', 'planner', 'reviewer'):
                for i in range(3):
                    pool.record_outcome(url, 'a/high', role, f'{role}-{i}', 'task', {'invalid_output': 1}, revision)
                self.assertEqual(first(role), 'z/unscored')
            # Re-reading benchmark metadata does not erase recorded failures.
            models[0]['benchmarks'] = benchmark(100, 100)
            pool = FreeModelPool(directory)
            self.assertEqual(first('reviewer'), 'z/unscored')
