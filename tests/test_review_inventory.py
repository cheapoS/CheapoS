"""Small in-memory review payloads; no Git, waits or provider calls."""
import copy
import json
import unittest

from cheapos import context_evidence
from cheapos.providers import BudgetError, reserve, reconcile


def inventory():
    return [f'tests/fixtures/project_{i:04d}/some_module.py' for i in range(900)]


def exchange():
    return [
        {'role': 'assistant', 'tool_calls': [{'id': 'listing', 'function': {'name': 'list_files', 'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': 'listing', 'content': json.dumps(inventory())},
    ]


class ReviewInventoryTests(unittest.TestCase):
    def test_large_inventory_fits_unchanged_budget_and_remains_retrievable(self):
        task = {'limits': {'output_tokens': 8192, 'reviewer_tokens': 200000, 'dollars': 0},
                'usage': {'reviewer': {'tokens': 159110, 'cost': 0}, 'cost': 0,
                          'uncertain_requests': 0, 'estimated_requests': 0}}
        config = {'input_rate': 0, 'output_rate': 0}
        messages = [{'role': 'system', 'content': 'Review every criterion.'},
                    {'role': 'user', 'content': 'Current source, checks and findings: ' + 'x' * 18000}] + exchange()
        before = copy.deepcopy(messages)
        with self.assertRaises(BudgetError):
            reserve(task, config, messages, [], 'reviewer')
        reduced = context_evidence.review_inventories(task, messages)
        self.assertEqual(messages, before)
        self.assertEqual(reduced[:3], before[:3])
        preview = json.loads(reduced[3]['content'])
        self.assertEqual(preview['file_count'], 900)
        reservation = reserve(task, config, reduced, [], 'reviewer')
        self.assertLessEqual(reservation['tokens'], 40890)
        self.assertEqual(reservation['completion_tokens'], 8192)
        restored = json.loads(json.dumps(task))
        text = ''; offset = 0
        while True:
            page = context_evidence.read(restored, preview['context_reference'], offset)
            text += page['content']; offset = page['next_offset']
            if not page['has_more']: break
        self.assertEqual(json.loads(text), inventory())
        self.assertEqual(context_evidence.review_inventories(task, reduced), reduced)
        reconcile(task, config, reservation, {'prompt_tokens': 1000, 'completion_tokens': 500})
        self.assertEqual(task['usage']['reviewer']['tokens'], 160610)
        self.assertEqual(task['limits']['reviewer_tokens'], 200000)

    def test_source_findings_errors_and_small_listings_are_not_compacted(self):
        for name, content in [('read_file', json.dumps(inventory())), ('review_decision', json.dumps(inventory())),
                              ('list_files', json.dumps(['app.py'])), ('list_files', 'invalid ' * 900),
                              ('list_files', json.dumps({'error': 'x' * 5000}))]:
            messages = exchange(); messages[0]['tool_calls'][0]['function']['name'] = name
            messages[1]['content'] = content
            task = {}
            self.assertIs(context_evidence.review_inventories(task, messages), messages)
            self.assertEqual(task, {})
