"""Small local process fixture plus deterministic permission/evidence tests."""
import copy
import json
import shlex
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import task_commands, verification, check_output
from cheapos.branch_authorization import CheckScopes
from cheapos.branch_controller import BranchController
from cheapos.engine import Engine, Runtime, WORKER_TOOLS, REVIEW_TOOLS
from cheapos.unattended_setup import require_ready
from test_engine import LocalCase, call


class CommandPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.workspace = self.root / 'tasks' / 'one' / 'workspace'
        for path in (self.source, self.workspace):
            (path / '.git').mkdir(parents=True)
        self.task = {'id': 'one', 'source': str(self.source), 'workspace': str(self.workspace)}

    def test_grant_persists_only_for_original_task_and_checkout_identity(self):
        self.assertFalse(task_commands.allowed(self.task))
        task_commands.grant(self.task, True)
        restored = json.loads(json.dumps(self.task))
        self.assertTrue(task_commands.allowed(restored))
        restored['id'] = 'two'
        self.assertFalse(task_commands.allowed(restored))
        restored = copy.deepcopy(self.task)
        restored['workspace'] = str(self.source)
        self.assertFalse(task_commands.allowed(restored))
        (self.workspace / '.git').rename(self.workspace / '.old-git')
        (self.workspace / '.git').mkdir()
        self.assertFalse(task_commands.allowed(self.task))
        task_commands.grant(self.task, False)
        self.assertNotIn('task_command_permission', self.task)
        with self.assertRaises(ValueError): task_commands.grant(self.task, 'true')

    def test_working_directory_rejects_absolute_parent_symlink_and_git_escape(self):
        (self.workspace / 'component').mkdir()
        (self.workspace / 'outside').symlink_to(self.source, target_is_directory=True)
        self.assertEqual(task_commands.directory(self.workspace, 'component'), (self.workspace / 'component').resolve())
        for value in ('../..', str(self.workspace), 'outside', '.git', 'missing', None):
            with self.subTest(value=value), self.assertRaises((ValueError, FileNotFoundError)):
                task_commands.directory(self.workspace, value)

    def test_authorized_variants_and_missing_runner_do_not_grant_other_tasks(self):
        scopes = CheckScopes(Mock())
        scopes.project_grants.authorize.return_value = (None, 'not granted')
        scopes.project_grants.proposal.return_value = None
        task_commands.grant(self.task, True)
        self.assertEqual(scopes.authorize(self.task, ['missing-runner', 'test']), 'task_commands')
        prepared = scopes.prepare(self.task, ['missing-runner', 'test'], allow_missing=True)
        self.assertTrue(prepared['setup_required'])
        self.assertEqual(prepared['command'], ['missing-runner', 'test'])
        task_commands.grant(self.task, False)
        self.assertIsNone(scopes.authorize(self.task, ['missing-runner', 'test']))
        with self.assertRaises(ValueError): scopes.prepare(self.task, ['missing-runner', 'test'])

    def test_setup_permission_does_not_make_missing_workspace_ready(self):
        with patch('cheapos.unattended_setup.environment.inspect', return_value={'status': 'missing', 'evidence': 'runner absent', 'next_step': 'setup'}):
            scopes = [{'command': ['missing-runner']}]
            with self.assertRaises(ValueError): require_ready(self.task, scopes)
            self.assertFalse(require_ready(self.task, scopes, allow_commands=True)['ready'])
            with self.assertRaises(ValueError): require_ready({'workspace': '/missing/task-copy'}, scopes, allow_commands=True)

    def test_commands_invalidate_evidence_even_when_disk_patch_is_unchanged(self):
        self.task['check_command'] = ['python3', 'test.py']
        with patch.object(verification, 'Workspace') as workspace, patch.object(verification, 'git', return_value='head'), patch.object(verification, 'runner_identity', return_value=['runner']), patch.object(verification, 'config_identity', return_value={}):
            workspace.return_value.root = self.workspace
            workspace.return_value.patch.return_value = ''
            before = verification.evidence_identity(self.task)
            self.task['command_environment_revision'] = 1
            self.assertNotEqual(before, verification.evidence_identity(self.task))

    def test_permission_changes_require_idle_task_and_current_directory(self):
        engine = SimpleNamespace(lock=threading.RLock(), runtimes={}, require_active_task=Mock(), store=Mock(), event=Mock(), session_permissions=Mock())
        engine.store.get.return_value = self.task
        with self.assertRaises(ValueError): Engine.set_task_command_permission(engine, 'one', {'enabled': True, 'directory': str(self.source)})
        engine.runtimes['one'] = SimpleNamespace(thread=SimpleNamespace(is_alive=lambda: True))
        with self.assertRaises(ValueError): Engine.set_task_command_permission(engine, 'one', {'enabled': True, 'directory': str(self.workspace)})
        self.assertFalse(task_commands.allowed(self.task))
        engine.runtimes.clear()
        Engine.set_task_command_permission(engine, 'one', {'enabled': True, 'directory': str(self.workspace)})
        self.assertTrue(task_commands.allowed(self.task))
        Engine.set_task_command_permission(engine, 'one', {'enabled': False, 'directory': str(self.workspace)})
        self.assertFalse(task_commands.allowed(self.task))

    def test_only_worker_has_command_tool(self):
        self.assertIn('run_command', [t['function']['name'] for t in WORKER_TOOLS])
        self.assertNotIn('run_command', [t['function']['name'] for t in REVIEW_TOOLS])

    def test_start_grant_requires_explicit_trusted_boolean_and_cannot_expand_on_replay(self):
        for enabled in (None, False, True, 'true'):
            with self.subTest(enabled=enabled):
                task = {**self.task, 'branch_run': {'status': 'awaiting_authorization'}}
                controller = SimpleNamespace(engine=SimpleNamespace(lock=threading.RLock(), store=Mock(), runtimes={}),
                    proposals=Mock(), contract=Mock(return_value={}), _validate_start_inputs=Mock(), _finish_start=Mock(), validate_authority=Mock())
                controller.engine.store.get.return_value = task
                controller.proposals.authorize.return_value = {'id': 'authorization'}
                values = {'proposal_id': 'proposal', 'approved': True}
                if enabled is not None: values['allow_task_commands'] = enabled
                with patch('cheapos.branch_controller.state.require_supported', side_effect=lambda r:r), patch('cheapos.test_policy.approve'):
                    if enabled == 'true':
                        with self.assertRaises(ValueError): BranchController.authorize(controller, 'one', values)
                        controller.proposals.authorize.assert_not_called()
                        continue
                    BranchController.authorize(controller, 'one', values)
                    self.assertEqual(task_commands.allowed(task), enabled is True)
                    task['branch_run']['status'] = 'paused'
                    BranchController.authorize(controller, 'one', {**values, 'allow_task_commands': True})
                    self.assertEqual(task_commands.allowed(task), enabled is True)


class CommandContinuationTests(LocalCase):
    def test_missing_dependency_setup_check_and_independent_review_without_operator_rescue(self):
        task = self.fixture(paid=True)
        task.update(conversational=True, auto_approve_checks=False, status='paused', error_code='environment_setup', environment_setup={'status':'missing','evidence':'dependency absent'})
        self.engine.store.save(task)
        runtime = Runtime(task)
        with patch('cheapos.workspace.Workspace.run_checks') as runner:
            result = self.engine.checks(runtime, 'python3 --version', operation='command')
            self.assertEqual(result['code'], 'command_permission_required')
            runner.assert_not_called()
        self.engine.set_task_command_permission(task['id'], {'enabled': True, 'directory': task['workspace']})
        command = shlex.join([sys.executable, '-c', "from pathlib import Path; assert Path('component/dependency-ready').exists(), 'missing dependency'"])
        setup = shlex.join([sys.executable, '-c', "from pathlib import Path; Path('dependency-ready').write_text('ready'); print('prepared')"])
        (Path(task['workspace']) / 'component').mkdir()
        messages = iter([call('run_checks', {'command': command}), call('run_command', {'command': setup, 'directory': 'component'}),
                         call('run_checks', {'command': command}), call('checkpoint', {'summary': 'Setup completed and actual verification passed.'}),
                         call('review_decision', {'decision': 'APPROVE', 'feedback': 'Independently reviewed the candidate and verification.'})])
        provider = Mock()
        provider.complete.side_effect = lambda *args: (next(messages), {'prompt_tokens': 10, 'completion_tokens': 5, 'cost': 0})
        self.engine.provider_factory = lambda *args: provider
        self.engine.start(task['id'])
        result = self.finish(task)
        self.assertEqual(result['status'], 'approved', result.get('error'))
        self.assertEqual(len(result['checks']), 2)
        self.assertFalse(result['checks'][0]['passed'])
        self.assertTrue(result['checks'][1]['passed'])
        self.assertEqual(len(result['command_runs']), 1)
        self.assertNotIn('verification_identity', result['command_runs'][0])
        self.assertEqual(result['command_environment_revision'], 1)
        self.assertFalse(any(e['title']=='Permission needed to run the verification command' for e in result['events']))
        self.assertEqual(result['checkpoints'][-1]['decision'], 'APPROVE')
        self.assertEqual(check_output.read(self.engine.store, task['id'], result['command_runs'][0]['run_id'])['output'], 'prepared\n')

        # Failure and timeouts return evidence to the worker, never passed tests.
        runtime = Runtime(result)
        check_count = len(result['checks'])
        for reason in ('timed out', 'output limit exceeded'):
            with patch('cheapos.workspace.Workspace.run_checks', return_value={'command': ['python3'], 'passed': False, 'reason': reason, 'output': 'diagnostic', 'duration': 0}):
                failed = self.engine.checks(runtime, 'python3 --version', operation='command')
            self.assertFalse(failed['passed'])
            self.assertEqual(len(result['checks']), check_count)
        with patch('cheapos.workspace.Workspace.run_checks', side_effect=FileNotFoundError('missing runner')):
            failed = self.engine.checks(runtime, 'missing-runner', operation='command')
        self.assertEqual(failed['reason'], 'process could not start')
        result['branch_run'] = {'test_policy_version': 1}
        with self.assertRaisesRegex(ValueError, 'Full-suite'):
            self.engine.checks(runtime, 'python3 -m unittest discover', operation='command')
        result.pop('branch_run')
        def cancel(*args, **kwargs):
            runtime.stop.set()
            return {'command': ['python3'], 'passed': False, 'reason': 'cancelled', 'output': '', 'duration': 0}
        with patch('cheapos.workspace.Workspace.run_checks', side_effect=cancel):
            with self.assertRaises(InterruptedError):
                self.engine.checks(runtime, 'python3 --version', operation='command')
        self.assertEqual(result['command_runs'][-1]['reason'], 'cancelled')
