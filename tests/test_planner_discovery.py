"""Grounded planner read recovery; tiny files, scripted replies, no network/Git runs."""
import copy
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cheapos import branch_planner as planner


class PlannerDiscoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name, text in [('scripts/check.py', 'def plan(): return []\n'),
                           ('tests/test_check_selection.py', 'def test_selection(): pass\n'),
                           ('README.md', 'Read scripts/check.py and its focused tests.\n')]:
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(text)
        self.files = ['README.md', 'scripts/check.py', 'tests/test_check_selection.py']
        listing = patch.object(planner.Workspace, 'list_files', return_value=self.files)
        listing.start()
        self.addCleanup(listing.stop)

    def test_failed_paths_get_real_choices_and_existing_evidence(self):
        evidence = {'scripts/check.py': {'path': 'scripts/check.py', 'start_line': 1, 'end_line': 20}}
        for path in ('/Users/example/repo_94/scripts/check.py', 'testing_regressions.py',
                     'A directory of 884 mixed files including source and random data', None):
            result = planner._inspection_recovery({'files': self.files}, {'path': path}, evidence)
            self.assertTrue(set(result['available_paths']) <= set(self.files))
            self.assertIn('scripts/check.py', result['available_paths'])
            self.assertEqual(result['already_read'], list(evidence.values()))
            self.assertNotIn('repo_94', json.dumps(result))
        self.assertEqual(planner._inspection_recovery({}, {}, {})['available_paths'], [])

    def test_absolute_path_never_probes_or_rebases_another_root(self):
        fake = '/Users/example/repo_94/scripts/check.py'
        shadow = self.root / fake.lstrip('/')
        shadow.parent.mkdir(parents=True)
        shadow.write_text('WRONG FILE')
        with patch.object(Path, 'exists', side_effect=AssertionError('Absolute path was probed')):
            with self.assertRaisesRegex(ValueError, 'Absolute paths are not inspected'):
                planner.inspect_project_file(self.root, fake)
        with self.assertRaisesRegex(ValueError, 'Project file not found.*relative path'):
            planner.inspect_project_file(self.root, 'testing_regressions.py')

    def test_directory_discovery_filters_secret_names_and_symlinks(self):
        (self.root / 'scripts' / 'credentials.json').write_text('PRIVATE')
        (self.root / 'scripts' / 'private.key').write_text('PRIVATE')
        (self.root / 'scripts' / 'alias').symlink_to(self.root / 'tests', target_is_directory=True)
        (self.root / 'scripts' / 'node_modules').mkdir()
        result = planner.inspect_project_file(self.root, 'scripts')
        self.assertEqual(result['entries'], ['check.py'])
        self.assertEqual(result['paths'], ['scripts/check.py'])
        self.assertNotIn('PRIVATE', json.dumps(result))
        for path in ('scripts/alias', 'scripts/node_modules', '../outside', 'scripts/credentials.json'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                planner.inspect_project_file(self.root, path)

    def test_duplicate_failure_is_not_executed_again_and_planner_can_finish(self):
        limits = {'dollars': 0, 'requests': 30, 'working_seconds': 900}
        check = 'python3 -B -m unittest tests.test_check_selection'
        proposal = {'items': [{'id': 'selection', 'title': 'Improve selection',
            'instructions': 'Improve the existing selector', 'acceptance_criteria': ['Focused selection works'],
            'required_checks': [check]}], 'limits': limits, 'final_checks': [check]}
        def call(name, arguments, identity):
            return {'tool_calls': [{'id': identity, 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}
        bad = {'path': '/Users/example/repo_94/scripts/check.py'}
        replies = [call('inspect_project_file', {'path': 'scripts/check.py'}, 'read'),
                   call('inspect_project_file', bad, 'bad1'), call('inspect_project_file', bad, 'bad2'),
                   call('inspect_project_file', {'path': 'tests/test_check_selection.py'}, 'tests'),
                   call('propose_branch_plan', {'status': 'plan', 'plan': proposal, 'clarification': ''}, 'plan')]
        requests = []
        def request(runtime, messages, tools, role, **options):
            self.assertEqual(role, 'planner')
            requests.append(copy.deepcopy(messages))
            return replies.pop(0)
        task = {'planning_limits': limits}
        runtime = SimpleNamespace(task=task, stop=threading.Event(), guard=lambda: None)
        engine = SimpleNamespace(request=request)
        captured = {'source': str(self.root), 'prompt': 'Suggest a selector improvement'}
        captured['hash'] = planner._digest(captured)
        with patch.object(planner, 'inspect_project_file', wraps=planner.inspect_project_file) as reads:
            result = planner.plan(engine, runtime, captured)
        self.assertEqual(reads.call_count, 4)  # README context + source + one failed read + tests
        repeated = json.loads(requests[3][-1]['content'])
        self.assertTrue(repeated['repeated_failed_read'])
        self.assertIn('scripts/check.py', repeated['available_paths'])
        self.assertEqual(repeated['already_read'][0]['path'], 'scripts/check.py')
        self.assertIn('def plan(): return []', str(requests[-1]))
        self.assertEqual(result['items'][0]['id'], 'selection')
        self.assertEqual(result['limits'], limits)
        self.assertNotIn('branch_run', task)  # Proposing does not start work.
        self.assertEqual(len(requests), 5)
