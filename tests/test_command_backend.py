"""Deterministic isolation contracts; mocks do not prove Linux enforcement."""
import copy
import json
import os
from pathlib import Path
import signal
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import command_backend as backend, environment, task_commands, verification
from cheapos.engine import Engine, Runtime
from cheapos.preview import Previews
from cheapos.workspace import Workspace


class BackendTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base / 'tasks' / 'one' / 'workspace'
        self.root.mkdir(parents=True)
        (self.root / '.git').mkdir()
        self.source = self.base / 'source'
        self.source.mkdir()
        (self.source / '.git').mkdir()
        self.task = {'id': 'one', 'source': str(self.source), 'workspace': str(self.root),
                     'command_backend': 'bubblewrap'}

    def test_policy_is_strict_and_legacy_restore_does_not_use_new_defaults(self):
        for value in (None, '', {}, 'docker', 'HOST', False):
            with self.subTest(value=value), self.assertRaises(ValueError): backend.select(value)
        with patch.dict(os.environ, {'CHEAPOS_COMMAND_BACKEND': 'bubblewrap'}):
            self.assertEqual(backend.captured({}), 'host')
            self.assertEqual(backend.captured(json.loads(json.dumps(self.task))), 'bubblewrap')
        task_commands.grant(self.task, True)
        self.assertTrue(task_commands.allowed(json.loads(json.dumps(self.task))))
        self.task['command_backend'] = 'host'
        self.assertFalse(task_commands.allowed(self.task))

    def test_unavailable_or_unsupported_never_starts_host_command(self):
        for system in ('Darwin', 'Windows', 'Linux'):
            with self.subTest(system=system), patch.object(backend.platform, 'system', return_value=system), patch.object(backend, 'BWRAP', str(self.base / 'absent')), patch('cheapos.workspace.subprocess.Popen') as popen:
                with self.assertRaisesRegex(ValueError, 'fallback is disabled'):
                    Workspace(self.root).run_checks(['touch', 'unsafe'], threading.Event(), backend='bubblewrap')
                popen.assert_not_called()
                state = environment.inspect({**self.task, 'check_directory': '.'}, ['python3'])
                self.assertEqual(state['missing'], 'command_backend')
                self.assertFalse((self.root / 'unsafe').exists())

    def test_launcher_requires_trusted_non_setuid_binary(self):
        fake = self.base / 'bwrap'
        fake.write_text('fixture')
        fake.chmod(0o755)
        with patch.object(backend.platform, 'system', return_value='Linux'), patch.object(backend, 'BWRAP', str(fake)), patch.object(backend.Path, 'stat', return_value=SimpleNamespace(st_mode=0o104755, st_uid=0)):
            with self.assertRaisesRegex(ValueError, 'non-setuid'): backend.available('bubblewrap')

    def test_mounts_environment_network_and_argv_are_explicit(self):
        component = self.root / 'component'; component.mkdir()
        argv = ['python3', '-c', 'print("literal; $(no shell)")']
        with patch.object(backend, 'available'):
            command, env = backend.launch('bubblewrap', argv, self.root, component,
                                          {'SECRET': 'secret-marker', 'PATH': '/host/custom', 'PYTHONPATH': '/host/private'})
        for flag in ('--unshare-user', '--unshare-pid', '--unshare-net', '--unshare-ipc',
                     '--unshare-uts', '--new-session', '--die-with-parent', '--disable-userns', '--clearenv'):
            self.assertIn(flag, command)
        self.assertNotIn('--share-net', command)
        self.assertNotIn('--ro-bind-try', command)
        self.assertEqual(command.count('--bind'), 1)
        index = command.index('--bind')
        self.assertEqual(command[index:index+3], ['--bind', str(self.root), str(self.root)])
        self.assertEqual(command[-len(argv)-3:], ['--chdir', str(component), '--', *argv])
        self.assertNotIn('secret-marker', json.dumps([command, env]))
        self.assertNotIn('/host', json.dumps([command, env]))
        self.assertEqual(env, {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        self.assertIn(['--ro-bind', str(self.root / '.git'), str(self.root / '.git')],
                      [command[i:i+3] for i in range(len(command))])
        host = {'PATH': '/custom', 'PYTHONPATH': '/host'}
        self.assertEqual(backend.launch('host', argv, self.root, component, host), (argv, host))

    def test_mount_refuses_host_bridges_and_reserved_roots(self):
        file = self.root / 'file'; file.write_text('kept')
        os.link(file, self.base / 'external')
        with self.assertRaisesRegex(ValueError, 'hard-linked'): backend.validate_workspace(self.root)
        (self.base / 'external').unlink()
        if hasattr(os, 'mkfifo'):
            os.mkfifo(self.root / 'fifo')
            with self.assertRaisesRegex(ValueError, 'FIFOs'): backend.validate_workspace(self.root)
            (self.root / 'fifo').unlink()
        for root in ('/', '/tmp', '/usr/test-task', '/proc', '/home/worker'):
            with self.subTest(root=root), self.assertRaisesRegex(ValueError, 'reserved'): backend.validate_workspace(Path(root))
        (self.root / 'outside').symlink_to(self.source, target_is_directory=True)
        backend.validate_workspace(self.root)  # resolved only inside namespace; never mounted
        with self.assertRaises(ValueError): task_commands.directory(self.root, 'outside')

    def test_git_file_is_hidden_and_symlink_marker_is_rejected(self):
        marker = self.root / '.git'; marker.rmdir(); marker.write_text('gitdir: /private/repo')
        with patch.object(backend, 'available'):
            command, _ = backend.launch('bubblewrap', ['true'], self.root, self.root, {})
            self.assertIn(['--ro-bind', '/dev/null', str(marker)], [command[i:i+3] for i in range(len(command))])
            marker.unlink(); marker.symlink_to(self.source)
            with self.assertRaisesRegex(ValueError, 'symlinked Git'):
                backend.launch('bubblewrap', ['true'], self.root, self.root, {})

    def test_runner_resolution_uses_fixed_path_and_rejects_hidden_tools(self):
        tool = self.base / 'private-tool'; tool.write_text('tool'); tool.chmod(0o755)
        self.assertIsNone(backend.executable(str(tool), self.root, self.root))
        with patch.object(backend.shutil, 'which', return_value=str(tool)) as which:
            self.assertIsNone(backend.executable('python3', self.root, self.root))
            which.assert_called_once_with('python3', path=backend.PATH)
        local = self.root / 'runner'; local.write_text('tool'); local.chmod(0o755)
        self.assertEqual(backend.executable('./runner', self.root, self.root), str(local))

    def test_backend_identity_changes_and_missing_runtime_rejects_saved_evidence(self):
        self.task['check_command'] = ['python3', 'test.py']
        launcher = self.base / 'launcher'; launcher.write_text('first')
        with patch.object(backend, 'available'), patch.object(backend, 'BWRAP', str(launcher)), patch.object(backend, 'executable', return_value='/usr/bin/python3'), patch.object(verification, 'Workspace') as workspace, patch.object(verification, 'git', return_value='head'), patch.object(verification, 'runner_identity', return_value=['runner']), patch.object(verification, 'config_identity', return_value={}):
            workspace.return_value.root = self.root
            workspace.return_value.patch.return_value = ''
            first = verification.evidence_identity(self.task)
            self.assertTrue(first)
            self.assertEqual(first, verification.evidence_identity(json.loads(json.dumps(self.task))))
            record = {'command': self.task['check_command'], 'passed': True, 'exit_code': 0,
                      'input_identity': first, 'verification_identity': first, 'truncated': False}
            self.task['checks'] = [record]
            self.assertEqual(verification.reusable_check(self.task, self.task['check_command']), record)
            launcher.write_text('second')
            self.assertIsNone(verification.reusable_check(self.task, self.task['check_command']))
            self.task['command_backend'] = 'host'
            self.assertNotEqual(first, verification.evidence_identity(self.task))
        self.task['command_backend'] = 'bubblewrap'
        with patch.object(backend, 'available', side_effect=ValueError('missing')):
            self.assertIsNone(verification.evidence_identity(self.task))

    def test_launch_failure_has_no_second_attempt_and_cleanup_covers_all_exits(self):
        with patch.object(backend, 'available'), patch('cheapos.workspace.subprocess.Popen', side_effect=OSError('namespace denied')) as popen:
            with self.assertRaisesRegex(OSError, 'namespace denied'):
                Workspace(self.root).run_checks(['true'], threading.Event(), backend='bubblewrap')
            self.assertEqual(popen.call_count, 1)
            self.assertEqual(popen.call_args.args[0][0], backend.BWRAP)
        for state in ('done', 'cancel', 'timeout', 'output', 'callback'):
            process = Mock(pid=123, returncode=0 if state=='done' else -9)
            process.poll.return_value = 0 if state=='done' else None
            stop = Mock(); stop.wait.return_value = state=='cancel'
            callback = Mock(side_effect=RuntimeError('preview failed')) if state=='callback' else None
            real_fstat = os.fstat
            def output_stat(fd):
                value = real_fstat(fd)
                return os.stat_result((*value[:6], 64_000_001, *value[7:])) if state == 'output' else value
            with self.subTest(state=state), patch('cheapos.workspace.os.fstat', side_effect=output_stat), patch.object(backend, 'available'), patch('cheapos.workspace.subprocess.Popen', return_value=process), patch('cheapos.workspace.os.killpg') as kill, patch('cheapos.workspace.time.monotonic', side_effect=lambda: 100 if process.poll.called else 0):
                if state=='callback':
                    with self.assertRaisesRegex(RuntimeError, 'preview failed'):
                        Workspace(self.root).run_checks(['true'], stop, backend='bubblewrap', on_output=callback)
                else:
                    result = Workspace(self.root).run_checks(['true'], stop, timeout=None if state == 'output' else 1, backend='bubblewrap')
                    self.assertEqual(result['passed'], state=='done')
                    self.assertEqual(result['execution_environment']['network'], 'none')
                    self.assertEqual(result['reason'], {'done':None, 'cancel':'cancelled', 'timeout':'timed out', 'output':'output limit exceeded'}[state])
                kill.assert_called_once_with(123, signal.SIGKILL)
                process.wait.assert_called_once()

    def test_preview_rejects_isolated_tasks_before_any_process_or_thread(self):
        manager = Previews(SimpleNamespace(store=SimpleNamespace(root=self.base, get=lambda _: self.task), lock=threading.RLock()))
        with patch('cheapos.preview.subprocess.check_output') as process, patch('cheapos.preview.threading.Thread') as thread:
            with self.assertRaisesRegex(ValueError, 'host fallback is disabled'):
                manager._action('one', 'preview-start', {})
            process.assert_not_called(); thread.assert_not_called()

    def test_exact_grants_bind_backend_and_host_profiles_are_not_reused(self):
        from cheapos.branch_authorization import CheckScopes
        from cheapos.project_permissions import ProjectTestGrants
        grants = Mock(revisions={})
        grants.proposal.return_value = None
        grants.authorize.return_value = (None, None)
        scopes = CheckScopes(grants)
        tool = self.root / 'runner'; tool.write_text('test'); tool.chmod(0o755)
        argv = [str(tool), '--test']
        with patch.object(backend, 'identity', side_effect=lambda mode, *args: {'backend':mode} if mode != 'host' else None):
            scope = scopes.prepare(self.task, argv)
            scopes.consent(self.task, scope, exact=True)
            self.assertTrue(scopes.authorize(self.task, argv))
            changed = {**self.task, 'command_backend':'host'}
            self.assertIsNone(scopes.authorize(changed, argv))
        owner = Mock()
        self.assertIsNone(ProjectTestGrants.proposal(owner, self.task, argv))
        self.assertIsNone(ProjectTestGrants.authorize(owner, self.task, argv)[0])
        self.assertEqual(ProjectTestGrants.visible(owner, self.task), [])
        owner.binding.assert_not_called()

    def test_ungranted_command_is_denied_before_backend_or_launcher(self):
        runtime = SimpleNamespace(task=self.task)
        with patch.object(backend, 'available') as available, patch('cheapos.workspace.subprocess.Popen') as popen:
            result = Engine.checks(SimpleNamespace(), runtime, 'python3 --version', operation='command')
            self.assertEqual(result['code'], 'command_permission_required')
            available.assert_not_called(); popen.assert_not_called()


class DispatchTests(unittest.TestCase):
    def test_small_saved_task_dispatch_retains_receipts_and_cannot_downgrade(self):
        from test_engine import LocalCase
        from cheapos.storage import Store
        fixture = LocalCase()
        fixture.setUp()
        try:
            fixture.engine.command_backend_default = 'bubblewrap'
            task = fixture.fixture()
            task['conversational'] = True
            self.assertEqual(task['command_backend'], 'bubblewrap')
            fixture.engine.command_backend_default = 'host'
            fixture.engine.store.save(task)
            loaded = Store(fixture.engine.store.root).get(task['id'])
            self.assertEqual(loaded['command_backend'], 'bubblewrap')
            task_commands.grant(task, True)
            result = {'command': ['python3', '--version'], 'passed': True, 'exit_code': 0,
                      'reason': None, 'output': 'fixture output', 'truncated': False, 'duration': 0}
            with patch.object(backend, 'available'), patch('cheapos.engine.environment.inspect', return_value={'status':'ready'}), patch('cheapos.engine.evidence_identity', return_value='isolated-proof'), patch.object(Workspace, 'run_checks', return_value=result.copy()) as run:
                command = fixture.engine.checks(Runtime(task), 'python3 --version', operation='command')
                self.assertEqual(run.call_args.kwargs['backend'], 'bubblewrap')
                self.assertEqual(command['execution_environment']['network'], 'none')
                self.assertEqual(task['command_runs'][-1]['output'], 'fixture output')
                self.assertNotIn('verification_identity', command)
                check = fixture.engine.checks(Runtime(task), 'python3 --version')
                self.assertTrue(check['passed'])
                self.assertEqual(check['verification_identity'], 'isolated-proof')
                self.assertEqual(check['execution_environment']['backend'], 'bubblewrap')
                self.assertEqual(run.call_count, 2)
            fixture.engine.store.save(task)
            saved = Store(fixture.engine.store.root).get(task['id'])
            self.assertEqual(saved['checks'][-1]['execution_environment'], check['execution_environment'])
            with patch.object(backend, 'available', side_effect=ValueError('backend unavailable')), patch.object(Workspace, 'run_checks') as run:
                with self.assertRaisesRegex(ValueError, 'backend unavailable'):
                    fixture.engine.checks(Runtime(saved), 'python3 --version')
                run.assert_not_called()
            self.assertEqual(saved['command_backend'], 'bubblewrap')
            self.assertEqual(len(saved['checks']), 1)
        finally:
            fixture.tearDown()
            fixture.doCleanups()
