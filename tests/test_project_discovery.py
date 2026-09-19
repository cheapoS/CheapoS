"""Small local-file fixtures: no model requests, subprocesses or live services."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_planner as planner, project_context, project_discovery
from cheapos.workspace import allowed_name


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.names = []
        # Exercise real file boundaries and readers, substituting only Git's
        # inventory. This avoids a full task/branch workflow per layout.
        git = patch('cheapos.workspace.git', side_effect=lambda *a, **k: '\0'.join(self.names))
        self.git = git.start()
        self.addCleanup(git.stop)

    def write(self, name, content):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        self.names.append(name)

    def test_nested_apps_guidance_and_validation_are_supplied_before_url_guessing(self):
        self.write('README.md', 'Old prototype: http://127.0.0.1:5188\n')
        self.write('AGENTS.md', 'Production code is in services/site; root HTML is a prototype.\n')
        self.write('services/site/AGENTS.md', 'Use the scripts in this component.\n')
        self.write('services/site/package.json', json.dumps({
            'packageManager': 'pnpm@10.0.0', 'scripts': {'test': 'node --test', 'deploy': 'remote login && deploy'}}))
        self.write('services/site/pnpm-lock.yaml', 'lockfileVersion: 9\n')
        self.write('index.html', '<p>Prototype</p>')
        context = planner.project_context(self.root)
        self.assertEqual(context['manifests'][0]['path'], 'AGENTS.md')
        docs = {d['path']: d for d in context['manifests']}
        self.assertIn('Production code', docs['AGENTS.md']['contents'])
        self.assertIn('services/site/AGENTS.md', docs)
        self.assertIn('services/site/package.json', docs)
        script, = context['validation_scripts']
        self.assertEqual((script['cwd'], script['name'], script['package_managers']),
                         ('services/site', 'test', ['pnpm']))
        self.assertIn('not permission', script['authority'])
        with self.assertRaisesRegex(ValueError, 'URL is not a repository file'):
            planner.inspect_project_file(self.root, 'http://127.0.0.1:5188/AGENTS.md')
        self.assertTrue(all(call.args[1:2] == ('ls-files',) for call in self.git.call_args_list))

    def test_repository_types_and_unknown_layouts_remain_discoverable(self):
        layouts = [
            {'pyproject.toml': '[project]\nname="tiny"', 'tests/test_math.py': 'def test_sum(): pass'},
            {'libraries/a/Cargo.toml': '[package]\nname="a"', 'services/b/go.mod': 'module example/b',
             'apps/c/client.csproj': '<Project />'},
            {'index.html': '<h1>Static site</h1>', 'styles.css': 'body {}'},
            {'sources/logic.custom': 'custom language', 'notes/readme.txt': 'Build conventions not yet defined.'},
        ]
        for index, files in enumerate(layouts):
            with self.subTest(layout=index):
                self.names = []
                for name, content in files.items():
                    self.write(name, content)
                context = planner.project_context(self.root)
                self.assertEqual(set(context['files']), set(files))
                declared = {p for c in context['discovery']['components'] for p in c['manifests']}
                self.assertEqual(declared, {p for p in files if project_discovery.kind(p) == 'manifest'})
                self.assertEqual(context['validation_scripts'], [])  # No invented runners.
                self.assertEqual(context['discovery']['file_count'], len(files))

    def test_directory_pages_reach_components_beyond_initial_summary(self):
        for index in range(65):
            self.write('app%02d/package.json' % index, '{"scripts":{"test":"node --test"}}')
        first = planner.inspect_project_file(self.root, '.')
        second = planner.inspect_project_file(self.root, '.', entry_offset=first['next_entry_offset'])
        self.assertEqual(len(first['paths']), 60)
        self.assertEqual(len(second['paths']), 5)
        self.assertEqual(len(set(first['paths'] + second['paths'])), 65)
        self.assertFalse(second['has_more'])
        self.assertIsNone(second['next_entry_offset'])
        self.assertGreater(first['discovery']['omitted_components'], 0)
        last = planner.inspect_project_file(self.root, 'app64')
        self.assertEqual(last['discovery']['components'][0]['manifests'], ['app64/package.json'])
        self.assertEqual(last['paths'], ['app64/package.json'])
        with self.assertRaises(ValueError):
            planner.inspect_project_file(self.root, '.', entry_offset=-1)

    def test_no_secrets_symlinks_or_config_execution_and_malformed_manifest_is_readable(self):
        self.write('.env', 'secret-value')
        self.write('node_modules/package.json', '{"private":"secret-dependency"}')
        self.write('src/README.md', 'Safe documentation')
        (self.root / 'linked').symlink_to(self.root / 'src', target_is_directory=True)
        self.names.append('linked/README.md')
        self.write('package.json', '{ invalid JSON')
        self.write('setup.py', 'raise RuntimeError("must not execute")')
        context = planner.project_context(self.root)
        self.assertEqual(set(context['files']), {'src/README.md', 'package.json', 'setup.py'})
        self.assertNotIn('secret', json.dumps(context))
        self.assertEqual(context['validation_scripts'], [])
        self.assertIn('{ invalid JSON', json.dumps(context))
        self.assertTrue(all(allowed_name(p) for p in context['files']))

    def test_large_guidance_is_explicitly_partial_and_retrievable(self):
        self.write('AGENTS.md', 'a' * 4500 + '\nUse a scoped check here.\n')
        context = planner.project_context(self.root)
        excerpt = context['manifests'][0]
        self.assertTrue(excerpt['truncated'])
        self.assertEqual(len(excerpt['contents']), 4000)
        full = planner.inspect_project_file(self.root, 'AGENTS.md', query='scoped check')
        self.assertTrue(full['found'])
        self.assertIn('scoped check', full['contents'])

    def test_summary_budget_reports_omissions_without_preventing_more_inspection(self):
        for index in range(12):
            self.write('component%02d/AGENTS.md' % index, '\U0001f30d' * 4000)
        self.write('scripts/readme_demo.py', 'Not a README document')
        context = planner.project_context(self.root)
        self.assertLessEqual(len(json.dumps(context).encode()), 96000)
        self.assertGreater(context['omitted_sources'], 0)
        self.assertTrue(context['files_truncated'])
        self.assertNotIn('scripts/readme_demo.py', [d['path'] for d in context['manifests']])
        document = planner.inspect_project_file(self.root, 'component11/AGENTS.md')
        self.assertEqual(document['contents'], '\U0001f30d' * 4000)

    def test_worker_brief_uses_same_component_facts_and_retains_authorized_command(self):
        self.write('AGENTS.md', 'Root guidance')
        self.write('component/Gemfile', 'source "https://example.invalid"')
        self.write('component/AGENTS.md', 'Component guidance')
        task = {'workspace': str(self.root), 'check_command': ['selected-runner', 'test']}
        with patch('cheapos.project_context.git', return_value='head'):
            brief = project_context.brief(task)
        self.assertEqual(brief['discovery']['components'], planner.project_context(self.root)['discovery']['components'])
        self.assertEqual(brief['test_command']['argv'], task['check_command'])
        self.assertIn('component/AGENTS.md', [d['path'] for d in brief['sources']])
        self.assertLessEqual(len(json.dumps(brief).encode()), 24000)


class ProposalProvenanceTests(unittest.TestCase):
    limits = {'dollars': 0, 'requests': 30}

    def response(self, command):
        proposal = {'items': [{'id': 'one', 'title': 'Small fix', 'instructions': 'Implement the requested fix',
                              'dependencies': [], 'acceptance_criteria': ['The defect is fixed'],
                              'required_checks': [command]}], 'limits': self.limits, 'final_checks': [command]}
        return {'tool_calls': [{'id': 'proposal', 'function': {'name': 'propose_branch_plan', 'arguments': json.dumps(
            {'status': 'plan', 'plan': proposal, 'clarification': ''})}}]}

    def test_invented_command_is_model_error_but_documented_missing_runner_is_setup(self):
        with patch('cheapos.test_profiles.executable_identity', return_value=None):
            with self.assertRaises(planner.PlanningResponseError):
                planner._parse(self.response('Run the identified test command'), self.limits, '/fixture')
            docs = project_discovery.command_evidence({'path': 'CONTRIBUTING.md', 'contents': 'Use `custom-check test`.'})
            with self.assertRaises(planner.PlanningSetupRequired) as stopped:
                planner._parse(self.response('custom-check test'), self.limits, '/fixture', check_evidence=docs)
            self.assertEqual(stopped.exception.plan['final_checks'], ['custom-check test'])
            with self.assertRaises(planner.PlanningResponseError):
                planner._parse(self.response('custom-check invented'), self.limits, '/fixture', check_evidence=docs)

    def test_missing_declared_package_manager_is_a_real_setup_issue(self):
        docs = project_discovery.command_evidence({'path': 'app/package.json', 'contents': json.dumps({
            'packageManager': 'pnpm@10.0.0', 'scripts': {'test': 'node --test'}})})
        with patch('cheapos.test_profiles.executable_identity', return_value=None):
            with self.assertRaises(planner.PlanningSetupRequired):
                planner._parse(self.response('pnpm --dir app test'), self.limits, '/fixture', check_evidence=docs)

    def test_bad_planner_hands_off_and_completes_proposal_without_operator_setup(self):
        task = {'planning_limits': self.limits, 'execution': {'mode': 'remote'}, 'route': {'base_url': 'fixture'},
                'providers': {'planner': {'model': 'bad'}}, 'usage': {'cost': 0}}
        runtime = SimpleNamespace(task=task, stop=threading.Event(), guard=Mock(), failed_models=set())
        inputs = {'source': '/fixture', 'prompt': 'Suggest one small improvement. Explain before changing.'}
        inputs['hash'] = planner._digest(inputs)
        requests = []
        def request(runtime, messages, *args, **kwargs):
            requests.append(copy.deepcopy(messages))
            task['usage']['cost'] += 1
            return self.response('Run the identified test command' if len(requests) < 4 else 'real-check test')
        engine = SimpleNamespace(request=request, event=Mock(), store=SimpleNamespace(save=Mock()))
        def select(*args):
            task['providers']['planner'] = {'model': 'good'}
        with patch.object(planner, 'project_context', return_value={'files': ['AGENTS.md']}), \
                patch('cheapos.test_profiles.executable_identity', side_effect=lambda exe, _: '/bin/check' if exe == 'real-check' else None), \
                patch('cheapos.routing._select_connections', side_effect=select) as selected:
            result = planner.plan(engine, runtime, inputs)
        self.assertEqual(result['final_checks'], ['real-check test'])
        self.assertEqual(selected.call_count, 1)
        self.assertEqual(task['usage']['cost'], 4)
        self.assertEqual(requests[0][:2], requests[-1][:2])
        self.assertIn('not an established environment failure', str(requests[-1]))
        self.assertIn('bad', runtime.failed_models)
        self.assertNotIn('authorization_ref', task)

    def test_saved_strategy_gets_new_map_without_resetting_history_or_usage(self):
        inputs = {'source': '/fixture', 'prompt': 'Keep scope'}
        inputs['hash'] = planner._digest(inputs)
        historical = {'role': 'user', 'content': 'Earlier retained findings'}
        task = {'planning_limits': self.limits, 'usage': {'cost': 8}, 'planning_strategy': {
            'input_hash': inputs['hash'], 'messages': [{'role': 'system', 'content': 'old'},
            {'role': 'user', 'content': 'old map'}, historical], 'attempt': 1, 'discovery': 5,
            'handoffs': 2, 'evidence': {'file': {'path': 'file'}}, 'failed_reads': {'old': {'error': 'missing'}},
            'proposal_requested': True}}
        runtime = SimpleNamespace(task=task, stop=threading.Event(), guard=Mock())
        engine = SimpleNamespace(request=Mock(return_value=self.response('real-check test')))
        with patch.object(planner, 'project_context', return_value={'files': ['new-map-file']}), \
                patch('cheapos.test_profiles.executable_identity', return_value='/bin/check'):
            planner.plan(engine, runtime, inputs)
        strategy = task['planning_strategy']
        self.assertEqual((strategy['attempt'], strategy['discovery'], strategy['handoffs']), (1, 5, 2))
        self.assertEqual(task['usage']['cost'], 8)
        self.assertIn(historical, strategy['messages'])
        self.assertIn('new-map-file', strategy['messages'][1]['content'])
        self.assertEqual(strategy['failed_reads'], {'old': {'error': 'missing'}})
        self.assertNotIn('tool_choice', engine.request.call_args.kwargs)
