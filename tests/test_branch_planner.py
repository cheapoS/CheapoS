import copy
import json
import sys
import shlex
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    def reply(self, plan=None):
        value = {'status': 'plan', 'plan': plan or self.valid, 'clarification': ''}
        return {'tool_calls': [{'id': 'call', 'function': {'name': 'propose_branch_plan', 'arguments': json.dumps(value)}}]}

    def engine(self, responses):
        def request(runtime, messages, tools, role, purpose):
            self.requests.append(copy.deepcopy(messages))
            self.assertEqual(role, 'worker')
            self.assertEqual(purpose, 'branch_planning')
            self.assertEqual([t['function']['name'] for t in tools], ['propose_branch_plan'])
            runtime.task['request_metrics'].append({'id': str(len(self.requests)), 'purpose': purpose})
            return responses.pop(0)
        return SimpleNamespace(request=request)

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

    def test_two_repairs_are_bounded_and_side_effect_tools_never_run(self):
        bad = {'tool_calls': [{'function': {'name': 'write_file', 'arguments': '{}'}}]}
        captured = planner.capture_inputs(self.root, 'Do work')
        with self.assertRaisesRegex(ValueError, 'after two repairs'):
            planner.plan(self.engine([bad, bad, bad]), self.runtime, captured)
        self.assertEqual(len(self.requests), 3)
        self.requests.clear()
        self.assertEqual(planner.plan(self.engine([bad, self.reply()]), self.runtime, captured), self.valid)

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
                planner.plan(self.engine([response] * 3), self.runtime, planner.capture_inputs(self.root, 'Work'))

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

    def test_cancellation_never_creates_or_authorizes_work(self):
        captured = planner.capture_inputs(self.root, 'Work')
        self.runtime.stop.set()
        with self.assertRaises(InterruptedError): planner.plan(self.engine([]), self.runtime, captured)
        self.assertFalse(self.requests)
        self.runtime.stop.clear()
        def request(*args, **kwargs):
            self.runtime.stop.set()
            return self.reply()
        with self.assertRaises(InterruptedError): planner.plan(SimpleNamespace(request=request), self.runtime, captured)


if __name__ == '__main__': unittest.main()
