import copy
import unittest
from cheapos import unattended_items as items


class IndependentItemsTests(unittest.TestCase):
    def run_record(self):
        return {'schema_version': 1, 'id': 'run', 'plan': {'continue_independent': True},
                'items': [{'id': name, 'status': 'pending', 'dependencies': deps, 'evidence': {}}
                          for name, deps in [('a', []), ('b', ['a']), ('c', [])]],
                'pending_operations': [], 'events': [], 'event_sequence': 0, 'waiting_for_user': 'Question'}

    def test_clean_blocker_defers_only_authorized_independent_work(self):
        run = self.run_record()
        run['items'][0]['status'] = 'working'
        self.assertTrue(items.defer(run, run['items'][0], 'Choose behavior', True))
        self.assertEqual(run['items'][0]['status'], 'blocked')
        self.assertEqual(run['items'][0]['question'], 'Choose behavior')
        self.assertNotIn('waiting_for_user', run)
        self.assertEqual(items.next_item(run)['id'], 'c')
        run['items'][2]['status'] = 'committed'
        self.assertIsNone(items.next_item(run))
        run['items'][0].pop('question')
        self.assertEqual(items.next_item(run)['id'], 'a')
        run['items'][0]['status'] = 'committed'
        self.assertEqual(items.next_item(run)['id'], 'b')

    def test_nondeferrable_cases_preserve_entire_record(self):
        for mode in ('legacy', 'dirty', 'pending', 'dependent_only'):
            run = self.run_record()
            clean = True
            if mode == 'legacy': run['plan'].pop('continue_independent')
            if mode == 'dirty': clean = False
            if mode == 'pending': run['pending_operations'] = [{'id': 'pending'}]
            if mode == 'dependent_only': run['items'].pop()
            before = copy.deepcopy(run)
            self.assertFalse(items.defer(run, run['items'][0], 'Question', clean))
            self.assertEqual(run, before)
        run = self.run_record()
        run['items'][2]['status'] = 'reviewing'
        self.assertEqual(items.next_item(run)['id'], 'c')
        run['plan'].clear()
        self.assertEqual(items.next_item(run)['id'], 'a')

    def test_actual_completion_order_requires_exact_unique_dependency_safe_receipts(self):
        run = self.run_record()
        for item in run['items']:
            item['status'] = 'committed'
            item['commit_receipt'] = {'stage': 'completed', 'run_id': 'run', 'item_id': item['id']}
        run['completed_operations'] = [copy.deepcopy(run['items'][n]['commit_receipt']) for n in (2, 0, 1)]
        self.assertEqual([i['id'] for i in items.completion_order(run)], ['c', 'a', 'b'])
        for mode in ('duplicate', 'missing', 'wrong_run', 'receipt_changed', 'dependency'):
            bad = copy.deepcopy(run)
            ops = bad['completed_operations']
            if mode == 'duplicate': ops[1] = copy.deepcopy(ops[0])
            if mode == 'missing': ops.pop()
            if mode == 'wrong_run': ops[0]['run_id'] = 'other'
            if mode == 'receipt_changed': ops[0]['tree'] = 'altered'
            if mode == 'dependency': ops[1], ops[2] = ops[2], ops[1]
            with self.subTest(mode=mode), self.assertRaises(ValueError): items.completion_order(bad)
        run['plan'].clear()
        self.assertEqual([i['id'] for i in items.completion_order(run)], ['a', 'b', 'c'])
