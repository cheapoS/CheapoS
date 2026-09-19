import copy
import hashlib
import json
import sys
import shlex
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from cheapos import branch_planner as planner
from cheapos.workspace import git


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        git(self.root, 'init', '-q')
        self.limits = {'dollars': 0, 'working_seconds': 900, 'requests': 30}
        self.valid = {'items': [{'id': 'one', 'title': 'Add reader', 'instructions': 'Implement reader', 'dependencies': [], 'acceptance_criteria': ['Reader parses a row'], 'required_checks': [shlex.join([sys.executable, '-m', 'unittest'])]}], 'limits': self.limits, 'final_checks': [shlex.join([sys.executable, '-m', 'unittest'])]}
        self.task = {'planning_limits': self.limits, 'request_metrics': [], 'usage': {'cost': 0}}
        self.runtime = SimpleNamespace(task=self.task, stop=threading.Event(), guard=lambda: None)
        self.requests = []
        self.offered = []

    def reply(self, plan=None):
        value = {'status': 'plan', 'plan': plan or self.valid, 'clarification': ''}
        return {'tool_calls': [{'id': 'call', 'function': {'name': 'propose_branch_plan', 'arguments': json.dumps(value)}}]}

    def engine(self, responses):
        def request(runtime, messages, tools, role, purpose, **options):
            self.requests.append(copy.deepcopy(messages))
            self.offered.append((copy.deepcopy(tools), copy.deepcopy(options)))
            self.assertEqual(role, 'planner')
            self.assertEqual(purpose, 'branch_planning')
            self.assertEqual(tools[0]['function']['name'], 'propose_branch_plan')
            self.assertTrue(all(t['function']['name'] in {'propose_branch_plan', 'inspect_project_file'} for t in tools))
            runtime.task['request_metrics'].append({'id': str(len(self.requests)), 'purpose': purpose})
            return responses.pop(0)
        return SimpleNamespace(
            request=request, 
            effective_role_mapping=lambda project: {'mapping': {'planner': 'p', 'worker': 'w', 'reviewer': 'r'}, 'error': None}
        )

    def test_prompt_document_and_combined_paths_capture_whole_plain_document(self):
        (self.root / 'spec.md').write_text('Implement a reader. Then test it.\nNo Markdown checkboxes needed.\n')
        for prompt, document in [('Implement a reader', None), ('', 'spec.md'), ('Preserve Unicode', 'spec.md')]:
            with self.subTest(prompt=prompt, document=document):
                captured = planner.capture_inputs(self.root, prompt, document)
                output = planner.plan(self.engine([self.reply()]), self.runtime, captured)
                self.assertEqual(output, self.valid)
                sent = json.loads(self.requests[-1][1]['content'])['captured_inputs']
                self.assertEqual(sent['prompt'], prompt)
                self.assertEqual(sent['document']['contents'] if document else sent['document'], (self.root / 'spec.md').read_text() if document else None)
        self.assertEqual(len(self.task['request_metrics']), 3)

    def test_capture_does_not_reread_changed_document(self):
        (self.root / 'spec.md').write_text('Original complete job\n')
        captured = planner.capture_inputs(self.root, '', 'spec.md')
        (self.root / 'spec.md').write_text('New unrelated job\n')
        planner.plan(self.engine([self.reply()]), self.runtime, captured)
        self.assertIn('Original complete job', self.requests[-1][1]['content'])
        captured['prompt'] = 'tampered'
        with self.assertRaises(ValueError): planner.plan(self.engine([]), self.runtime, captured)

    def test_rejects_unsafe_missing_binary_empty_and_oversize_documents(self):
        (self.root / 'okay').write_text('spec')
        (self.root / '.env').write_text('private')
        (self.root / 'link').symlink_to('okay')
        (self.root / 'big').write_bytes(b'x' * (planner.MAX_DOCUMENT_BYTES + 1))
        (self.root / 'binary').write_bytes(b'a\0b')
        (self.root / 'badutf').write_bytes(b'\xff')
        (self.root / 'empty').write_text(' ')
        for name in ('.env', 'link', 'big', 'binary', 'badutf', 'empty', 'missing', '../outside', str(self.root / 'okay')):
            with self.subTest(name=name), self.assertRaises(ValueError): planner.capture_inputs(self.root, '', name)
        with self.assertRaises(ValueError): planner.capture_inputs(self.root, '')

    def test_distinct_repair_strategies_preserve_authority_and_never_run_side_effects(self):
        bad = {'tool_calls': [{'function': {'name': 'write_file', 'arguments': '{}'}}]}
        captured = planner.capture_inputs(self.root, 'Do work')
        with self.assertRaisesRegex(ValueError, 'after two repairs'):
            planner.plan(self.engine([bad] * 6), self.runtime, captured)
        self.assertEqual(len(self.requests), 6)
        self.assertTrue(self.task['strategy_continuation'])
        self.requests.clear()
        self.assertEqual(planner.plan(self.engine([self.reply()]), self.runtime, captured), self.valid)

    def test_conflicting_scope_returns_clarification_without_retry(self):
        (self.root / 'spec').write_text('Delete the reader')
        captured = planner.capture_inputs(self.root, 'Keep the reader', 'spec')
        reply = self.reply()
        reply['tool_calls'][0]['function']['arguments'] = json.dumps({'status': 'clarification', 'plan': None, 'clarification': 'Should the reader be kept or deleted?'})
        with self.assertRaises(planner.ClarificationRequired) as raised:
            planner.plan(self.engine([reply]), self.runtime, captured)
        self.assertIn('kept or deleted', raised.exception.question)
        self.assertEqual(len(self.requests), 1)

    def test_repair_receives_rejected_call_and_specific_missing_field(self):
        response = self.reply()
        invalid = json.loads(response['tool_calls'][0]['function']['arguments'])
        del invalid['status']
        response['tool_calls'][0]['function']['arguments'] = json.dumps(invalid)
        original = copy.deepcopy(response)
        engine = self.engine([response, self.reply()])
        events = []
        engine.event = lambda task, kind, title, detail: events.append((kind, detail))
        result = planner.plan(engine, self.runtime, planner.capture_inputs(self.root, 'Implement the utility'))
        self.assertEqual(result, self.valid)
        repair = self.requests[-1]
        self.assertEqual(repair[-2]['tool_calls'], response['tool_calls'])
        self.assertEqual(repair[-1]['role'], 'tool')
        self.assertEqual(repair[-1]['tool_call_id'], response['tool_calls'][0]['id'])
        self.assertIn('missing: status', repair[-1]['content'])
        self.assertEqual(events[0][0], 'planning_repair')
        self.assertEqual(events[0][1]['attempt'], 1)
        self.assertEqual(response, original)

    def test_complete_plan_accepts_only_absent_or_null_clarification_metadata(self):
        value = json.loads(self.reply()['tool_calls'][0]['function']['arguments'])
        for empty in ('missing', None):
            candidate = copy.deepcopy(value)
            if empty == 'missing': candidate.pop('clarification')
            else: candidate['clarification'] = empty
            reply = self.reply(); reply['tool_calls'][0]['function']['arguments'] = json.dumps(candidate)
            self.assertEqual(planner._parse(reply, self.limits), self.valid)
        for ambiguous in (False, [], {}, 'Should I change the scope?'):
            candidate = dict(value, clarification=ambiguous)
            reply = self.reply(); reply['tool_calls'][0]['function']['arguments'] = json.dumps(candidate)
            with self.assertRaises(ValueError): planner._parse(reply, self.limits)
        for candidate in ({'status': 'clarification', 'plan': None}, {'status': 'plan'}, {'plan': self.valid}, dict(value, unauthorized=True)):
            reply = self.reply(); reply['tool_calls'][0]['function']['arguments'] = json.dumps(candidate)
            with self.assertRaises(ValueError): planner._parse(reply, self.limits)

    def test_budget_widening_missing_checks_and_truncated_plan_rejected(self):
        changed = copy.deepcopy(self.valid)
        changed['limits']['dollars'] = 100
        missing = copy.deepcopy(self.valid)
        missing['items'][0]['required_checks'] = []
        truncated = self.reply()
        truncated['finish_reason'] = 'length'
        for response in (self.reply(changed), self.reply(missing), truncated):
            with self.subTest(response=response), self.assertRaises(ValueError):
                planner.plan(self.engine([response] * 6), self.runtime, planner.capture_inputs(self.root, 'Work'))

    def test_prose_and_shell_checks_receive_field_specific_repair(self):
        for field, bad in [('item', 'List all files'), ('final', 'python3 -m unittest && echo passed')]:
            invalid = copy.deepcopy(self.valid)
            if field == 'item': invalid['items'][0]['required_checks'] = [bad]
            else: invalid['final_checks'] = [bad]
            result = planner.plan(self.engine([self.reply(invalid), self.reply()]), self.runtime,
                                  planner.capture_inputs(self.root, 'Implement reader'))
            self.assertEqual(result, self.valid)
            feedback = self.requests[-1][-1]['content']
            self.assertIn('items[one].required_checks[0]' if field == 'item' else 'final_checks[0]', feedback)
            self.assertIn('List' if field == 'item' else 'shell', feedback.lower() if field != 'item' else feedback)

    def test_model_cannot_enable_measurement(self):
        proposed = dict(self.valid, measurement=True)
        with self.assertRaisesRegex(ValueError, 'Only the operator'):
            planner._parse(self.reply(proposed), self.limits)

    def test_context_first_discovery_retains_assumptions_in_signed_plan(self):
        (self.root / 'package.json').write_text('{"scripts":{"test":"node --test"}}')
        (self.root / 'controls.js').write_text('function restartServer() {}')
        (self.root / '.env').write_text('SECRET')
        (self.root / 'linked').symlink_to(self.root / 'controls.js')
        inspect = {'tool_calls': [{'id': 'read', 'function': {'name': 'inspect_project_file', 'arguments': '{"path":"controls.js"}'}}]}
        reply = self.reply()
        value = json.loads(reply['tool_calls'][0]['function']['arguments'])
        value['assumptions'] = ['Reuse the existing restartServer control.']
        reply['tool_calls'][0]['function']['arguments'] = json.dumps(value)
        result = planner.plan(self.engine([inspect, reply]), self.runtime, planner.capture_inputs(self.root, 'Add a restart button'))
        context = json.loads(self.requests[0][1]['content'])['project_context']
        self.assertIn('controls.js', context['files'])
        self.assertNotIn('.env', context['files'])
        self.assertNotIn('linked', context['files'])
        self.assertIn('node --test', context['manifests'][0]['contents'])
        self.assertIn('restartServer', self.requests[1][-1]['content'])
        self.assertEqual(self.task['planning_assumptions'], value['assumptions'])
        self.assertIn(value['assumptions'][0], result['items'][0]['instructions'])

    def test_repeated_failed_discovery_preserves_error_and_repairs_without_reading_private_files(self):
        (self.root / '.env').write_text('TOP_SECRET')
        inspect = {'tool_calls': [{'function': {'name': 'inspect_project_file', 'arguments': '{"path":".env"}'}}]}
        result = planner.plan(self.engine([inspect] * 3 + [self.reply()]), self.runtime,
                              planner.capture_inputs(self.root, 'Improve existing controls'))
        self.assertEqual(result, self.valid)
        self.assertEqual(len(self.requests), 4)
        self.assertNotIn('TOP_SECRET', json.dumps(self.requests))
        self.assertIn('Project inspection did not advance', self.requests[-1][-1]['content'])
        self.assertIn('repeated_failed_read', json.dumps(self.requests[-1]))
        self.assertEqual([t['function']['name'] for t in self.offered[0][0]], ['propose_branch_plan', 'inspect_project_file'])
        for tools, options in self.offered:
            self.assertEqual([t['function']['name'] for t in tools], ['propose_branch_plan', 'inspect_project_file'])
            self.assertNotIn('tool_choice', options)
        with self.assertRaises(ValueError):
            planner.inspect_project_file(self.root, '../outside')

    def test_inspect_project_file_lists_directory_entries(self):
        (self.root / 'subdir').mkdir(exist_ok=True)
        (self.root / 'subdir' / 'a.py').write_text('a = 1')
        (self.root / 'subdir' / 'b.py').write_text('b = 2')
        result = planner.inspect_project_file(self.root, 'subdir')
        self.assertTrue(result['is_directory'])
        self.assertEqual(result['entries'], ['a.py', 'b.py'])
        self.assertEqual(result['total_entries'], 2)
        self.assertIn('Select a specific file path', result['guidance'])

    def test_inspect_project_file_normalizes_drive_letters_and_diff_prefixes(self):
        (self.root / 'module.py').write_text('def hello(): pass\n')
        result1 = planner.inspect_project_file(self.root, 'A:/module.py')
        self.assertEqual(result1['path'], 'module.py')
        self.assertIn('def hello', result1['contents'])
        result2 = planner.inspect_project_file(self.root, 'a/module.py')
        self.assertEqual(result2['path'], 'module.py')
        self.assertIn('def hello', result2['contents'])
        (self.root / 'subdir').mkdir(exist_ok=True)
        (self.root / 'subdir' / 'nested.py').write_text('def nested(): pass\n')
        result3 = planner.inspect_project_file(self.root, 'nested.py')
        self.assertEqual(result3['path'], 'subdir/nested.py')
        self.assertIn('def nested', result3['contents'])

    def test_cancellation_never_creates_or_authorizes_work(self):
        captured = planner.capture_inputs(self.root, 'Work')
        self.runtime.stop.set()
        with self.assertRaises(InterruptedError): planner.plan(self.engine([]), self.runtime, captured)
        self.assertFalse(self.requests)
        self.runtime.stop.clear()
        def request(*args, **kwargs):
            self.runtime.stop.set()
            return self.reply()
        with self.assertRaises(InterruptedError): planner.plan(SimpleNamespace(request=request, effective_role_mapping=lambda p: {'mapping': {'planner': 'p', 'worker': 'w', 'reviewer': 'r'}, 'error': None}), self.runtime, captured)


    def test_auto_healing_missing_limits_and_final_checks(self):
        # 1. Model omits limits and final_checks
        bare_plan = {
            'items': [{
                'id': 'one', 'title': 'Add reader', 'instructions': 'Implement reader',
                'dependencies': [], 'acceptance_criteria': ['Reader parses a row'],
                'required_checks': [shlex.join([sys.executable, '-m', 'unittest'])]
            }]
        }
        reply1 = {'tool_calls': [{'id': 'call1', 'function': {'name': 'propose_branch_plan', 'arguments': json.dumps({'status': 'plan', 'plan': bare_plan})}}]}
        captured = planner.capture_inputs(self.root, 'Work')
        output1 = planner.plan(self.engine([reply1]), self.runtime, captured)
        self.assertEqual(output1['limits'], self.limits)
        self.assertEqual(output1['final_checks'], [shlex.join([sys.executable, '-m', 'unittest'])])

        # 2. Model outputs items at root instead of nested under plan
        root_items = {
            'status': 'plan',
            'items': [{
                'id': 'one', 'title': 'Add reader', 'instructions': 'Implement reader',
                'dependencies': [], 'acceptance_criteria': ['Reader parses a row'],
                'required_checks': [shlex.join([sys.executable, '-m', 'unittest'])]
            }]
        }
        reply2 = {'tool_calls': [{'id': 'call2', 'function': {'name': 'propose_branch_plan', 'arguments': json.dumps(root_items)}}]}
        output2 = planner.plan(self.engine([reply2]), self.runtime, captured)
        self.assertEqual(output2['items'][0]['title'], 'Add reader')
        self.assertEqual(output2['limits'], self.limits)


if __name__ == '__main__': unittest.main()


class FinalCheckParserTests(unittest.TestCase):
    def test_derivation_preserves_all_unique_checks_or_requires_repair(self):
        limits = {'dollars': 0, 'working_seconds': 900, 'requests': 30}
        items = [{'id': 'item'+str(i), 'title': 'Item', 'instructions': 'Implement',
                  'acceptance_criteria': ['Works'], 'required_checks': ['python3 -m unittest test_'+str(i)]}
                 for i in range(13)]
        def parse(candidate):
            message = {'tool_calls': [{'function': {'name': 'propose_branch_plan', 'arguments': json.dumps(
                {'status': 'plan', 'clarification': '', 'plan': {'items': candidate, 'limits': limits}})}}]}
            return planner._parse(message, limits)
        with self.assertRaisesRegex(ValueError, 'consolidated final integration'):
            parse(items)
        items[-1]['required_checks'] = items[0]['required_checks']
        result = parse(items)
        self.assertEqual(len(result['final_checks']), 12)
        self.assertEqual(result['final_checks'], [i['required_checks'][0] for i in items[:12]])

    def test_parse_filters_plan_preview_when_real_checks_exist(self):
        limits = {'dollars': 0, 'working_seconds': 900, 'requests': 30}
        items = [{'id': 'item1', 'title': 'Item', 'instructions': 'Implement',
                  'acceptance_criteria': ['Works'],
                  'required_checks': ['python3 -m unittest test_1', 'python3 -B scripts/check.py --plan']}]
        message = {'tool_calls': [{'function': {'name': 'propose_branch_plan', 'arguments': json.dumps(
            {'status': 'plan', 'clarification': '', 'plan': {'items': items, 'limits': limits,
             'final_checks': ['python3 -m unittest test_1', 'scripts/check.py --plan']}})}}]}
        result = planner._parse(message, limits)
        self.assertEqual(result['items'][0]['required_checks'], ['python3 -m unittest test_1'])
        self.assertEqual(result['final_checks'], ['python3 -m unittest test_1'])

    def test_parse_normalizes_flexible_items_and_aliases(self):
        limits = {'dollars': 0, 'working_seconds': 900, 'requests': 30}
        raw_items = [
            {
                'id': 1,
                'description': 'Inspect and patch the service configuration',
                'depends_on': [],
            },
            {
                'id': 'step-2',
                'title': 'Verify service',
                'instructions': 'Run validation tests',
                'depends_on': [1],
                'acceptance_criteria': ['Tests pass'],
                'required_checks': ['python3 -m unittest test_1'],
            }
        ]
        message = {'tool_calls': [{'function': {'name': 'propose_branch_plan', 'arguments': json.dumps(
            {'status': 'plan', 'clarification': '', 'plan': {
                'items': raw_items,
                'final_checks': ['python3 -m unittest test_1'],
            }})}}]}
        result = planner._parse(message, limits)
        self.assertEqual(result['items'][0]['id'], '1')
        self.assertEqual(result['items'][0]['instructions'], 'Inspect and patch the service configuration')
        self.assertEqual(result['items'][0]['dependencies'], [])
        self.assertEqual(result['items'][0]['title'], 'Inspect and patch the service configuration')
        self.assertTrue(len(result['items'][0]['acceptance_criteria']) > 0)
        self.assertEqual(result['items'][0]['required_checks'], ['python3 -m unittest test_1'])
        self.assertNotIn('description', result['items'][0])
        self.assertNotIn('depends_on', result['items'][0])
        self.assertEqual(result['items'][1]['id'], 'step-2')
        self.assertEqual(result['items'][1]['dependencies'], ['1'])
        self.assertEqual(result['items'][1]['required_checks'], ['python3 -m unittest test_1'])

        # Also test plan supplied as a serialized JSON string
        str_message = {'tool_calls': [{'function': {'name': 'propose_branch_plan', 'arguments': json.dumps(
            {'status': 'plan', 'clarification': '', 'plan': json.dumps({
                'items': raw_items,
                'final_checks': ['python3 -m unittest test_1'],
            })})}}]}
        str_result = planner._parse(str_message, limits)
        self.assertEqual(str_result['items'][0]['id'], '1')
        self.assertEqual(str_result['items'][1]['id'], 'step-2')


class PlannerExcerptTests(unittest.TestCase):
    """Small file/provider fixtures; no Git workflow, server, or live inference."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.limits = {'dollars': 0, 'working_seconds': 900, 'requests': 30}
        self.runtime = SimpleNamespace(task={'planning_limits': self.limits}, stop=threading.Event(), guard=lambda: None)

    def call(self, name, arguments):
        return {'tool_calls': [{'id': 'call', 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}

    def run_plan(self, responses):
        captured = {'version': 1, 'source': str(self.root), 'prompt': 'Add a restart button', 'document': None}
        captured['hash'] = planner._digest(captured)
        self.requests, self.events = [], []

        def request(runtime, messages, tools, role, purpose):
            self.assertEqual((role, purpose), ('planner', 'branch_planning'))
            self.requests.append(copy.deepcopy(messages))
            return responses.pop(0)

        engine = SimpleNamespace(
            request=request, 
            event=lambda *args: self.events.append(args),
            effective_role_mapping=lambda project: {'mapping': {'planner': 'p', 'worker': 'w', 'reviewer': 'r'}, 'error': None}
        )
        with patch.object(planner, 'project_context', return_value={'files': ['app.js']}):
            return planner.plan(engine, self.runtime, captured)

    def test_large_source_query_reads_relevant_context_without_enlarging_spec_limit(self):
        text = '/* padding */\n' * 5500 + '.restart-button { color: green; }\n' + '/* end */\n' * 2000
        data = text.encode('utf-8')
        (self.root / 'styles.css').write_bytes(data)
        result = planner.inspect_project_file(self.root, 'styles.css', query='.restart-button')
        self.assertGreater(len(data), planner.MAX_DOCUMENT_BYTES)
        self.assertEqual(result['source_bytes'], len(data))
        self.assertEqual(result['hash'], hashlib.sha256(data).hexdigest())
        self.assertTrue(result['found'])
        self.assertEqual(result['match_line'], 5501)
        self.assertIn('.restart-button { color: green; }', result['contents'])
        self.assertLessEqual(len(result['contents']), 12000)
        self.assertTrue(result['truncated'])
        self.assertTrue(result['has_more'])
        with patch.object(planner.Workspace, 'project_root', return_value=self.root):
            with self.assertRaises(ValueError):
                planner.capture_inputs(self.root, document='styles.css')

    def test_excerpts_resume_exactly_across_long_lines_crlf_and_unicode(self):
        for text in ('x' * 11999 + '\r\n' + 'é' * 13000, 'line\r\n' * 450, 'x' * 25000):
            with self.subTest(length=len(text)):
                (self.root / 'app.js').write_bytes(text.encode('utf-8'))
                position, chunks = {}, []
                for _ in range(10):
                    result = planner.inspect_project_file(self.root, 'app.js', **position)
                    self.assertLessEqual(len(result['contents']), 12000)
                    chunks.append(result['contents'])
                    if not result['has_more']:
                        break
                    self.assertTrue(result['contents'])
                    position = {'start_line': result['next_start_line'], 'start_column': result['next_start_column']}
                else:
                    self.fail('Continuation did not reach the end of the file')
                self.assertEqual(''.join(chunks), text)

    def test_ranges_and_queries_are_bounded_and_missing_match_is_explicit(self):
        (self.root / 'app.js').write_text('one\ntwo target\nthree\nfour target\n')
        result = planner.inspect_project_file(self.root, 'app.js', start_line=2, end_line=2, query='target')
        self.assertEqual(result['contents'], 'two target\n')
        self.assertEqual(result['match_line'], 2)
        self.assertEqual(result['next_start_line'], 3)
        missing = planner.inspect_project_file(self.root, 'app.js', end_line=1, query='target')
        self.assertFalse(missing['found'])
        self.assertEqual(missing['contents'], '')
        for arguments in ({'start_line': True}, {'start_line': 0}, {'start_line': 5}, {'start_column': 100},
                          {'start_line': 3, 'end_line': 2}, {'query': ''}, {'query': 'a' * 201}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                planner.inspect_project_file(self.root, 'app.js', **arguments)

    def test_source_security_and_workspace_byte_ceiling_remain_effective(self):
        (self.root / 'normal.js').write_text('source')
        (self.root / '.env').write_text('private')
        (self.root / 'link').symlink_to('normal.js')
        (self.root / 'nested-link').symlink_to(self.root, target_is_directory=True)
        (self.root / 'too-big').write_bytes(b'x' * (planner.MAX_FILE_BYTES + 1))
        (self.root / 'binary').write_bytes(b'a\0b')
        (self.root / 'badutf').write_bytes(b'\xff')
        for path in ('.env', 'link', 'nested-link/normal.js', 'too-big', 'binary', 'badutf', '../outside', str(self.root / 'normal.js')):
            with self.subTest(path=path), self.assertRaises(ValueError):
                planner.inspect_project_file(self.root, path, query='source')

    def test_large_source_inspection_and_plain_text_repair_lead_to_a_valid_proposal(self):
        (self.root / 'app.js').write_text('/* padding */\n' * 6000 + 'function restartServer() {}')
        check = shlex.join([sys.executable, '-m', 'unittest'])
        proposal = {'items': [{'id': 'restart', 'title': 'Restart button', 'instructions': 'Reuse restartServer',
                              'acceptance_criteria': ['Button restarts the server'], 'required_checks': [check]}],
                    'limits': self.limits, 'final_checks': [check]}
        prose = {'content': 'I need the restartServer handler before proposing a plan.', 'finish_reason': 'stop'}
        original = copy.deepcopy(prose)
        result = self.run_plan([prose, self.call('inspect_project_file', {'path': 'app.js', 'query': 'restartServer'}),
                                self.call('propose_branch_plan', {'status': 'plan', 'plan': proposal, 'clarification': ''})])
        self.assertEqual(result['items'][0]['id'], 'restart')
        self.assertEqual(result['limits'], self.limits)
        self.assertEqual(len(self.requests), 3)
        self.assertEqual(self.requests[1][-2], {'role': 'assistant', 'content': prose['content']})
        self.assertIn('plain text instead of', self.requests[1][-1]['content'])
        excerpt = json.loads(self.requests[2][-1]['content'])
        self.assertTrue(excerpt['found'])
        self.assertIn('function restartServer()', excerpt['contents'])
        self.assertNotIn('error', excerpt)
        self.assertEqual([e[1] for e in self.events], ['planning_repair', 'planning_inspection'])
        inspection = self.events[-1][3]
        self.assertEqual(inspection['path'], 'app.js')
        self.assertEqual(inspection['inspection'], 1)
        self.assertNotIn('contents', inspection)
        self.assertEqual(prose, original)

    def test_parallel_discovery_executes_all_reads(self):
        (self.root / 'a.js').write_text('const a = 1;\n')
        (self.root / 'b.js').write_text('const b = 2;\n')
        check = shlex.join([sys.executable, '-m', 'unittest'])
        proposal = {'items': [{'id': 'init', 'title': 'Init', 'instructions': 'Do work',
                              'acceptance_criteria': ['Done'], 'required_checks': [check]}],
                    'limits': self.limits, 'final_checks': [check]}
        multi_inspect = {
            'tool_calls': [
                {'id': 'c1', 'function': {'name': 'inspect_project_file', 'arguments': json.dumps({'path': 'a.js'})}},
                {'id': 'c2', 'function': {'name': 'inspect_project_file', 'arguments': json.dumps({'path': 'b.js'})}},
            ]
        }
        result = self.run_plan([multi_inspect, self.call('propose_branch_plan', {'status': 'plan', 'plan': proposal, 'clarification': ''})])
        self.assertEqual(result['items'][0]['id'], 'init')
        self.assertEqual(len(self.requests), 2)
        # Verify both tool results were delivered in the prompt
        tool_replies = [m for m in self.requests[1] if m.get('role') == 'tool']
        self.assertEqual(len(tool_replies), 2)
        self.assertIn('const a = 1;', tool_replies[0]['content'])
        self.assertIn('const b = 2;', tool_replies[1]['content'])

    def test_response_diagnostics_distinguish_missing_multiple_and_truncated_calls(self):
        from cheapos.branch_pause import PauseError, public
        tool = self.call('propose_branch_plan', {})['tool_calls'][0]
        cases = [({'content': 'Please paste the CSS. PRIVATE_MARKER'}, 'plain text instead of'),
                 ({'tool_calls': None}, 'neither a proposal'),
                 ({'tool_calls': [tool, tool]}, 'multiple tool calls'),
                 ({'tool_calls': [tool], 'finish_reason': 'length'}, 'output limit')]
        for response, reason in cases:
            with self.subTest(reason=reason):
                self.runtime.task.pop('planning_strategy', None)
                with self.assertRaises(PauseError) as caught:
                    self.run_plan([response] * 6)
                self.assertEqual(len(self.requests), 6)
                self.assertEqual(len(self.events), 6)
                self.assertIn(reason, str(caught.exception))
                self.assertIn('after two repairs', str(caught.exception))
                banner = public({'version': 1, 'cause': 'malformed_output', 'stage': 'planning',
                                 'diagnostic': caught.exception.safe_diagnostic})
                self.assertIn(reason, banner['explanation'])
                self.assertNotIn('PRIVATE_MARKER', banner['explanation'])

    def test_repair_context_is_bounded_and_truncated_inspection_does_not_run(self):
        clarification = self.call('propose_branch_plan', {'status': 'clarification', 'plan': None,
                                                        'clarification': 'Restart the app or the model gateway?'})
        with self.assertRaises(planner.ClarificationRequired):
            self.run_plan([{'content': 'x' * 20000}, clarification])
        self.assertEqual(len(self.requests[1][-2]['content']), 12000)
        truncated = self.call('inspect_project_file', {'path': 'app.js'})
        truncated['finish_reason'] = 'length'
        with patch.object(planner, 'inspect_project_file') as inspect:
            with self.assertRaises(planner.ClarificationRequired):
                self.run_plan([truncated, clarification])
            inspect.assert_not_called()
        self.assertIn('output limit', self.requests[1][-1]['content'])
