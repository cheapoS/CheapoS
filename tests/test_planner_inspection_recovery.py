"""Small planning recovery replays; no Git, sockets, model calls or waits."""
import copy
import json
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_planner as planner


class InspectionRecoveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.inputs = {'source': directory.name, 'prompt': 'Suggest one small improvement; explain before editing.'}
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

    def test_opening_contract_advertises_complete_envelope_and_example_parses(self):
        self.run_plan([self.finish()])
        messages = self.requests[0]['messages']
        self.assertIn('Planning checklist:', messages[0]['content'])
        self.assertIn('Only inspect_project_file and propose_branch_plan are available', messages[0]['content'])
        envelope = json.loads(messages[1]['content'])
        example = envelope['proposal_format_example']
        self.assertEqual(example['plan']['limits'], self.limits)
        schema = planner.TOOLS[0]['function']['parameters']
        plan_schema = schema['properties']['plan']
        item_schema = plan_schema['properties']['items']['items']
        self.assertEqual(set(example), set(schema['required']))
        self.assertEqual(set(example['plan']), set(plan_schema['required']))
        self.assertEqual(set(example['plan']['items'][0]), set(item_schema['required']))
        self.assertFalse(plan_schema['additionalProperties'])
        self.assertFalse(item_schema['additionalProperties'])
        self.assertNotIn('description', item_schema['properties'])
        self.assertNotIn('depends_on', item_schema['properties'])
        # Fill the instructional placeholders with evidence from this fixture.
        example['plan']['items'] = self.proposal['items']
        example['plan']['final_checks'] = self.proposal['final_checks']
        with patch('cheapos.test_profiles.executable_identity', return_value='/fixture/node'):
            self.assertEqual(planner._parse(self.call('propose_branch_plan', example), self.limits), self.proposal)
        state = json.loads(messages[-1]['content'])['planning_state']
        self.assertEqual(state['recent_inspections'], [])
        self.assertEqual(state['recent_failed_paths'], [])
        self.assertEqual(state['supplied_manifest_excerpts'], ['app/package.json'])
        self.assertEqual(state['allowed_tools'], [tool['function']['name'] for tool in reversed(planner.TOOLS)])

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
        reminder = json.loads(messages[-1]['content'])['planning_state']
        self.assertEqual([r['path'] for r in reminder['recent_inspections']], ['app/package.json', 'app/src/main.ts'])
        self.assertEqual(len(reminder['recent_failed_paths']), 3)
        for request in self.requests:
            self.assertEqual(sum('"planning_state"' in m.get('content', '') for m in request['messages']), 1)
        self.assertFalse(any('"planning_state"' in m.get('content', '') for m in self.task['planning_strategy']['messages']))

    def test_invalid_proposal_fields_handoff_and_finish_without_operator_action(self):
        bad = {'status': 'plan', 'plan': copy.deepcopy(self.proposal), 'clarification': ''}
        bad['plan']['items'][0]['invented_instructions_field'] = 'Keep the same scope'
        result, inspected, selected = self.run_plan([
            self.read('app/src/main.ts'), *[self.call('propose_branch_plan', bad) for _ in range(3)], self.finish()])
        self.assertEqual(result, self.proposal)
        self.assertEqual(inspected.call_count, 1)
        self.assertEqual(selected.call_count, 1)
        self.assertEqual(self.task['usage']['tokens'], 150)
        self.assertEqual(self.task['planning_limits'], self.limits)
        self.assertNotIn('authorization_ref', self.task)
        messages = self.requests[-1]['messages']
        self.assertIn('invented_instructions_field', str(messages))
        self.assertEqual(json.loads(messages[-1]['content'])['planning_state']['recent_inspections'][0]['path'], 'app/src/main.ts')
        self.assert_paired(messages)

    def test_reminder_preserves_partial_read_coordinates_without_duplicating_contents(self):
        def inspect(source, path, **kwargs):
            return {**self.inspect(source, path, **kwargs), 'truncated': True, 'has_more': True,
                    'next_start_line': 2, 'next_start_column': 41}
        self.run_plan([self.read('app/src/main.ts'), self.finish()], inspect=inspect)
        messages = self.requests[-1]['messages']
        recent = json.loads(messages[-1]['content'])['planning_state']['recent_inspections'][0]
        self.assertTrue(recent['has_more'])
        self.assertEqual((recent['next_start_line'], recent['next_start_column']), (2, 41))
        self.assertNotIn('contents', recent)
        self.assertIn('retained source for app/src/main.ts', messages[-2]['content'])

    def test_resume_refreshes_catalog_text_even_when_contract_version_is_unchanged(self):
        with self.assertRaises(InterruptedError):
            self.run_plan([self.read('app/src/main.ts'), InterruptedError('restart')])
        saved = self.task['planning_strategy']
        saved['messages'][0]['content'] = 'Obsolete planner instructions'
        before = copy.deepcopy(saved)
        result, inspected, selected = self.run_plan([self.finish()])
        self.assertEqual(result, self.proposal)
        inspected.assert_not_called(); selected.assert_not_called()
        self.assertEqual(saved['messages'][0]['content'], planner.SYSTEM)
        self.assertEqual(saved['messages'][1:], before['messages'][1:])
        for field in ('attempt', 'discovery', 'handoffs', 'evidence', 'failed_reads', 'contract_version'):
            self.assertEqual(saved[field], before[field])

    def test_contract_upgrade_retains_pending_proposal_and_recovery_history(self):
        with self.assertRaises(InterruptedError):
            self.run_plan([self.read('app/src/main.ts'), self.read('app/src/main.ts'), InterruptedError('restart')])
        saved = self.task['planning_strategy']
        saved['contract_version'] = 0
        saved['messages'][0]['content'] = 'Earlier contract'
        saved['messages'][1]['content'] = '{}'
        before = copy.deepcopy(saved)
        result, inspected, selected = self.run_plan([self.finish()])
        self.assertEqual(result, self.proposal)
        inspected.assert_not_called()
        selected.assert_not_called()
        self.assertEqual(saved['messages'][2:], before['messages'][2:])
        for field in ('attempt', 'discovery', 'handoffs', 'evidence', 'failed_reads', 'observed_inspections', 'proposal_requested'):
            self.assertEqual(saved[field], before[field])
        self.assertEqual(saved['contract_version'], planner.CONTRACT_VERSION)
        self.assertEqual(saved['messages'][0]['content'], planner.SYSTEM)
        self.assertEqual(json.loads(saved['messages'][1]['content'])['proposal_format_example']['plan']['limits'], self.limits)
        self.assertEqual(self.task['usage']['tokens'], 140)
        request = self.requests[-1]
        self.assertEqual(request['options']['tool_choice']['function']['name'], 'propose_branch_plan')
        self.assertIn('Submit propose_branch_plan', json.loads(request['messages'][-1]['content'])['planning_state']['next_action'])
        self.assert_paired(request['messages'])

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

    def test_malformed_inspection_is_not_sent_back_as_a_native_call(self):
        self.assert_repaired_inspection('{"path": ')

    def test_missing_path_is_not_sent_back_as_a_native_call(self):
        self.assert_repaired_inspection('{"filename":"app/src/main.ts"}')

    def assert_repaired_inspection(self, arguments):
        batch = self.read('app/src/main.ts')
        batch['tool_calls'].append({'id': 'bad', 'function': {
            'name': 'inspect_project_file', 'arguments': arguments}})
        result, inspected, selected = self.run_plan([batch, self.finish()])
        self.assertEqual(result, self.proposal)
        inspected.assert_called_once()
        selected.assert_not_called()
        messages = self.requests[-1]['messages']
        self.assert_paired(messages)
        self.assertEqual([c['id'] for m in messages for c in m.get('tool_calls', [])], ['1'])
        self.assertIn('retained source for app/src/main.ts', str(messages))
        diagnostic = next(m for m in messages if (m.get('content') or '').startswith('Tool argument diagnostic:'))
        info = json.loads(diagnostic['content'].split(': ', 1)[1])
        self.assertEqual(info['outcome'], 'Rejected before execution.')
        self.assertEqual(info['feedback'][0]['code'], 'invalid_tool_arguments')
        raw = json.loads(self.task['context_evidence'][info['context_reference']]['text'])
        self.assertEqual(raw['assistant']['tool_calls'][-1]['function']['arguments'], arguments)
        self.assertEqual(self.task['usage']['tokens'], 120)

    def test_resume_repairs_legacy_history_without_resetting_attempts_or_reads(self):
        with self.assertRaises(InterruptedError):
            self.run_plan([self.read('app/src/main.ts'), InterruptedError('stopped')])
        saved = self.task['planning_strategy']
        saved['messages'].extend([
            {'role': 'assistant', 'tool_calls': [{'id': 'old-bad', 'function': {
                'name': 'inspect_project_file', 'arguments': '{"path": '}}]},
            {'role': 'tool', 'tool_call_id': 'old-bad', 'content': '{"error":"Expecting value","path":null}'}])
        saved.update(attempt=2, handoffs=3)
        before = copy.deepcopy(saved)
        result, inspected, selected = self.run_plan([self.finish()])
        self.assertEqual(result, self.proposal)
        inspected.assert_not_called()
        selected.assert_not_called()
        for field in ('attempt', 'handoffs', 'discovery', 'evidence', 'failed_reads', 'observed_inspections'):
            self.assertEqual(saved[field], before[field])
        self.assert_paired(self.requests[-1]['messages'])
        self.assertIn('retained source for app/src/main.ts', str(self.requests[-1]['messages']))
        self.assertNotIn('old-bad', [c['id'] for m in self.requests[-1]['messages'] for c in m.get('tool_calls', [])])
        self.assertEqual(self.task['planning_limits'], self.limits)
        self.assertNotIn('authorization_ref', self.task)

    def test_unoffered_call_becomes_diagnostic_and_valid_proposal_finishes(self):
        result, inspected, selected = self.run_plan([self.call('reponse', {'answer': 'Done'}), self.finish()])
        self.assertEqual(result, self.proposal)
        inspected.assert_not_called()
        selected.assert_not_called()
        messages = self.requests[-1]['messages']
        self.assert_paired(messages)
        self.assertFalse(any(m.get('tool_calls') for m in messages))
        self.assertIn('reponse', str(messages))
        self.assertIn('Tool argument diagnostic:', str(messages))

    def test_provider_tool_rejection_explains_both_offered_tools(self):
        from cheapos.providers import ToolCallValidationError
        result, inspected, selected = self.run_plan([
            ToolCallValidationError(), self.read('app/src/main.ts'), self.finish()])
        self.assertEqual(result, self.proposal)
        inspected.assert_called_once()
        selected.assert_not_called()
        feedback = self.requests[1]['messages'][-2]['content']
        self.assertIn('Only inspect_project_file and propose_branch_plan are available', feedback)
        self.assertIn('For inspection', feedback)
        self.assertIn('For a proposal', feedback)

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
