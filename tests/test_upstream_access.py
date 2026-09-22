"""Provider access regression cases; no network, Git, subprocesses or real waits."""
import copy
import io
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from cheapos.engine import Engine
from cheapos.model_pool import FreeModelPool
from cheapos.providers import http_failure, ProviderError
from cheapos.routing import PROBE_MARKER, RoutingPause, select_remote
from cheapos import route_health

URL = 'http://localhost:1/v1'
DENIED = "[403]: Error from provider (Console): OpenCode's free tier can only be used from within OpenCode"
KEY_REQUIRED = 'This model requires an opencode API key — add one in Settings → Providers.'


def rejection(message=DENIED, model='oc/ling', status=403, gateway='omniroute'):
    error = HTTPError(URL, status, 'denied', {'Retry-After': '3600'},
                      io.BytesIO(json.dumps({'error': {'message': message}}).encode()))
    return http_failure(error, {'gateway': gateway, 'model': model})


def model(name, **extra):
    return {'id': name, 'free': True, 'tool_calling': True, **extra}


class UpstreamAccessTests(unittest.TestCase):
    def test_opencode_premium_refusal_excludes_only_model_and_keeps_ambiguous_auth_fatal(self):
        for prefix in ('', '[402]: ', '[402]: [402]: '):
            error = rejection(prefix + KEY_REQUIRED, 'oc/union-alpha', 402)
            self.assertEqual((error.code, error.scope), ('upstream_access_denied', 'model'))
            self.assertNotIn(KEY_REQUIRED, str(error))
        raw = HTTPError(URL, 402, 'denied', {}, io.BytesIO(json.dumps(
            {'error': {'code': 'premium_model_requires_key', 'message': 'private upstream details'}}).encode()))
        error = http_failure(raw, {'gateway': 'omniroute', 'model': 'oc/union-alpha'})
        self.assertEqual((error.code, error.scope), ('upstream_access_denied', 'model'))
        self.assertNotIn('private', str(error))
        with tempfile.TemporaryDirectory() as directory:
            pool = FreeModelPool(directory)
            pool.record(URL, 'oc/union-alpha', 'reviewer', error=error, connection_revision='one')
            pool = FreeModelPool(directory)
            denied = pool.observation(URL, 'oc/union-alpha', 'one')
            self.assertTrue(denied['cooling_down'])
            self.assertEqual(denied['failure']['scope'], 'model')
            self.assertFalse(denied['failure']['quality_impact'])
            for name, revision in (('oc/free', 'one'), ('groq/qwen', 'one'), ('oc/union-alpha', 'two')):
                self.assertFalse(pool.observation(URL, name, revision)['cooling_down'])
        for message, name, status, gateway in (
                (KEY_REQUIRED, 'groq/qwen', 402, 'omniroute'),
                (KEY_REQUIRED, 'oc/union-alpha', 401, 'omniroute'),
                (KEY_REQUIRED, 'oc/union-alpha', 402, 'openai'),
                ('Payment required', 'oc/union-alpha', 402, 'omniroute'),
                (KEY_REQUIRED + ' private suffix', 'oc/union-alpha', 402, 'omniroute')):
            error = rejection(message, name, status, gateway)
            self.assertEqual(error.code, f'http_{status}')
            self.assertEqual(route_health.classify(error)['scope'], 'connection')

    def test_known_upstream_denial_is_scoped_without_leaking_error_body(self):
        for message, name, status in ((DENIED, 'oc/ling', 403),
                ('No active credentials for provider: groq. private details', 'groq/qwen', 401)):
            error = rejection(message, name, status)
            self.assertEqual((error.code, error.scope, error.retry_after), ('upstream_access_denied', 'provider', None))
            self.assertEqual(route_health.classify(error)['category'], 'credential_access')
            from cheapos import branch_pause
            self.assertEqual(branch_pause.classify(error, {})['cause'], 'provider_connection')
            self.assertNotIn(message, str(error))
        for message, name, status, gateway in ((DENIED, 'groq/qwen', 403, 'omniroute'),
                (DENIED, 'oc/ling', 401, 'omniroute'), (DENIED, 'oc/ling', 403, 'direct'),
                ('Invalid client API key', 'oc/ling', 401, 'omniroute'),
                ('Forbidden', 'oc/ling', 403, 'omniroute'),
                ('No active credentials for provider: other. private', 'oc/ling', 401, 'omniroute')):
            error = rejection(message, name, status, gateway)
            self.assertEqual(error.code, f'http_{status}')
            self.assertEqual(route_health.classify(error)['scope'], 'connection')
            self.assertIsNone(error.retry_after)

    def test_denial_cools_only_provider_and_revision_without_quality_penalty(self):
        with tempfile.TemporaryDirectory() as directory:
            pool = FreeModelPool(directory)
            pool.record(URL, 'oc/ling', 'worker', error=rejection(), connection_revision='one')
            pool = FreeModelPool(directory)  # same boundary after restart
            sibling = pool.observation(URL, 'oc/other', 'one')
            self.assertTrue(sibling['cooling_down'])
            self.assertEqual(sibling['cooldown_scope'], 'provider')
            self.assertFalse(sibling['retry_known'])
            self.assertEqual(sibling.get('failures', 0), 0)
            self.assertFalse(pool.observation(URL, 'groq/qwen', 'one')['cooling_down'])
            self.assertFalse(pool.observation(URL, 'oc/ling', 'two')['cooling_down'])

    def test_probe_denial_skips_siblings_and_selects_another_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            pool = FreeModelPool(directory)
            catalog = [model(name) for name in ('oc/ling', 'oc/other', 'groq/qwen')]
            gateway = SimpleNamespace(settings={}, pool=pool, matches=lambda url: True,
                catalog=lambda **kw: {'status': 'ready', 'models': catalog})
            task = {'providers': {}, 'events': [], 'route': {'base_url': URL, 'preferred': {'worker': 'oc/ling'}}}
            def request(*args, **kw):
                if kw['config_override']['model'] == 'oc/ling': raise rejection()
                return {'tool_calls': [{'id': 'probe', 'function': {'name': 'routing_ready',
                    'arguments': json.dumps({'marker': PROBE_MARKER})}}]}
            engine = SimpleNamespace(gateway=gateway, event=Mock(), store=Mock(), parse_call=Engine.parse_call,
                                     request=Mock(side_effect=request))
            runtime = SimpleNamespace(task=task, failed_models=set(), route_wait_started_at=1000)
            select_remote(engine, runtime)
            self.assertEqual([c.kwargs['config_override']['model'] for c in engine.request.call_args_list], ['oc/ling', 'groq/qwen'])
            self.assertEqual(task['providers']['worker']['model'], 'groq/qwen')
            self.assertEqual(runtime.failed_models, set())
            self.assertIsNone(runtime.route_wait_started_at)

    def test_cached_auth_denial_is_a_prerequisite_not_an_hour_of_fake_work(self):
        for error in (rejection(), ProviderError('private', code='http_403')):
            with self.subTest(code=error.code), tempfile.TemporaryDirectory() as directory:
                pool = FreeModelPool(directory)
                pool.record(URL, 'oc/ling', 'worker', error=error)
                catalog = [model('oc/ling'), model('oc/other'), model('unrelated/image', tool_calling=False),
                           model('paid/coder', free=False)]
                gateway = SimpleNamespace(settings={}, pool=pool, matches=lambda url: True,
                    catalog=lambda **kw: {'status': 'ready', 'models': catalog})
                engine = SimpleNamespace(gateway=gateway, event=Mock(), store=Mock(), request=Mock())
                task = {'providers': {}, 'events': [], 'route': {'base_url': URL}}
                runtime = SimpleNamespace(task=task, failed_models=set(), route_autorecover=True)
                with self.assertRaisesRegex(RoutingPause, 'access was denied') as caught:
                    select_remote(engine, runtime)
                self.assertIsNone(caught.exception.retry_at)
                engine.request.assert_not_called()

    def test_review_request_automatically_moves_provider_with_saved_evidence(self):
        from tests.test_transport import TransportTests
        for cached, premium in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(cached=cached, premium=premium), tempfile.TemporaryDirectory() as directory:
                engine, runtime, _ = TransportTests().harness()
                task = runtime.task
                cfg = dict(task['providers']['worker'], gateway='omniroute', input_rate=0, output_rate=0)
                task.update(execution={'mode': 'remote'}, route={'base_url': URL},
                            providers={'worker': dict(cfg, model='author/code'), 'reviewer': dict(cfg, model='oc/ling')},
                            checks=[{'passed': True, 'digest': 'current'}], patch='saved patch',
                            pending_review={'branch_candidate_id': 'current', 'review_requests': 2})
                task['limits']['dollars'] = 0
                saved = copy.deepcopy({k: task[k] for k in ('checks', 'patch', 'pending_review', 'limits')})
                runtime.handoffs = 2; runtime.failed_models = set()
                engine.count_recovery_turn = Mock()
                engine.event = lambda t, kind, title, detail: t['events'].append({'id': str(len(t['events'])), 'kind': kind, 'title': title, 'detail': detail})
                pool = FreeModelPool(directory)
                catalog = [model(name) for name in ('oc/ling', 'groq/qwen', 'author/code')]
                if not premium: catalog.append(model('oc/other'))
                catalog += [model('paid/coder', free=False), model('local/coder', local=True)]
                engine.gateway = SimpleNamespace(settings={'base_url': URL}, pool=pool, matches=lambda url: True,
                    catalog=lambda **kw: {'status': 'ready', 'models': catalog})
                def denied(): return rejection(KEY_REQUIRED, 'oc/ling', 402) if premium else rejection()
                if cached: pool.record(URL, 'oc/ling', 'reviewer', error=denied())
                calls = []
                decision = {'tool_calls': [{'id': 'review', 'function': {'name': 'review_decision',
                    'arguments': json.dumps({'decision': 'APPROVE', 'feedback': 'Verified saved evidence'})}}]}
                class Provider:
                    streams_output = False
                    def __init__(self, config): self.config = config
                    def complete(self, messages, tools, maximum):
                        calls.append((self.config['model'], copy.deepcopy(messages)))
                        if self.config['model'] == 'oc/ling': raise denied()
                        return decision, {'prompt_tokens': 3, 'completion_tokens': 2, 'cost': 0}
                    def complete_brief(self, messages, tools, maximum, emit, stopped):
                        return {'tool_calls': [{'id': 'probe', 'function': {'name': 'routing_ready',
                            'arguments': json.dumps({'marker': PROBE_MARKER})}}]}, {'prompt_tokens': 2, 'completion_tokens': 1}
                engine.provider_factory = lambda role, config: Provider(config)
                messages = [{'role': 'user', 'content': 'Review current patch with saved passing checks.'}]
                result = engine.request(runtime, messages, [{'function': {'name': 'review_decision'}}], 'reviewer')
                self.assertEqual(result, decision)
                self.assertEqual([name for name, _ in calls], ['groq/qwen'] if cached else ['oc/ling', 'groq/qwen'])
                from cheapos.instructions.runtime import with_tools
                expected = with_tools(messages, [{'function': {'name': 'review_decision'}}])
                self.assertTrue(all(history == expected for _, history in calls))
                self.assertEqual(expected[1:], messages)  # current tool contract precedes intact evidence
                self.assertEqual(runtime.handoffs, 2)
                self.assertEqual(runtime.failed_models, set())
                self.assertEqual({k: task[k] for k in saved}, saved)
                self.assertEqual(task['usage']['cost'], 0)
                self.assertGreater(task['usage']['reviewer']['tokens'], 0)
                self.assertEqual(task['usage']['uncertain_requests'], 0 if cached else 1)
                self.assertEqual(task['providers']['reviewer']['model'], 'groq/qwen')

    def test_wait_reports_reason_and_total_wait_across_availability_checks(self):
        clock = [1000.0]
        stop = SimpleNamespace(is_set=lambda: False, wait=lambda delay: clock.__setitem__(0, clock[0] + delay))
        task = {'status': 'running', 'limits': {'run_minutes': 90},
                'route_unavailable': {'can_wait': True, 'retry_at': 1002, 'message': 'Connection is temporarily unavailable.', 'scope': 'connection'}}
        runtime = SimpleNamespace(task=task, stop=stop, guard=lambda: None, started=1000)
        snapshots = []
        engine = SimpleNamespace(event=lambda t, *args: snapshots.append(copy.deepcopy(t.get('route_wait'))))
        with patch('cheapos.engine.time.time', side_effect=lambda: clock[0]), patch('cheapos.engine.time.monotonic', side_effect=lambda: clock[0]):
            Engine.wait_for_route(engine, runtime)
            task['route_unavailable']['retry_at'] = 1004
            Engine.wait_for_route(engine, runtime)
        waits = [s for s in snapshots if s]
        self.assertTrue(all(s['started_at'] == 1000 for s in waits))
        self.assertTrue(all(s['message'] == task['route_unavailable']['message'] for s in waits))
        self.assertEqual(runtime.metric_cooldown_wait, 4)
        self.assertEqual(task['status'], 'running')
        self.assertIsNone(task['route_wait'])
