import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

from cheapos.engine import Engine
from cheapos.gateways import OmniRouteGateway, OpenAICompatibleGateway, gateway_for, normalize_models
from cheapos.omniroute import OmniRouteManager, validate_settings
from cheapos.providers import ProviderError


class CatalogTests(unittest.TestCase):
    def test_ollama_routes_are_local_but_paid_prices_and_combos_are_not_overridden(self):
        entries=normalize_models({'data':[
            {'id':'ollama/coder','owned_by':'ollama','capabilities':{'tool_calling':True}},
            {'id':'ollama/paid','owned_by':'ollama','pricing':{'prompt':'.000001','completion':'.000001'}},
            {'id':'auto/ollama','owned_by':'combo'}]})
        indexed={m['id']:m for m in entries}
        self.assertTrue(indexed['ollama/coder']['local'])
        self.assertTrue(indexed['ollama/coder']['free'])
        self.assertFalse(indexed['ollama/paid']['free'])
        self.assertFalse(indexed['auto/ollama']['free'])

    def test_free_variants_capabilities_and_unknown_prices(self):
        models = normalize_models({'data': [
            {'id': 'openrouter/coder:free', 'capabilities': {'tool_calling': True}, 'context_length': 32000},
            {'id': 'auto/cheap', 'owned_by': 'combo', 'pricing': {'prompt': '0', 'completion': '0'}},
            {'id': 'some/free-name'}, {'id': 'vendor/model:free'},
            {'id': 'paid', 'pricing': {'prompt': '.000002', 'completion': '.000004'}, 'supported_parameters': ['tools']},
            {'id': 'invalid-price', 'pricing': {'prompt': '-1', 'completion': 'NaN'}},
            {'id': 'openrouter/coder:free'}, None, {'id': ''}
        ]})
        by_id = {m['id']: m for m in models}
        self.assertEqual(len(models), 6)
        free = by_id['openrouter/coder:free']
        self.assertTrue(free['free'])
        self.assertTrue(free['tool_calling'])
        self.assertEqual(free['context_length'], 32000)
        self.assertEqual((by_id['paid']['input_rate'], by_id['paid']['output_rate']), (2, 4))
        self.assertTrue(by_id['paid']['tool_calling'])
        for name in ['auto/cheap', 'some/free-name', 'vendor/model:free', 'invalid-price']:
            self.assertFalse(by_id[name]['free'])
        self.assertIsNone(by_id['some/free-name']['tool_calling'])
        self.assertIsNone(by_id['invalid-price']['input_rate'])
        self.assertTrue(normalize_models({'data': [{'id': 'coder:free'}]}, openrouter=True)[0]['free'])
        with self.assertRaises(ProviderError):
            normalize_models({'data': 'invalid'})

    def test_gateway_keeps_direct_provider_credentials_separate(self):
        config = {'base_url': 'http://127.0.0.1:20128/v1', 'key_env': 'CHEAPOS_WORKER_API_KEY', 'gateway': 'omniroute'}
        with patch.dict(os.environ, {'CHEAPOS_WORKER_API_KEY': 'fixture-provider-key'}):
            self.assertEqual(gateway_for(config).key, '')
            self.assertEqual(gateway_for(config, 'fixture-client-key').key, 'fixture-client-key')
            self.assertIsInstance(gateway_for({**config, 'gateway': 'openai'}), OpenAICompatibleGateway)


class CatalogHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.requests.append((self.path, self.headers.get('Authorization')))
        self.send_response(self.server.status)
        if self.server.identity:
            self.send_header('x-omniroute-route-class', 'CLIENT_API')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'data': [{'id': 'openrouter/coder:free', 'capabilities': {'tool_calling': True}}]}).encode())


class GatewayHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), CatalogHandler)
        self.server.requests, self.server.status, self.server.identity = [], 200, True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.manager = OmniRouteManager(self.temp.name)
        self.manager.configure({'base_url': f'http://127.0.0.1:{self.server.server_port}/v1', 'api_key': 'fixture-client-key'})

    def tearDown(self):
        self.manager.shutdown()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_existing_instance_is_reused_and_only_catalog_is_requested(self):
        with patch('cheapos.omniroute.subprocess.Popen') as spawn:
            self.manager.startup()
            self.manager.thread.join(5)
            state = self.manager.snapshot()
            self.assertEqual(state['status'], 'ready')
            self.assertEqual(state['model_count'], 1)
            self.assertFalse(state['owned'])
            spawn.assert_not_called()
        self.assertEqual(self.server.requests, [('/v1/models', 'Bearer fixture-client-key')])
        self.assertNotIn('fixture-client-key', json.dumps(state))
        with self.assertRaisesRegex(ValueError, 'only stop'):
            self.manager.stop_owned()
        self.manager.configure({'keep_running': False})
        self.manager.shutdown()
        # Disabling keep-running never claims ownership of a reused instance.
        self.assertTrue(OmniRouteGateway({'base_url': self.manager.settings['base_url']}).health())

    def test_auth_and_conflicting_port_never_spawn_a_second_server(self):
        for status, identity, expected in [(401, True, 'auth_required'), (200, False, 'unavailable'), (503, True, 'unavailable')]:
            self.server.status, self.server.identity = status, identity
            with patch('cheapos.omniroute.subprocess.Popen') as spawn:
                self.manager.refresh(start=True)
                self.manager.thread.join(5)
                self.assertEqual(self.manager.snapshot()['status'], expected)
                spawn.assert_not_called()
        self.assertNotIn('fixture-client-key', self.manager.snapshot()['message'])


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = OmniRouteManager(self.temp.name)

    def tearDown(self):
        self.manager.shutdown()
        self.temp.cleanup()

    def test_settings_are_local_and_credentials_are_not_persisted(self):
        self.manager.configure({'api_key': 'fixture-key', 'auto_start': False, 'keep_running': False})
        persisted = self.manager.path.read_text()
        self.assertNotIn('fixture-key', persisted)
        self.assertNotIn('api_key', persisted)
        restored = OmniRouteManager(self.temp.name)
        self.assertFalse(restored.settings['auto_start'])
        self.assertFalse(restored.settings['keep_running'])
        self.assertEqual(restored.api_key, os.environ.get('CHEAPOS_GATEWAY_API_KEY', ''))
        self.manager.configure({'base_url': 'http://127.0.0.1:20129/v1'})
        self.assertEqual(self.manager.api_key, '')
        for url in ['https://remote.example/v1', 'http://0.0.0.0:20128/v1', 'http://user:secret@localhost/v1', 'http://localhost:0/v1', 'http://localhost:99999/v1', 'http://localhost:20128/v1?secret=x']:
            with self.assertRaises(ValueError):
                validate_settings({'base_url': url})

    def test_missing_installation_and_disabled_autostart_are_nonblocking(self):
        with patch.object(self.manager, '_probe', side_effect=ProviderError('offline')), patch.object(self.manager, '_port_open', return_value=False), patch('cheapos.omniroute.find_executable', return_value=None), patch('cheapos.omniroute.subprocess.Popen') as spawn:
            self.manager.startup()
            self.manager.thread.join(5)
            self.assertEqual(self.manager.snapshot()['status'], 'not_installed')
            self.manager.configure({'auto_start': False})
            self.manager.startup()
            self.manager.thread.join(5)
            self.assertEqual(self.manager.snapshot()['status'], 'offline')
            spawn.assert_not_called()

    def test_owned_start_uses_loopback_and_stops_only_when_requested(self):
        process = Mock(pid=123456)
        process.poll.return_value = None
        with patch.object(self.manager, '_probe', side_effect=[ProviderError('offline'), []]), patch.object(self.manager, '_port_open', return_value=False), patch('cheapos.omniroute.find_executable', return_value='/fixture/bin/omniroute'), patch('cheapos.omniroute.subprocess.Popen', return_value=process) as spawn, patch.dict(os.environ, {'CHEAPOS_WORKER_API_KEY': 'fixture-secret'}):
            self.manager.startup()
            self.manager.thread.join(5)
            self.assertEqual(self.manager.snapshot()['status'], 'ready')
            self.assertTrue(self.manager.snapshot()['owned'])
            args, kwargs = spawn.call_args
            self.assertEqual(args[0], ['/fixture/bin/omniroute', 'serve', '--port', '20128', '--no-open', '--no-tray', '--no-recovery'])
            self.assertEqual(kwargs['env']['OMNIROUTE_SERVER_HOST'], '127.0.0.1')
            self.assertNotIn('CHEAPOS_WORKER_API_KEY', kwargs['env'])
            self.assertTrue(kwargs['start_new_session'])
        with self.assertRaisesRegex(ValueError, 'Stop the OmniRoute instance'):
            self.manager.configure({'base_url': 'http://127.0.0.1:20129/v1'})
        with patch.object(self.manager, '_terminate') as terminate:
            self.manager.shutdown()
            terminate.assert_not_called()
            self.manager.configure({'keep_running': False})
            self.manager.shutdown()
            terminate.assert_called_once_with(process)
        self.manager.process = None

    def test_concurrent_start_and_settings_change_cannot_duplicate_process(self):
        entered, release = threading.Event(), threading.Event()
        def probe():
            entered.set()
            release.wait(5)
            return []
        with patch.object(self.manager, '_probe', side_effect=probe), patch('cheapos.omniroute.subprocess.Popen') as spawn:
            self.manager.startup()
            self.assertTrue(entered.wait(2))
            first_thread = self.manager.thread
            self.assertTrue(self.manager.refresh(start=True)['busy'])
            self.assertIs(self.manager.thread, first_thread)
            with self.assertRaisesRegex(ValueError, 'Wait for'):
                self.manager.configure({'auto_start': False})
            release.set()
            first_thread.join(5)
            spawn.assert_not_called()

    def test_startup_failure_is_reported_without_hiding_local_tasks(self):
        process = Mock(pid=123456)
        process.poll.return_value = 1
        with patch.object(self.manager, '_probe', side_effect=ProviderError('offline')), patch.object(self.manager, '_port_open', return_value=False), patch('cheapos.omniroute.find_executable', return_value='/fixture/omniroute'), patch('cheapos.omniroute.subprocess.Popen', return_value=process):
            self.manager.startup()
            self.manager.thread.join(5)
            self.assertEqual(self.manager.snapshot()['status'], 'error')
            self.assertIn('exited during startup', self.manager.snapshot()['message'])
        self.manager.process = None

    @unittest.skipUnless(os.name == 'posix', 'Process-group lifecycle is tested on macOS/Linux')
    def test_stop_terminates_a_real_owned_process(self):
        import sys
        self.manager.process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
        try:
            self.manager.stop_owned()
            self.assertIsNotNone(self.manager.process.poll())
            self.assertEqual(self.manager.snapshot()['status'], 'offline')
        finally:
            self.manager._terminate(self.manager.process)

    def test_managed_tasks_require_their_original_gateway_and_shared_key(self):
        engine = Engine(Path(self.temp.name) / 'engine')
        try:
            engine.gateway.configure({'api_key': 'fixture-client'})
            config = {'base_url': engine.gateway.settings['base_url'], 'gateway': 'omniroute', 'model': 'fixture', 'input_rate': 0, 'output_rate': 0}
            engine.configure({role: {**config, 'api_key': 'fixture-direct'} for role in ['worker', 'reviewer']})
            self.assertEqual(engine.provider_key('worker', engine.config['worker']), 'fixture-client')
            task = engine.create_demo()
            task['demo'] = False
            task['providers'] = engine.config
            engine.store.save(task)
            with self.assertRaisesRegex(ValueError, 'Connect OmniRoute'):
                engine.start(task['id'])
            engine.gateway.configure({'base_url': 'http://127.0.0.1:20129/v1'})
            engine.gateway._set_state('ready', 'fixture', [])
            with self.assertRaisesRegex(ValueError, 'different OmniRoute endpoint'):
                engine.start(task['id'])
            self.assertEqual(engine.provider_key('worker', engine.config['worker']), '')
        finally:
            engine.shutdown()


if __name__ == '__main__':
    unittest.main()

class PoolMetadataTests(unittest.TestCase):
    def test_invalid_explicit_free_prices_are_not_treated_as_zero(self):
        m=normalize_models({'data':[{'id':'openrouter/free:free','pricing':{'prompt':'NaN','completion':'-1'},'capabilities':{'reasoning':True}}]})[0]
        self.assertFalse(m['free']);self.assertTrue(m['reasoning'])

    def test_startup_skips_models_cooling_down_in_the_shared_pool(self):
        from cheapos.startup import catalog_candidates
        entries=[{'id':'bad','free':True,'tool_calling':True,'health':{'cooling_down':True}},
                 {'id':'new','free':True,'tool_calling':True}]
        result=catalog_candidates(entries,'http://127.0.0.1:20128/v1','omniroute')
        self.assertEqual([r['config']['model'] for r in result],['new'])
