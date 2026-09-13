import copy
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from cheapos.engine import Engine, Runtime, WORKER_TOOLS, limits_from
from cheapos.providers import BudgetError, ProviderError, reconcile, reserve, validate_provider
from cheapos.storage import Store
from cheapos.workspace import Workspace, git
from run import lock_data

CONFIG = {'base_url': 'https://example.invalid/v1', 'model': 'test-model', 'input_rate': 1, 'output_rate': 2, 'key_env': 'CHEAPOS_TEST_KEY'}


def call(name, args=None):
    return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call_1', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args or {})}}]}


def wait_for(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError('Timed out waiting for state')


class LocalCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = Engine(self.root / 'state', fixture_delay=0)

    def tearDown(self):
        self.engine.shutdown()
        for runtime in self.engine.runtimes.values():
            if runtime.thread:
                runtime.thread.join(5)
        self.temp.cleanup()

    def fixture(self, paid=False):
        task = self.engine.create_demo()
        if paid:
            task['demo'] = False
            task['providers'] = {'worker': dict(CONFIG), 'reviewer': dict(CONFIG)}
            self.engine.store.save(task)
        return task

    def finish(self, task):
        self.engine.runtimes[task['id']].thread.join(10)
        self.assertFalse(self.engine.runtimes[task['id']].thread.is_alive())
        return self.engine.store.get(task['id'])


class EngineTests(LocalCase):
    def test_resume_keeps_completed_observations_without_replaying_calls(self):
        task = self.fixture()
        self.engine.event(task, 'assistant', 'Worker', 'Next, add a regression test for inverted bounds.')
        observed = self.engine.file_tool(task, 'read_file', {'path': 'math_utils.py'})
        task['messages'] = [call('write_file', {'path': 'ambiguous.py', 'content': 'do not replay'})]
        self.engine.store.save(task)
        loaded = Store(self.root / 'state').get(task['id'])
        messages = self.engine.initial_messages(loaded)
        context = json.loads(messages[1]['content'])
        self.assertEqual(context['recent_activity'][-1]['detail']['result'], observed)
        self.assertIn('Next, add a regression test', context['recent_activity'][0]['detail'])
        self.assertTrue(all(m['role'] in {'system', 'user'} for m in messages))
        self.assertNotIn('ambiguous.py', json.dumps(messages))

    def test_compaction_keeps_recent_findings_with_bounded_history(self):
        task = self.fixture()
        for index in range(8):
            self.engine.event(task, 'tool', 'read file', {'result': 'x' * 12000, 'index': index})
        context = json.loads(self.engine.initial_messages(task)[1]['content'])
        recent = context['recent_activity']
        self.assertEqual(recent[-1]['detail']['index'], 7)
        self.assertLess(len(json.dumps(recent)), 24500)
        self.assertIn('partial history', context['continuation'])
        self.assertEqual(context['original_task'], task['prompt'])

    def test_real_demo_and_patch_apply(self):
        task = self.fixture()
        original = (Path(task['source']) / 'math_utils.py').read_text()
        self.engine.start(task['id'])
        result = self.finish(task)
        self.assertEqual(result['status'], 'approved', result['error'])
        self.assertEqual([c['passed'] for c in result['checks']], [False, True, True])
        self.assertEqual([c['decision'] for c in result['checkpoints']], ['REQUEST_CHANGES', 'APPROVE'])
        self.assertIn('Ran 4 tests', result['checks'][-1]['output'])
        self.assertEqual(result['usage']['cost'], 0)
        self.assertEqual((Path(task['source']) / 'math_utils.py').read_text(), original)
        patch = self.root / 'result.patch'
        patch.write_text(result['patch'])
        git(task['source'], 'apply', '--check', str(patch))
        git(task['source'], 'apply', str(patch))
        self.assertIn('raise ValueError', (Path(task['source']) / 'math_utils.py').read_text())
        loaded = Engine(self.root / 'state').store.get(task['id'])
        self.assertEqual(loaded['checkpoints'], result['checkpoints'])
        with self.assertRaisesRegex(ValueError, 'already complete'):
            self.engine.start(task['id'])

    def test_missing_usage_stops_before_tool_execution(self):
        task = self.fixture(paid=True)
        class Provider:
            def complete(self, *args):
                return call('write_file', {'path': 'should-not-exist.py', 'content': 'oops'}), {}
        self.engine.provider_factory = lambda *args: Provider()
        self.engine.start(task['id'])
        result = self.finish(task)
        self.assertEqual(result['status'], 'budget_paused')
        self.assertEqual(result['usage']['uncertain_requests'], 1)
        self.assertGreater(result['usage']['cost'], 0)
        self.assertFalse((Path(task['workspace']) / 'should-not-exist.py').exists())

    def test_failed_provider_is_not_retried_and_reservation_is_saved(self):
        task = self.fixture(paid=True)
        calls = []
        class Provider:
            def complete(self, *args):
                calls.append(True)
                raise ProviderError('Network timeout')
        self.engine.provider_factory = lambda *args: Provider()
        self.engine.start(task['id'])
        result = self.finish(task)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['usage']['uncertain_requests'], 1)
        self.assertGreater(result['usage']['cost'], 0)

    def test_budget_prevents_dispatch(self):
        task = self.fixture(paid=True)
        task['limits']['dollars'] = 0
        self.engine.store.save(task)
        self.engine.provider_factory = lambda *args: self.fail('Provider should not be reached')
        self.engine.start(task['id'])
        result = self.finish(task)
        self.assertEqual(result['status'], 'budget_paused')
        self.assertEqual(result['usage']['cost'], 0)

    def test_command_requires_approval_and_can_be_declined(self):
        task = self.fixture(paid=True)
        task['auto_approve_checks'] = False
        self.engine.store.save(task)
        class Provider:
            def complete(self, *args):
                return call('run_checks'), {'prompt_tokens': 10, 'completion_tokens': 10, 'cost': .001}
        self.engine.provider_factory = lambda *args: Provider()
        self.engine.start(task['id'])
        wait_for(lambda: self.engine.store.get(task['id'])['status'] == 'waiting_approval')
        self.assertEqual(self.engine.store.get(task['id'])['checks'], [])
        other = self.fixture()
        with self.assertRaisesRegex(ValueError, 'Another task'):
            self.engine.start(other['id'])
        self.engine.approve_check(task['id'], False)
        result = self.finish(task)
        self.assertEqual(result['status'], 'paused')
        self.assertEqual(result['checks'], [])

    def test_modified_files_during_check_are_not_accepted(self):
        task = self.fixture()
        task['check_command'] = [sys.executable, '-c', "open('new.py','w').write('changed')"]
        result = self.engine.checks(Runtime(task))
        self.assertFalse(result['passed'])
        self.assertIn('changed workspace files', result['reason'])

    def test_takeover_requires_explicit_approval(self):
        task = self.fixture()
        task['status'] = 'takeover_requested'
        self.engine.store.save(task)
        with self.assertRaisesRegex(ValueError, 'explicitly'):
            self.engine.start(task['id'])
        self.assertEqual(self.engine.store.get(task['id'])['active_role'], 'worker')

    def test_restart_does_not_replay_inflight_request(self):
        task = self.fixture(paid=True)
        reservation = reserve(task, CONFIG, [], WORKER_TOOLS, 'worker')
        task['status'] = 'running'
        self.engine.store.save(task)
        loaded = Store(self.root / 'state').get(task['id'])
        self.assertEqual(loaded['status'], 'interrupted')
        self.assertEqual(loaded['usage']['cost'], reservation['cost'])
        self.assertEqual(loaded['in_flight'], reservation)

    def test_keys_are_memory_only_and_settings_are_validated_atomically(self):
        config = {role: dict(CONFIG, api_key='secret-test-key') for role in ['worker', 'reviewer']}
        result = self.engine.configure(config)
        self.assertTrue(result['worker']['key_configured'])
        self.assertNotIn('secret-test-key', json.dumps(result))
        self.assertNotIn('secret-test-key', (self.root / 'state/config.json').read_text())
        config['reviewer']['input_rate'] = float('nan')
        with self.assertRaises(ValueError):
            self.engine.configure(config)
        self.assertEqual(self.engine.config['worker']['model'], 'test-model')


class BudgetTests(LocalCase):
    def test_reconciles_provider_reported_cost_and_tokens(self):
        task = self.fixture(paid=True)
        reservation = reserve(task, CONFIG, [], [], 'reviewer')
        self.assertTrue(reconcile(task, CONFIG, reservation, {'prompt_tokens': 120, 'completion_tokens': 35, 'cost': .034}))
        self.assertAlmostEqual(task['usage']['cost'], .034)
        self.assertEqual(task['usage']['reviewer']['tokens'], 155)
        self.assertEqual(task['usage']['uncertain_requests'], 0)

    def test_missing_cost_is_estimated_from_configured_prices(self):
        task = self.fixture(paid=True)
        reservation = reserve(task, CONFIG, [], [], 'worker')
        reconcile(task, CONFIG, reservation, {'prompt_tokens': 100, 'completion_tokens': 50})
        self.assertAlmostEqual(task['usage']['cost'], .0002)
        self.assertEqual(task['usage']['estimated_requests'], 1)

    def test_invalid_limits_and_remote_http_rejected(self):
        for values in [{'dollars': float('nan')}, {'iterations': 1.5}, {'worker_turns': True}, {'reviewer_tokens': -1}]:
            with self.assertRaises(ValueError):
                limits_from(values)
        with self.assertRaises(ValueError):
            validate_provider(dict(CONFIG, base_url='http://remote.example/api'), 'worker')
        with self.assertRaises(ValueError):
            validate_provider(dict(CONFIG, base_url='https://secret@remote.example/api'), 'worker')

    def test_reviewer_reservation_cannot_exceed_token_limit(self):
        task = self.fixture(paid=True)
        task['limits']['reviewer_tokens'] = 1800
        reservation = reserve(task, CONFIG, [], [], 'reviewer')
        self.assertEqual(reservation['tokens'], 1800)
        with self.assertRaises(BudgetError):
            reserve(task, CONFIG, [], [], 'reviewer')


class WorkspaceTests(LocalCase):
    def test_data_lock_prevents_second_writer(self):
        first = lock_data(self.root / 'locked')
        try:
            with self.assertRaisesRegex(ValueError, 'already in use'):
                lock_data(self.root / 'locked')
        finally:
            first.close()
        lock_data(self.root / 'locked').close()

    def test_path_escape_symlink_and_secret_files_blocked(self):
        task = self.fixture()
        workspace = Workspace(task['workspace'])
        for path in ['../outside.txt', '/tmp/outside.txt', '.git/config', '.env', 'nested/.env.local', 'private.key']:
            with self.assertRaises(ValueError):
                workspace.write_file(path, 'secret')
        (workspace.root / 'link').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            workspace.write_file('link/outside.txt', 'secret')
        (workspace.root / '.env').write_text('SECRET=123')
        (workspace.root / 'safe.py').write_text('safe')
        self.assertNotIn('SECRET', workspace.patch())
        self.assertNotIn('.env', workspace.patch())
        self.assertIn('safe.py', workspace.patch())

    def test_snapshot_excludes_secret_and_dependency_files(self):
        task = self.fixture()
        source = Path(task['source'])
        (source / '.env').write_text('SECRET=123')
        (source / 'key.pem').write_text('secret')
        (source / 'node_modules').mkdir()
        (source / 'node_modules/dep.js').write_text('dependency')
        (source / 'link.py').symlink_to(source / 'math_utils.py')
        workspace, metadata = Workspace.snapshot(source, self.root / 'copy')
        self.assertEqual(workspace.list_files(), ['math_utils.py', 'test_math_utils.py'])
        self.assertEqual(len(metadata['skipped']), 4)

    def test_delete_patch_and_exact_replacement(self):
        workspace = Workspace(self.fixture()['workspace'])
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            workspace.replace_text('math_utils.py', 'absent', 'replacement')
        (workspace.root / 'math_utils.py').unlink()
        self.assertIn('deleted file mode', workspace.patch())

    def test_command_timeout_and_environment(self):
        workspace = Workspace(self.fixture()['workspace'])
        result = workspace.run_checks([sys.executable, '-c', 'import time;time.sleep(5)'], threading.Event(), timeout=.1)
        self.assertFalse(result['passed'])
        self.assertEqual(result['reason'], 'timed out')
        self.assertLess(result['duration'], 2)
        result = workspace.run_checks([sys.executable, '-c', "import os;print(os.environ.get('CHEAPOS_WORKER_API_KEY','absent'))"], threading.Event())
        self.assertEqual(result['output'].strip(), 'absent')


if __name__ == '__main__':
    unittest.main()
