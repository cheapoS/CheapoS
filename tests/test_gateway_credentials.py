"""Small persistence cases: no real credential store, sockets, sleeps or agents."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cheapos.credentials import CredentialError, CredentialStore
from cheapos.omniroute import OmniRouteManager


class MemoryCredentials:
    backend = 'Test credential store'

    def __init__(self):
        self.items = {}
        self.locked = False

    def get(self, endpoint):
        if self.locked: raise CredentialError('Credential store locked')
        return self.items.get(endpoint)

    def set(self, endpoint, value):
        if self.locked: raise CredentialError('Credential store locked')
        self.items[endpoint] = value

    def delete(self, endpoint):
        if self.locked: raise CredentialError('Credential store locked')
        self.items.pop(endpoint, None)


class GatewayCredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'CHEAPOS_GATEWAY_API_KEY':''})
        env.start()
        self.addCleanup(env.stop)
        self.credentials = MemoryCredentials()
        self.manager = self.restore()
        self.url = self.manager.settings['base_url']

    def restore(self):
        manager = OmniRouteManager(self.temp.name, credential_store=self.credentials)
        self.addCleanup(manager.shutdown)
        return manager

    def save(self):
        self.manager.configure({'api_key':'fixture-client-key', 'remember_key':True})

    def test_restart_restores_key_without_exposing_it_in_settings_or_snapshot(self):
        self.save()
        revision = self.manager.settings['connection_revision']
        restored = self.restore()
        self.assertEqual(restored.api_key, 'fixture-client-key')
        self.assertEqual(restored.settings['connection_revision'], revision)
        self.assertEqual(restored.snapshot()['key_storage']['source'], 'saved')
        for path in Path(self.temp.name).rglob('*.json'):
            self.assertNotIn('fixture-client-key', path.read_text())
        self.assertNotIn('fixture-client-key', json.dumps(restored.snapshot()))
        self.manager.configure({'api_key':'replacement-key'})
        self.assertEqual(self.restore().api_key, 'replacement-key')

    def test_session_only_is_explicit_and_forgetting_removes_the_saved_key(self):
        self.manager.configure({'api_key':'session-key'})
        self.assertEqual(self.restore().api_key, '')
        self.assertEqual(self.credentials.items, {})
        # Promote the current session key without retyping it.
        self.manager.configure({'remember_key':True})
        self.assertEqual(self.restore().api_key, 'session-key')
        self.manager.configure({'remember_key':False})
        self.assertEqual(self.manager.api_key, 'session-key')
        self.assertEqual(self.restore().api_key, '')
        self.assertEqual(self.credentials.items, {})
        self.save()
        self.manager.configure({'api_key':'', 'remember_key':False})
        self.assertEqual(self.manager.api_key, '')
        self.assertFalse(self.manager.snapshot()['key_storage']['saved'])
        self.assertEqual(self.credentials.items, {})

    def test_endpoint_change_clears_key_and_authority_and_never_reuses_old_slot(self):
        self.save()
        revision = self.manager.settings['connection_revision']
        self.manager.configure({'included_models':['provider/model'], 'expected_connection_revision':revision})
        self.manager.configure({'base_url':'http://127.0.0.1:20129/v1'})
        self.assertEqual(self.manager.api_key, '')
        self.assertEqual(self.restore().api_key, '')
        self.assertNotEqual(self.manager.settings['connection_revision'], revision)
        self.assertEqual(self.manager.settings['included_models'], [])
        self.assertEqual(self.credentials.items, {})
        self.manager.configure({'base_url':self.url})
        self.assertEqual(self.manager.api_key, '')

    def test_environment_overrides_saved_key_without_overwriting_it(self):
        self.save()
        with patch.dict(os.environ, {'CHEAPOS_GATEWAY_API_KEY':'environment-key'}):
            restored = self.restore()
            self.assertEqual(restored.api_key, 'environment-key')
            self.assertEqual(restored.snapshot()['key_storage']['source'], 'environment')
            restored.configure({'auto_start':False})
            self.assertEqual(self.credentials.items[self.url], 'fixture-client-key')
        self.assertEqual(self.restore().api_key, 'fixture-client-key')

    def test_locked_store_does_not_crash_startup_and_refresh_can_restore_after_unlock(self):
        self.save()
        self.credentials.locked = True
        restored = self.restore()
        self.assertFalse(restored.snapshot()['key_configured'])
        self.assertIn('Unlock', restored.snapshot()['key_storage']['error'])
        self.credentials.locked = False
        with patch('cheapos.omniroute.OmniRouteGateway') as gateway:
            gateway.return_value.list_models.return_value = []
            restored._probe()
            self.assertEqual(gateway.call_args.args[1], 'fixture-client-key')
        self.assertIsNone(restored.snapshot()['key_storage']['error'])

    def test_failed_store_write_does_not_claim_saved_or_change_connection(self):
        before = self.manager.path.read_text()
        with patch.object(self.credentials, 'set', side_effect=CredentialError('locked')):
            with self.assertRaises(CredentialError): self.save()
        self.assertEqual(self.manager.path.read_text(), before)
        self.assertEqual(self.manager.api_key, '')
        self.assertFalse(self.manager.snapshot()['key_storage']['saved'])

    def test_disk_failure_rolls_back_saved_key_update_and_forget(self):
        self.save()
        before = self.manager.path.read_text()
        for values in ({'api_key':'replacement-key'}, {'api_key':'','remember_key':False},
                       {'api_key':'new-endpoint-key','base_url':'http://127.0.0.1:20129/v1','remember_key':True}):
            with self.subTest(values=values), patch('cheapos.omniroute.write_json', side_effect=OSError('disk full')):
                with self.assertRaises(OSError): self.manager.configure(values)
            self.assertEqual(self.credentials.items, {self.url:'fixture-client-key'})
            self.assertEqual(self.manager.path.read_text(), before)
            self.assertEqual(self.manager.api_key, 'fixture-client-key')

    def test_invalid_input_and_busy_connection_do_not_touch_credentials(self):
        for values in ({'api_key':None}, {'api_key':'bad\x00key'}, {'remember_key':'true'},
                       {'base_url':'https://example.org/v1','api_key':'key','remember_key':True}):
            with self.subTest(values=values), self.assertRaises(ValueError): self.manager.configure(values)
        self.manager.thread = SimpleNamespace(is_alive=lambda:True)
        try:
            with self.assertRaisesRegex(ValueError, 'Wait for'): self.save()
        finally:
            self.manager.thread = None
        self.assertEqual(self.credentials.items, {})


class CredentialAdapterTests(unittest.TestCase):
    def test_slots_are_scoped_to_directory_and_endpoint(self):
        a, b = CredentialStore('/tmp/cheapos-a'), CredentialStore('/tmp/cheapos-b')
        self.assertNotEqual(a._account('http://localhost:1/v1'), a._account('http://localhost:2/v1'))
        self.assertNotEqual(a._account('http://localhost:1/v1'), b._account('http://localhost:1/v1'))
        self.assertEqual(a._account('http://localhost:1/v1'), CredentialStore('/tmp/cheapos-a')._account('http://localhost:1/v1'))

    def test_secret_service_uses_stdin_and_sanitizes_process_failures(self):
        store = CredentialStore('/tmp/cheapos-fixture')
        store.backend = 'Secret Service'
        with patch('cheapos.credentials.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='', stderr='')) as run:
            store.set('http://localhost:1/v1', 'fixture-secret')
            self.assertNotIn('fixture-secret', str(run.call_args.args))
            self.assertEqual(run.call_args.kwargs['input'], 'fixture-secret')
        for failure in (SimpleNamespace(returncode=1,stdout='',stderr='fixture-secret'),
                        subprocess.TimeoutExpired(['secret-tool'],15,output='fixture-secret')):
            options = {'side_effect':failure} if isinstance(failure, Exception) else {'return_value':failure}
            with patch('cheapos.credentials.subprocess.run', **options), self.assertRaises(CredentialError) as error:
                store.get('http://localhost:1/v1')
            self.assertNotIn('fixture-secret', str(error.exception))
        store.backend = None
        with self.assertRaisesRegex(CredentialError, 'unavailable'):
            store.set('http://localhost:1/v1', 'fixture-secret')


if __name__ == '__main__': unittest.main()
