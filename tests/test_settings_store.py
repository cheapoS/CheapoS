"""Tiny pure/default-file cases: no models, Git, sockets or waits."""
import copy
import tempfile
import threading
import unittest
from pathlib import Path

from cheapos.engine import limits_from
from cheapos.routing import execution_from
from cheapos.providers import validate_provider
from cheapos.settings_store import SettingsStore, SettingsConflict


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SettingsStore(self.temp.name, limits_validator=limits_from,
            execution_validator=execution_from, provider_validator=validate_provider,
            lock=threading.RLock())
        self.project = str((Path(self.temp.name) / 'project').resolve())
        self.store.initialize({'execution': {'mode': 'remote'}, 'limits': {'dollars': 0}})

    def save(self, patch, project=None, remove=(), operation='save'):
        current = self.store.view(project)
        return self.store.save(patch, project=project, expected_revision=current['revision'],
            expected_parent_revision=current['parent_revision'], remove=remove, operation_id=operation)

    def test_explicit_values_and_inheritance(self):
        self.save({'roles.reviewer': {'strategy': 'only', 'model': 'review', 'connection_id': 'default'},
                   'execution.coordinator_assistance': True, 'limits.dollars': 2})
        result = self.save({'roles.reviewer': {'strategy': 'automatic'},
                           'execution.coordinator_assistance': False, 'limits.dollars': 0,
                           'allowed_connections': [], 'keep_up_to_date': True}, self.project, operation='project')
        self.assertEqual(result['values']['roles']['reviewer'], {'strategy': 'automatic'})
        self.assertFalse(result['values']['execution']['coordinator_assistance'])
        self.assertEqual(result['values']['limits']['dollars'], 0)
        self.assertEqual(result['values']['allowed_connections'], [])
        self.assertTrue(result['values']['keep_up_to_date'])
        self.assertEqual(result['sources']['roles.reviewer']['scope'], 'project')
        result = self.save({}, self.project, remove=['roles.reviewer'], operation='remove')
        self.assertEqual(result['values']['roles']['reviewer']['model'], 'review')
        self.assertEqual(result['sources']['roles.reviewer']['scope'], 'defaults')

    def test_revisions_are_scope_local_but_parent_is_checked(self):
        original = self.store.view(self.project)
        self.save({'limits.dollars': 1}, self.project + '-other')
        self.assertEqual(self.store.view(self.project), original)
        self.save({'limits.dollars': 2}, operation='app')
        before = self.store.path.read_bytes()
        with self.assertRaises(SettingsConflict) as caught:
            self.store.save({}, project=self.project, expected_revision=0,
                            expected_parent_revision=1, operation_id='stale')
        self.assertEqual(caught.exception.current['parent_revision'], 2)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_inherited_project_collision_rejects_entire_app_write(self):
        self.save({'roles.reviewer': {'strategy': 'only', 'model': 'same', 'connection_id': 'default'}}, self.project)
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(ValueError, self.project):
            self.save({'roles.worker': {'strategy': 'only', 'model': 'same', 'connection_id': 'default'}}, operation='bad')
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_idempotency_survives_restart_and_rejects_payload_reuse(self):
        patch = {'limits.dollars': 3}
        first = self.store.save(patch, expected_revision=1, operation_id='once')
        restarted = SettingsStore(self.temp.name, limits_validator=limits_from,
            execution_validator=execution_from, provider_validator=validate_provider)
        self.assertEqual(restarted.save(patch, expected_revision=1, operation_id='once'), first)
        self.assertEqual(restarted.read()['generation'], 2)
        with self.assertRaisesRegex(ValueError, 'different settings'):
            restarted.save({'limits.dollars': 4}, expected_revision=1, operation_id='once')

    def test_captured_chats_are_unchanged_after_defaults_change(self):
        a = self.store.capture(self.project, expected_revision=0, expected_parent_revision=1)
        b = self.store.capture(self.project, draft={'limits.dollars': 1})
        before = copy.deepcopy([a, b])
        self.save({'execution.mode': 'local', 'execution.local_model': 'different'})
        self.assertEqual([a, b], before)
        self.assertEqual(a['values']['execution']['mode'], 'remote')
        self.assertEqual(b['sources']['limits.dollars']['scope'], 'draft')
        with self.assertRaises(SettingsConflict):
            self.store.capture(self.project, expected_revision=0, expected_parent_revision=1)

    def test_unknown_fields_invalid_values_and_secrets_rejected(self):
        for patch in ({'limits.typo': 2}, {'execution.coordinator_assistance': 0},
                      {'keep_up_to_date': 'yes'}, {'allowed_connections': None},
                      {'roles.worker': {'strategy': 'prefer', 'model': 'x'}},
                      {'roles.worker': {'strategy': 'only', 'model': 'x', 'provider': {'api_key': 'secret'}}}):
            before = self.store.path.read_bytes()
            with self.assertRaises(ValueError):
                self.save(patch)
            self.assertEqual(self.store.path.read_bytes(), before)

    def test_migration_preserves_pins_provider_and_false_zero_without_secrets(self):
        root = Path(self.temp.name) / 'migrated'
        store = SettingsStore(root, limits_validator=limits_from,
            execution_validator=execution_from, provider_validator=validate_provider)
        provider = {'model': 'worker', 'base_url': 'http://127.0.0.1:20128/v1',
                    'gateway': 'omniroute', 'connection_id': 'default', 'input_rate': 0,
                    'output_rate': 0, 'api_key': 'never-copy'}
        store.initialize({'execution': {'mode': 'manual', 'coordinator_assistance': False,
                                        'coordinator_model': 'remember-me'}, 'limits': {'dollars': 0}},
                         {'defaults': {'reviewer': 'review'}, 'projects': {self.project: {'planner': 'plan'}}},
                         {'worker': provider})
        data = store.view(self.project)['values']
        self.assertEqual(data['roles']['worker']['provider']['connection_id'], 'default')
        self.assertEqual(data['roles']['reviewer']['model'], 'review')
        self.assertEqual(data['roles']['planner']['model'], 'plan')
        self.assertEqual(data['execution']['coordinator_model'], 'remember-me')
        self.assertEqual(data['limits']['dollars'], 0)
        self.assertNotIn('never-copy', store.path.read_text())
        self.assertEqual(store.legacy_role_mappings()['projects'][self.project], {'planner': 'plan'})
        original = store.path.read_bytes()
        store.initialize({'execution': {'mode': 'remote'}})
        self.assertEqual(store.path.read_bytes(), original)

    def test_draft_cannot_introduce_collision(self):
        self.save({'roles.worker': {'strategy': 'only', 'model': 'worker', 'connection_id': 'default'}})
        with self.assertRaisesRegex(ValueError, 'different model'):
            self.store.capture(draft={'roles.reviewer': {'strategy': 'only', 'model': 'worker', 'connection_id': 'default'}})

    def test_legacy_same_model_stays_pinned_but_new_collision_rejected(self):
        root = Path(self.temp.name) / 'legacy'
        store = SettingsStore(root, limits_validator=limits_from,
            execution_validator=execution_from, provider_validator=validate_provider)
        provider = {'model': 'local', 'base_url': 'http://127.0.0.1:11434/v1', 'input_rate': 0, 'output_rate': 0}
        store.initialize({'execution': {'mode': 'manual'}}, providers={'worker': provider, 'reviewer': provider})
        self.assertEqual(store.capture()['values']['roles']['worker']['strategy'], 'only')
        store.save({'limits.dollars': 0}, expected_revision=1, operation_id='keep')
        self.assertEqual(store.view()['values']['roles']['reviewer']['model'], 'local')

    def test_invalid_migration_does_not_create_store(self):
        store = SettingsStore(Path(self.temp.name) / 'bad', limits_validator=limits_from,
            execution_validator=execution_from, provider_validator=validate_provider)
        with self.assertRaises(ValueError):
            store.initialize({'limits': {'dollars': -1}})
        self.assertFalse(store.path.exists())
