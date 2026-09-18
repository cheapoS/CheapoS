"""Exact long-run evidence tracking; no Git, models, subprocesses or waits."""
import copy
import json
import unittest

from cheapos import progress


class ProgressTrackingTests(unittest.TestCase):
    def test_more_than_1000_states_survive_restart_without_crediting_cycles(self):
        task = {'prompt': 'Finish the task', 'patch': '', 'checks': [], 'worker_turns': 1200,
                'usage': {'cost': .25}, 'limits': {'uncapped_work': True}}
        self.assertFalse(progress.observe(task))
        for index in range(1100):
            task['patch'] = 'patch ' + str(index)
            self.assertTrue(progress.observe(task), index)
        restored = json.loads(json.dumps(task))
        self.assertEqual(progress.state(restored)['revision'], 1100)
        for patch in ('', 'patch 0', 'patch 500', 'patch 1099'):
            restored['patch'] = patch
            self.assertFalse(progress.observe(restored))
        restored['patch'] = 'new real change'
        self.assertTrue(progress.observe(restored))
        self.assertEqual(progress.state(restored)['revision'], 1101)
        self.assertEqual(restored['worker_turns'], 1200)
        self.assertEqual(restored['usage'], {'cost': .25})

    def test_legacy_saturated_index_migrates_without_renewing_attempts(self):
        task = {'prompt': 'Finish', 'patch': 'already seen'}
        saved = progress.state(task)
        saved.update(seen=[progress.digest(item) for item in progress.candidates(task)] +
                          [progress.digest(['older', n]) for n in range(1000)],
                     revision=1000, handoffs=9, malformed_attempts=3, answer_attempts=2)
        prior = copy.deepcopy(saved)
        self.assertFalse(progress.observe(task))
        self.assertEqual(set(saved['seen']), set(prior['seen']))
        for key in ('revision', 'handoffs', 'malformed_attempts', 'answer_attempts'):
            self.assertEqual(saved[key], prior[key])
        task['checks'] = [{'digest': 'candidate', 'command': ['focused-check'], 'passed': True,
                           'verification_identity': 'same inputs', 'output': 'OK in 1s'}]
        self.assertTrue(progress.observe(task))
        task['checks'][-1]['output'] = 'OK in 2s'
        self.assertFalse(progress.observe(task))

    def test_large_source_exploration_keeps_union_and_version_evidence(self):
        task = {'prompt': 'Inspect project'}
        for index in range(1100):
            self.assertTrue(progress.inspection(task, 'file' + str(index), 'v1', [1, 2]))
        restored = json.loads(json.dumps(task))
        self.assertFalse(progress.inspection(restored, 'file0', 'v1', [1, 2]))
        self.assertTrue(progress.inspection(restored, 'file0', 'v1', [2, 3]))
        self.assertTrue(progress.inspection(restored, 'file0', 'v2', [1, 2]))
        self.assertEqual(progress.state(restored)['revision'], 1102)
        self.assertEqual(progress.state(restored)['inspected'][progress.digest(['file0', 'v1'])], [1, 2, 3])

    def test_documentation_edits_remain_progress(self):
        task = {'prompt': 'Improve comments and README', 'patch': ''}
        progress.state(task)
        task['patch'] = '+# Explain the timeout\n'
        self.assertTrue(progress.observe(task))
        task['patch'] += '+README: usage instructions\n'
        self.assertTrue(progress.observe(task))
