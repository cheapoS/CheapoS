"""Planning recovery replays: in memory, no Git, sockets, model calls or waits."""
import copy
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_planner as planner


class InspectionRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.inputs = {'source': '/fixture', 'prompt': 'Suggest one small improvement; explain before editing.'}
        self.inputs['hash'] = planner._digest(self.inputs)
        self.limits = {'dollars': 0, 'requests': 30}
        self.task = {'planning_limits': self.limits, 'execution': {'mode': 'remote'},
                     'route': {'base_url': 'fixture'}, 'providers': {'planner': {'model': 'first'}},
                     'usage': {'tokens': 100, 'cost': 0}}
        self.runtime = SimpleNamespace(task=self.task, stop=threading.Event(), guard=Mock(), failed_models=set())
        self.context = {'files': ['app/package.json', 'app/src/main.ts'],
                        'manifests': [{'path': 'app/package.json', 'contents': '{"scripts":{"test":"node --test"}}'}]}
        self.proposal = {'items': [{'id': 'fix', 'title': 'Improve parsing', 'instructions': 'Fix parsing and test it', 'dependencies': [],
                                   'acceptance_criteria': ['Parsing preserves empty input'], 'required_checks': ['node --test']}],
                         'limits': self.limits, 'final_checks': ['node --test']}
        self.requests = []
        self.serial = 0
        self.engine = SimpleNamespace(store=SimpleNamespace(save=Mock()), event=Mock())

    def call(self, name, arguments):
        self.serial += 1
        return {'tool_calls': [{'id': str(self.serial), 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}

    def read(self, path, **kwargs):
        return self.call('inspect_project_file', {'path': path, **kwargs})

    def finish(self):
        return self.call('propose_branch_plan', {'status': 'plan', 'plan': self.proposal, 'clarification': ''})

    def inspect(self, source, path, **kwargs):
        self.assertEqual(source, self.inputs['source'])
        if path not in self.context['files']:
            raise ValueError('Project file not found')
        return {'path': path, 'contents': 'retained source for ' + path, 'hash': path,
                'start_line': kwargs.get('start_line', 1), 'end_line': kwargs.get('start_line', 1)}

    def run_plan(self, replies, inspect=None, select=None):
        responses = iter(replies)
        def request(runtime, messages, tools, role, purpose, **options):
            self.requests.append({'messages': copy.deepcopy(messages), 'options': options,
                                  'model': self.task['providers']['planner']})
            self.task['usage']['tokens'] += 10
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response
        self.engine.request = request
        def choose(*args):
            self.task['providers']['planner'] = {'model': 'replacement'}
        with patch.object(planner, 'project_context', return_value=self.context), \
                patch.object(planner, 'inspect_project_file', side_effect=inspect or self.inspect) as inspected, \
                patch('cheapos.test_profiles.executable_identity', return_value='/fixture/node'), \
                patch('cheapos.routing._select_connections', side_effect=select or choose) as selected:
            result = planner.plan(self.engine, self.runtime, self.inputs)
        return result, inspected, selected

    def assert_paired(self, messages):
        pending = []
        for message in messages:
            if message.get('tool_calls'):
                self.assertFalse(pending)
                pending = [call['id'] for call in message['tool_calls']]
            elif message['role'] == 'tool':
                self.assertIn(message['tool_call_id'], pending)
                pending.remove(message['tool_call_id'])
            else:
                self.assertFalse(pending)
        self.assertFalse(pending)

    def test_different_bad_paths_handoff_after_correction_despite_interleaved_good_reads(self):
        replies = [self.read('C:\fakepath\test.py'), self.read('app/package.json'),
                   self.read('app/nonexistent.ts'), self.read('app/src/main.ts'),
                   self.read('garbled/path.ts`'), self.finish()]
        result, _, selected = self.run_plan(replies)
        self.assertEqual(result, self.proposal)
        self.assertEqual(selected.call_count, 1)
        self.assertEqual(self.requests[-1]['model']['model'], 'replacement')
        self.assertEqual(self.task['usage'], {'tokens': 160, 'cost': 0})
        self.assertEqual(self.task['planning_limits'], self.limits)
        self.assertEqual(self.task['failed_planners'], ['first'])
        self.assertEqual(self.runtime.failed_models, {'first'})
        self.assertNotIn('authorization_ref', self.task)
        messages = self.requests[-1]['messages']
        self.assertEqual(messages[:2], self.requests[0]['messages'][:2])
        self.assertIn('retained source for app/src/main.ts', str(messages))
        self.assertIn('C:', str(messages))
        self.assert_paired(messages)

    def test_single_typo_can_be_corrected_without_switching_or_forcing_proposal(self):
        result, _, selected = self.run_plan([self.read('typo.ts'), self.read('app/src/main.ts'), self.finish()])
        self.assertEqual(result, self.proposal)
        selected.assert_not_called()
        self.assertEqual(self.requests[1]['options'], {})
        self.assertIn('available_paths', str(self.requests[1]['messages']))
        self.assert_paired(self.requests[-1]['messages'])

    def test_repeated_success_ignores_changing_carto_metadata_and_preserves_new_pages(self):
        self.engine.carto = SimpleNamespace(context=Mock(side_effect=lambda *a, **k: {'status': 'ready', 'sequence': len(self.requests)}))
        result, inspected, selected = self.run_plan([
            self.read('app/src/main.ts', start_line=1), self.read('app/src/main.ts', start_line=2),
            self.read('app/src/main.ts', start_line=2), self.finish()])
        self.assertEqual(result, self.proposal)
        self.assertEqual(inspected.call_count, 3)
        selected.assert_not_called()
        self.assertNotIn('tool_choice', self.requests[2]['options'])
        self.assertEqual(self.requests[3]['options']['tool_choice']['function']['name'], 'propose_branch_plan')
        self.assert_paired(self.requests[-1]['messages'])

    def test_failed_batch_retains_success_and_one_reply_per_call(self):
        batch = self.read('not-present.ts')
        batch['tool_calls'].extend(self.read('app/src/main.ts')['tool_calls'])
        result, _, selected = self.run_plan([batch, self.finish()])
        self.assertEqual(result, self.proposal)
        selected.assert_not_called()
        self.assert_paired(self.requests[-1]['messages'])
        self.assertIn('app/src/main.ts', self.task['planning_strategy']['evidence'])

    def test_resume_preserves_failed_inspections_and_switches_without_replaying_them(self):
        with self.assertRaises(InterruptedError):
            self.run_plan([self.read('bad1'), self.read('bad2'), InterruptedError('server stopped')])
        self.task = json.loads(json.dumps(self.task))
        self.runtime.task = self.task
        prior = copy.deepcopy(self.task['planning_strategy']['failed_reads'])
        result, _, selected = self.run_plan([self.read('bad3'), self.finish()])
        self.assertEqual(result, self.proposal)
        self.assertEqual(selected.call_count, 1)
        self.assertTrue(prior.items() <= self.task['planning_strategy']['failed_reads'].items())
        self.assertEqual(self.task['planning_strategy']['discovery'], 3)
        self.assertEqual(self.task['usage']['tokens'], 150)
        self.assert_paired(self.requests[-1]['messages'])

    def test_pinned_planner_is_not_replaced_and_can_recover(self):
        self.task['settings_snapshot'] = {'values': {'roles': {'planner': {'strategy': 'only'}}}}
        result, _, selected = self.run_plan([self.read('bad1'), self.read('bad2'), self.read('bad3'), self.finish()])
        self.assertEqual(result, self.proposal)
        selected.assert_not_called()
        self.assertNotIn('failed_planners', self.task)
        self.assertEqual(self.requests[-1]['model']['model'], 'first')

    def test_real_inspections_are_not_capped_at_six(self):
        result, inspected, selected = self.run_plan([
            *[self.read('app/src/main.ts', start_line=n) for n in range(1, 11)], self.finish()])
        self.assertEqual(result, self.proposal)
        self.assertEqual(inspected.call_count, 10)
        selected.assert_not_called()
        self.assertTrue(all('tool_choice' not in request['options'] for request in self.requests))
