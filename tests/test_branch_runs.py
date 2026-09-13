import copy
import json
import unittest

from cheapos import branch_runs as runs


def plan():
    return {'items': [dict(id=str(n), title='Item %s' % n, instructions='Implement it',
                           dependencies=[str(n - 1)] if n > 1 else [],
                           acceptance_criteria=['Works'], required_checks=['python -m unittest'])
                      for n in range(1, 4)], 'limits': {'tokens': 10000, 'active_seconds': 900, 'cost': 1.5}}


def evidence():
    return dict(acceptance_satisfied=True, checks_passed=True, review_approved=True,
                candidate_id='digest', review_candidate_id='digest', worker_model='worker', reviewer_model='reviewer')


class BranchRunTests(unittest.TestCase):
    def test_factory_roundtrip_original_capture_and_no_aliasing(self):
        source = plan()
        inputs = {'document': {'path': 'tasks.md', 'contents': 'The work', 'hash': 'abc'}}
        run = runs.new_run(source, original_request='Please implement', inputs=inputs, run_id='run-1', now='now')
        self.assertEqual(json.loads(json.dumps(run)), run)
        source['items'][0]['title'] = 'Changed'
        inputs['document']['contents'] = 'Changed'
        self.assertEqual(run['items'][0]['title'], 'Item 1')
        self.assertEqual(run['inputs']['document']['contents'], 'The work')
        self.assertEqual(run['original_request'], 'Please implement')
        self.assertEqual(run['consumption']['tokens'], 0)
        self.assertEqual(run['plan_digest'], runs.new_run(plan())['plan_digest'])

    def test_invalid_plans(self):
        cases = []
        for value in (float('nan'), float('inf'), True, -1, '100', None, 10 ** 1000):
            p = plan(); p['limits']['tokens'] = value; cases.append(p)
        for field, value in [('id', '1'), ('dependencies', ['missing']), ('dependencies', ['3']), ('dependencies', [{}]), ('dependencies', [[]]),
                             ('acceptance_criteria', []), ('title', 'x' * 121), ('instructions', 'x' * 4001),
                             ('status', 'committed')]:
            p = plan(); p['items'][1][field] = value; cases.append(p)
        p = plan(); p['items'] = []; cases.append(p)
        p = plan(); p['items'] *= 17; cases.append(p)
        p = plan(); p['items'][0]['required_checks'] = [{'timeout': float('inf')}]; cases.append(p)
        p = plan(); p['items'][0]['acceptance_criteria'] = ['x' * 501]; cases.append(p)
        p = plan(); p['items'][0]['dependencies'] = ['2']; cases.append(p)
        for p in cases:
            with self.subTest(plan=p), self.assertRaises(ValueError):
                runs.validate_plan(p)

    def test_aggregate_overflow_rejects_all(self):
        p = plan()
        p['items'] = [dict(p['items'][0], id=str(n), instructions='x' * 4000) for n in range(40)]
        with self.assertRaisesRegex(ValueError, 'aggregate'):
            runs.validate_plan(p)

    def test_unknown_version_preserved_and_cannot_transition(self):
        run = runs.new_run(plan()); run['schema_version'] = 999
        before = copy.deepcopy(run)
        self.assertFalse(runs.compatibility(run)['supported'])
        with self.assertRaisesRegex(ValueError, 'unsupported schema'):
            runs.transition(run, 'running')
        self.assertEqual(before, run)
        self.assertFalse(runs.summary(run)['compatible'])
        run['schema_version'] = True
        self.assertFalse(runs.compatibility(run)['supported'])

    def test_events_idempotent_and_deterministic_after_roundtrip(self):
        run = runs.new_run(plan(), run_id='r')
        first = runs.append_event(run, 'prepared', event_key='operation-1')
        restored = json.loads(json.dumps(run))
        self.assertEqual(first, runs.append_event(restored, 'prepared', event_key='operation-1'))
        second = runs.append_event(restored, 'completed')
        self.assertEqual(second['id'], 'r:2')
        self.assertEqual(len(restored['events']), 2)

    def test_completion_cannot_bypass_gate(self):
        run = runs.new_run(plan())
        with self.assertRaises(ValueError): runs.transition_item(run, '1', 'committed')
        runs.transition_item(run, '1', 'working')
        with self.assertRaises(ValueError): runs.transition_item(run, '2', 'working')
        runs.transition_item(run, '1', 'checking')
        runs.transition_item(run, '1', 'reviewing')
        for changes in ({'checks_passed': False}, {'review_candidate_id': 'stale'}, {'reviewer_model': 'worker'}, {'acceptance_satisfied': False}):
            bad = dict(evidence(), **changes)
            with self.assertRaises(ValueError): runs.transition_item(run, '1', 'committing', bad)
        runs.transition_item(run, '1', 'committing', evidence())
        with self.assertRaises(ValueError): runs.transition_item(run, '1', 'committed')
        run['items'][0]['commit_receipt'] = {'sha': 'source-sha'}
        runs.transition_item(run, '1', 'committed')
        runs.transition_item(run, '2', 'working')

    def test_full_lifecycle_no_change_and_final_gates(self):
        run = runs.new_run(plan())
        runs.transition(run, 'awaiting_authorization')
        with self.assertRaises(ValueError): runs.transition(run, 'running')
        run['authorization_ref'] = 'operator-contract'
        runs.transition(run, 'running')
        with self.assertRaises(ValueError): runs.transition(run, 'paused')
        runs.transition(run, 'paused', reason='command_grant')
        runs.transition(run, 'running')
        with self.assertRaises(ValueError): runs.transition(run, 'finalizing')
        for item in run['items']:
            for status in ('working', 'checking', 'reviewing'):
                runs.transition_item(run, item['id'], status)
            with self.assertRaises(ValueError): runs.transition_item(run, item['id'], 'satisfied_without_change', evidence())
            runs.transition_item(run, item['id'], 'satisfied_without_change', dict(evidence(), no_change=True))
        runs.transition(run, 'finalizing')
        with self.assertRaises(ValueError): runs.transition(run, 'ready_for_merge')
        run['final_evidence'] = evidence()
        runs.transition(run, 'ready_for_merge')
        with self.assertRaises(ValueError): runs.transition(run, 'merging')
        run['merge_authorization_ref'] = 'human-merge'
        runs.transition(run, 'merging')
        with self.assertRaises(ValueError): runs.transition(run, 'merged')
        run['merge_receipt'] = {'sha': 'merged-sha'}
        runs.transition(run, 'merged')
        self.assertEqual(runs.summary(run)['completed_count'], 3)

    def test_summary_allowlist_never_leaks_authority_or_input(self):
        run = runs.new_run(plan(), original_request='SECRET', inputs={'token': 'SECRET'})
        run['authorization_ref'] = 'SECRET'
        run['pending_operations'] = [{'token': 'SECRET'}]
        run['events'] = [{'detail': 'SECRET'}]
        self.assertNotIn('SECRET', json.dumps(runs.summary(run)))
        self.assertLess(len(json.dumps(runs.summary(run))), 2000)

    def test_restart_pauses_once_without_renewing_consumption(self):
        run = runs.new_run(plan())
        run['status'] = 'running'
        run['consumption']['tokens'] = 50
        runs.recover_restart(run)
        self.assertEqual(run['pause_reason'], 'restart')
        self.assertEqual(runs.task_status(run), 'paused')
        self.assertEqual(run['consumption']['tokens'], 50)
        runs.recover_restart(run)
        self.assertEqual(len(run['events']), 1)
        self.assertEqual(runs.summary(run), runs.summary(runs.summary(run)))
        run['schema_version'] = 99
        before = copy.deepcopy(run)
        runs.recover_restart(run)
        self.assertEqual(before, run)
        self.assertEqual(runs.task_status(run), 'interrupted')

    def test_all_states_serializable(self):
        run = runs.new_run(plan())
        for state in runs.RUN_STATES:
            run['status'] = state
            for item_state in runs.ITEM_STATES:
                run['items'][0]['status'] = item_state
                self.assertEqual(json.loads(json.dumps(run)), run)


if __name__ == '__main__':
    unittest.main()
