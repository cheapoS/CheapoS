"""Preference reload tests without agent/Git workflows or model requests."""
import tempfile
import unittest

from cheapos.engine import Engine
from cheapos.storage import write_json


class PreferencePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = self.restart()
        self.execution = {'mode':'delegate','local_model':'gemma4:31b','local_reviewer':'fixture-reviewer'}

    def restart(self):
        engine = Engine(self.temp.name)
        self.addCleanup(engine.shutdown)
        return engine

    def test_local_choice_survives_restart_mode_switch_and_limit_changes(self):
        self.engine.save_preferences({'execution':self.execution})
        self.assertEqual(self.restart().preferences()['execution'], self.execution)
        self.engine.save_preferences({'execution':{'mode':'remote'}})
        self.engine.save_preferences({'limits':{'dollars':0}})
        self.engine.save_preferences({'execution':{'mode':'delegate'}})
        self.assertEqual(self.restart().preferences()['execution'], self.execution)
        self.engine.save_preferences({'execution':{'local_reviewer':''}})
        self.assertEqual(self.restart().preferences()['execution'], {**self.execution,'local_reviewer':''})

    def test_old_or_invalid_limits_do_not_erase_valid_model_choice(self):
        for limits in ('missing', None, {'worker_turns':-1}, {'dollars':'invalid'}):
            saved = {'execution':self.execution}
            if limits != 'missing': saved['limits'] = limits
            write_json(self.engine.store.root/'preferences.json', saved)
            preferences = self.restart().preferences()
            self.assertEqual(preferences['execution'], self.execution)
            self.assertEqual(preferences['limits']['dollars'], 0)

    def test_invalid_execution_does_not_reset_valid_limits(self):
        write_json(self.engine.store.root/'preferences.json', {'execution':{'mode':'obsolete'},'limits':{'dollars':0,'worker_turns':80}})
        preferences = self.restart().preferences()
        self.assertEqual(preferences['limits']['worker_turns'], 80)
        self.assertEqual(preferences['execution']['mode'], 'manual')

    def test_invalid_update_does_not_overwrite_saved_choice(self):
        self.engine.save_preferences({'execution':self.execution})
        for execution in (None, 'local', {'mode':'invalid'}, {'local_model':False}):
            with self.assertRaises(ValueError): self.engine.save_preferences({'execution':execution})
        self.assertEqual(self.restart().preferences()['execution'], self.execution)


if __name__ == '__main__': unittest.main()
