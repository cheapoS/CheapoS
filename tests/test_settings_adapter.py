"""Real Engine methods over tiny disk defaults, no server/model/Git fixture."""
import copy
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from cheapos.engine import Engine
from cheapos.settings_adapter import initialize
from cheapos.settings_store import SettingsConflict


class SettingsAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = Engine.__new__(Engine)
        self.engine.lock = threading.RLock()
        self.engine.store = SimpleNamespace(root=self.root)
        self.engine._legacy_config = {'worker': None, 'reviewer': None, 'planner': None}
        self.engine.startup = SimpleNamespace(busy=lambda: False, models_changed=Mock())
        self.project = str((self.root / 'project').resolve())
        self.engine.projects = lambda include_hidden=False: [{'path': self.project}]
        self.entry = {'version': 1, 'base_url': 'http://127.0.0.1:20128/v1', 'connection_revision': 'rev',
                      'included_models': [], 'connection_id': 'default', 'gateway_type': 'omniroute', 'name': 'gateway'}
        self.gateway = SimpleNamespace(settings={**self.entry, 'enabled': True}, models=[
            {'id': 'worker', 'free': True, 'tool_calling': True}, {'id': 'reviewer', 'free': True, 'tool_calling': True}])
        self.engine.connections = SimpleNamespace(capture=lambda: [copy.deepcopy(self.entry)], selected_id='default',
            for_policy=lambda entry: self.gateway, resolve=lambda cfg, fallback: self.gateway)
        self.engine.gateway = self.gateway
        initialize(self.engine)

    def test_preferences_compatibility_uses_only_new_store(self):
        result = self.engine.save_preferences({'execution': {'mode': 'remote'}, 'limits': {'dollars': 0}})
        self.assertEqual(result['execution']['mode'], 'remote')
        (self.root / 'preferences.json').write_text(json.dumps({'execution': {'mode': 'local'}}))
        self.assertEqual(self.engine.preferences()['execution']['mode'], 'remote')
        self.assertFalse((self.root / 'config.json').exists())

    def test_project_mutations_require_registry_and_one_scope(self):
        self.assertEqual(self.engine.settings_project(self.project), self.project)
        with self.assertRaisesRegex(ValueError, 'Project not found'):
            self.engine.settings_project('/unknown')
        with self.assertRaisesRegex(ValueError, 'one settings scope'):
            self.engine.save_role_mappings({'defaults': {}, 'projects': {self.project: {}}})
        self.engine.save_role_mappings({'projects': {self.project: {'reviewer': 'chosen'}}})
        self.assertEqual(self.engine.effective_role_mapping(self.project)['mapping'], {'reviewer': 'chosen'})

    def test_explicit_automatic_project_override_masks_legacy_pin(self):
        self.engine.save_role_mappings({'defaults': {'reviewer': 'pinned'}})
        self.engine.settings_store.save({'roles.reviewer': {'strategy': 'automatic'}}, project=self.project,
            expected_revision=0, expected_parent_revision=2, operation_id='project')
        result = self.engine.effective_role_mapping(self.project)
        self.assertNotIn('reviewer', result['mapping'])
        self.assertEqual(result['selections']['reviewer'], {'strategy': 'automatic'})

    def test_capture_stale_parent_rejected_and_overrides_retained(self):
        self.engine.save_preferences({'execution': {'mode': 'remote'}})
        with self.assertRaises(SettingsConflict):
            self.engine.settings_capture({'repository': self.project, 'settings': {'expected_revision': 0, 'expected_parent_revision': 1}})
        snapshot = self.engine.settings_capture({'repository': self.project, 'settings': {
            'expected_revision': 0, 'expected_parent_revision': 2, 'overrides': {'limits.dollars': 0, 'keep_up_to_date': True}}})
        self.assertEqual(snapshot['values']['execution']['mode'], 'remote')
        self.assertTrue(snapshot['values']['keep_up_to_date'])
        self.assertEqual(snapshot['sources']['limits.dollars']['scope'], 'draft')

    def test_policy_explicit_empty_connections_never_means_all(self):
        snapshot = self.engine.settings_capture({'settings': {'expected_revision': self.engine.settings_store.view()['revision'], 'overrides': {'allowed_connections': []}}})
        policy = self.engine.settings_policy(snapshot)
        self.assertEqual(policy['gateway_connections'], [])
        self.assertNotIn('gateway_access', policy)
        self.assertEqual(policy['providers'], {'worker': None, 'reviewer': None, 'planner': None})

    def test_only_selection_uses_exact_connection_and_cached_model(self):
        snapshot = self.engine.settings_capture({'settings': {'expected_revision': self.engine.settings_store.view()['revision'], 'overrides': {'roles.worker': {
            'strategy': 'only', 'connection_id': 'default', 'model': 'worker'}}}})
        result = self.engine.settings_policy(snapshot)
        self.assertEqual(result['providers']['worker']['model'], 'worker')
        self.assertEqual(result['providers']['worker']['connection_id'], 'default')
        with self.assertRaisesRegex(ValueError, 'excluded'):
            self.engine.settings_capture({'settings': {'expected_revision': self.engine.settings_store.view()['revision'], 'overrides': {'allowed_connections': [], 'roles.worker': {
                'strategy': 'only', 'connection_id': 'default', 'model': 'worker'}}}})
        self.entry['connection_revision'] = 'new-live-revision'
        self.assertEqual(self.engine.settings_policy(snapshot), result)

    def test_placement_conflicts_are_rejected_before_dispatch(self):
        with self.assertRaisesRegex(ValueError, 'conflicts with local placement'):
            self.engine.settings_capture({'settings': {'expected_revision': 1, 'overrides': {
                'execution.mode': 'local', 'roles.worker': {'strategy': 'only', 'model': 'worker', 'connection_id': 'default'}}}})
        local = {'base_url': 'http://127.0.0.1:11434/v1', 'model': 'local', 'input_rate': 0, 'output_rate': 0}
        with self.assertRaisesRegex(ValueError, 'conflicts with remote placement'):
            self.engine.settings_capture({'settings': {'expected_revision': 1, 'overrides': {
                'execution.mode': 'remote', 'roles.worker': {'strategy': 'only', 'model': 'local', 'connection_id': None, 'provider': local}}}})

    def test_configure_saves_app_binding_atomically_without_config_file(self):
        provider = {'gateway': 'omniroute', 'connection_id': 'default', 'base_url': self.entry['base_url'],
                    'input_rate': 0, 'output_rate': 0}
        self.gateway.matches = lambda url: url == self.entry['base_url']
        self.gateway.api_key = ''
        self.engine.configure({'worker': {**provider, 'model': 'worker'}, 'reviewer': {**provider, 'model': 'reviewer'}})
        self.assertEqual(self.engine.config['worker']['model'], 'worker')
        self.assertEqual(self.engine.settings_store.view()['values']['roles']['worker']['strategy'], 'only')
        self.assertFalse((self.root / 'config.json').exists())
        snapshot = self.engine.settings_capture({})
        self.engine.save_role_mappings({'defaults': {'worker': 'different'}})
        self.assertEqual(self.engine.settings_policy(snapshot)['providers']['worker']['model'], 'worker')
