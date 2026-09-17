import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch
from cheapos.engine import Runtime, ProgressPause, current_evidence, limits_from
from cheapos.verification import evidence_identity
from cheapos.test_profiles import executable_identity
from cheapos.workspace import Workspace
from test_engine import LocalCase


class VerificationTests(LocalCase):
    def test_identity_invalidates_inputs_but_not_metadata(self):
        task = self.fixture()
        identity = evidence_identity(task)
        self.assertTrue(identity)
        record = {'verification_identity': identity}
        task.update(custom_title='Renamed', pinned=True)
        self.assertTrue(current_evidence(task, record))
        root = Path(task['workspace'])
        test = root / 'test_math_utils.py'
        original = test.read_text()
        test.write_text(original + '\n# test changed\n')
        self.assertFalse(current_evidence(task, record))
        test.write_text(original)
        self.assertTrue(current_evidence(task, record))
        task['check_command'].append('-v')
        self.assertFalse(current_evidence(task, record))
        task['check_command'].pop()
        (root / 'pyproject.toml').write_text('[project]\nname="changed"\n')
        self.assertFalse(current_evidence(task, record))
        (root / 'pyproject.toml').unlink()
        task['workspace_generation'] = 1
        self.assertFalse(current_evidence(task, record))
        self.assertFalse(current_evidence(task, {'generation': 1, 'passed': True}))

    def test_real_deadline_stops_process_without_code_repair(self):
        task = self.fixture()
        task['check_command'] = [sys.executable, '-c', 'import time;time.sleep(10)']
        runtime = Runtime(task)
        runtime.started -= task['limits']['run_minutes'] * 60 - 2
        with self.assertRaises(ProgressPause):
            self.engine.checks(runtime)
        check = task['checks'][-1]
        self.assertEqual(check['outcome'], 'task_deadline')
        self.assertLess(check['duration'], 3)
        self.assertLess(check['allowed_seconds'], 2)
        self.assertIsNone(check['verification_identity'])

    def test_explicit_timeout_and_legacy_default(self):
        task = self.fixture()
        task['limits']['check_seconds'] = 360
        task['check_command'] = [sys.executable, '-c', 'pass']
        with patch.object(Workspace, 'run_checks', return_value={'passed':True, 'command':task['check_command'], 'reason':None}) as run:
            self.engine.checks(Runtime(task))
            self.assertEqual(run.call_args.kwargs['timeout'], 360)
            task['limits'].pop('check_seconds')
            self.engine.checks(Runtime(task))
            self.assertEqual(run.call_args.kwargs['timeout'], 90)
        for value in (0, 1801, True, float('nan')):
            with self.assertRaises(ValueError): limits_from({'check_seconds':value})

    def test_process_timeout_is_distinct_from_failed_test(self):
        workspace = Workspace(self.fixture()['workspace'])
        result = workspace.run_checks([sys.executable, '-c', 'import time;time.sleep(10)'], threading.Event(), timeout=.1)
        self.assertEqual(result['reason'], 'timed out')
        result = workspace.run_checks([sys.executable, '-c', 'assert False'], threading.Event(), timeout=1)
        self.assertFalse(result['passed'])
        self.assertIsNone(result['reason'])

    def test_virtualenv_is_not_system_python_and_config_invalidates(self):
        task = self.fixture()
        root = Path(task['workspace']) / '.venv'
        (root / 'bin').mkdir(parents=True)
        (root / 'pyvenv.cfg').write_text('home = fixture\n')
        executable = root / 'bin' / 'python'
        executable.symlink_to(sys.executable)
        self.assertNotEqual(executable_identity(str(executable), root), executable_identity(sys.executable, root))
        task['check_command'] = [str(executable), '-m', 'unittest']
        before = evidence_identity(task)
        (root / 'pyvenv.cfg').write_text('home = changed\n')
        self.assertNotEqual(before, evidence_identity(task))

    def test_documentation_check_reports_only_actual_command(self):
        task = self.fixture()
        Workspace(task['workspace']).write_file('NOTES.md', 'Document the existing behavior.\n')
        task['check_command'] = ['git', 'diff', '--check']
        check = self.engine.checks(Runtime(task))
        self.assertTrue(check['passed'])
        self.assertEqual(check['command'], ['git', 'diff', '--check'])
        self.assertEqual(check['next_action'], 'Only this command was verified.')
        self.assertTrue(current_evidence(task, check))

    def test_longer_command_finishes_with_selected_allowance(self):
        task = self.fixture()
        task['limits']['check_seconds'] = 1
        task['check_command'] = [sys.executable, '-c', 'import time;time.sleep(.2)']
        result = self.engine.checks(Runtime(task))
        self.assertTrue(result['passed'])
        self.assertEqual(result['allowed_seconds'], 1)

    def test_repeated_check_failure_guidance(self):
        task = self.fixture()
        task['check_command'] = [sys.executable, '-c', 'assert False, "demo failure"']
        runtime = Runtime(task)
        first = self.engine.checks(runtime)
        self.assertFalse(first['passed'])
        self.assertEqual(first['outcome'], 'test_failure')
        self.assertEqual(first['next_action'], 'Inspect the failing assertion or process error before changing code.')
        second = self.engine.checks(runtime)
        self.assertFalse(second['passed'])
        self.assertEqual(second['outcome'], 'test_failure')
        self.assertTrue(second['next_action'].startswith('Repeated test failure:'))

    def test_run_checks_includes_pythonpath_for_tests_and_root(self):
        workspace = Workspace(self.fixture()['workspace'])
        check = workspace.run_checks([sys.executable, '-c', 'import os; print("PP:" + os.environ.get("PYTHONPATH", ""))'], threading.Event(), timeout=5)
        self.assertTrue(check['passed'])
        self.assertIn(str(workspace.root), check['output'])
