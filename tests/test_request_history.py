"""Pure history-projection cases; no network, Git fixtures or waits."""
import copy
import json
import unittest

from cheapos.request_history import project
from cheapos.engine import Engine, ToolArgumentsError


def history(arguments, name='final_review_decision'):
    return [{'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': 'rejected', 'type': 'function', 'function': {'name': name, 'arguments': arguments}}]},
        {'role': 'tool', 'tool_call_id': 'rejected', 'content': '{"error":"Arguments rejected; call not executed"}'}]


class RequestHistoryTests(unittest.TestCase):
    def test_invalid_history_is_lossless_idempotent_and_does_not_repair_new_calls(self):
        for arguments in ('{"decision":"APPROVE"} trailing', '{', '[]', 'null',
                          '{"score":NaN}', '', None, {'path': 'example.py'}, float('inf')):
            with self.subTest(arguments=arguments):
                messages = history(arguments)
                before = copy.deepcopy(messages)
                projected = project(messages)
                call = projected[0]['tool_calls'][0]
                envelope = json.loads(call['function']['arguments'])
                self.assertEqual(envelope['_cheapos_invalid_arguments'], arguments if isinstance(arguments, str) else json.dumps(arguments))
                self.assertEqual(call['id'], 'rejected')
                self.assertEqual(call['function']['name'], 'final_review_decision')
                self.assertEqual(projected[1], messages[1])
                self.assertEqual(messages, before)
                self.assertEqual(project(projected), projected)
                self.assertEqual(project(json.loads(json.dumps(messages))), projected)
        with self.assertRaises(ToolArgumentsError):
            Engine.parse_call(history('{"decision":"APPROVE"} trailing')[0]['tool_calls'][0])

    def test_valid_calls_evidence_and_mixed_batch_pairing_are_unchanged(self):
        messages = history('{')
        good = {'id': 'read', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{"path": "example.py"}'}}
        messages[0].update(content='Retained assistant text', reasoning_details=[{'data': 'opaque'}])
        messages[0]['tool_calls'].append(good)
        messages.append({'role': 'tool', 'tool_call_id': 'read', 'content': 'Exact source evidence'})
        projected = project(messages)
        self.assertEqual(projected[0]['tool_calls'][1], good)
        for key in ('content', 'reasoning_details'):
            self.assertEqual(projected[0][key], messages[0][key])
        self.assertEqual(projected[1:], messages[1:])
        self.assertEqual(project(history('{"decision":"APPROVE"}')), history('{"decision":"APPROVE"}'))

    def test_empty_defaults_match_only_existing_read_only_tools(self):
        for name in ('list_files', 'get_diff'):
            projected = project(history('', name))
            self.assertEqual(projected[0]['tool_calls'][0]['function']['arguments'], '{}')
        self.assertIn('_cheapos_invalid_arguments', project(history('', 'run_checks'))[0]['tool_calls'][0]['function']['arguments'])
