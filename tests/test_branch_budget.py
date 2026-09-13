import copy
import threading
import time
import unittest
from types import SimpleNamespace
from cheapos.branch_budget import Ledger, LimitExceeded


class BranchBudgetTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.task = {'worker_turns': 2, 'tool_actions': 3, 'request_metrics': [{'id': 'planning', 'status': 'responded'}],
                     'usage': {'cost': .2, 'worker': {'tokens': 100, 'cost': .2}, 'reviewer': {'tokens': 0, 'cost': 0}},
                     'branch_run': {'limits': {'working_seconds': 100, 'dollars': 1, 'requests': 10, 'worker_turns': 10, 'tool_actions': 20, 'reviewer_tokens': 1000}, 'consumption': {}}}
        self.runtime = SimpleNamespace(task=self.task, stop=threading.Event())
        self.saved = []
        self.ledger = Ledger(self.runtime, lambda: self.saved.append(copy.deepcopy(self.task)), clock=lambda: self.now)

    def begin(self):
        self.ledger.begin(start_watchdog=False)

    def test_planning_cost_and_all_counters_survive_item_and_resume(self):
        self.begin()
        values = self.task['branch_run']['consumption']
        self.assertEqual((values['dollars'], values['requests'], values['worker_turns'], values['tool_actions']), (.2, 1, 2, 3))
        self.task['worker_turns'] += 2
        self.task['tool_actions'] += 4
        self.task['request_metrics'] = [{'id': 'next', 'status': 'uncertain'}]
        self.task['usage']['cost'] += .3
        self.ledger.guard()
        self.now += 8
        self.ledger.end()
        resumed = Ledger(self.runtime, lambda: None, clock=lambda: self.now)
        resumed.begin(start_watchdog=False)
        self.assertEqual((values['requests'], values['worker_turns'], values['tool_actions']), (2, 4, 7))
        self.assertAlmostEqual(values['dollars'], .5)
        self.assertEqual(values['working_seconds'], 38)
        resumed.end()

    def test_live_pause_refunds_reservation_operator_wait_excluded_cooldown_counted(self):
        self.begin()
        self.assertEqual(self.task['branch_run']['consumption']['working_seconds'], 30)
        self.now += 7
        self.ledger.suspend()
        self.assertEqual(self.task['branch_run']['consumption']['working_seconds'], 7)
        self.now += 5000
        self.ledger.resume(start_watchdog=False)
        self.now += 11  # Authorized route cooldown remains active.
        self.ledger.end()
        self.assertEqual(self.task['branch_run']['consumption']['working_seconds'], 18)

    def test_crash_retains_open_reservation_not_offline_time(self):
        self.begin()
        self.now += 16
        self.ledger.guard()
        persisted = copy.deepcopy(self.saved[-1])
        self.assertEqual(persisted['branch_run']['consumption']['working_seconds'], 46)
        self.now += 10000
        runtime = SimpleNamespace(task=persisted, stop=threading.Event())
        resumed = Ledger(runtime, lambda: None, clock=lambda: self.now)
        resumed.begin(start_watchdog=False)
        self.assertEqual(persisted['branch_run']['consumption']['working_seconds'], 76)
        resumed.end()
        self.assertEqual(persisted['branch_run']['consumption']['working_seconds'], 46)

    def test_time_limit_cancellation_and_monotonic_rollback_does_not_refund(self):
        self.begin()
        self.now += 20
        self.ledger.guard()
        self.now -= 15
        self.ledger.end()
        self.assertEqual(self.task['branch_run']['consumption']['working_seconds'], 20)
        resumed = Ledger(self.runtime, lambda: None, clock=lambda: self.now)
        resumed.begin(start_watchdog=False)
        self.now += 80
        with self.assertRaises(LimitExceeded): resumed.guard()
        self.assertTrue(self.runtime.stop.is_set())
        resumed.end()
        with self.assertRaises(LimitExceeded): Ledger(self.runtime, lambda: None, clock=lambda: self.now).begin(start_watchdog=False)

    def test_requests_reserve_before_dispatch_and_history_truncation_is_not_a_refund(self):
        self.task['branch_run']['limits']['requests'] = 2
        self.begin()
        self.ledger.guard(next_request=True)
        self.task['request_metrics'] = [{'id': 'second'}]
        self.ledger.guard()
        self.task['request_metrics'] = []
        with self.assertRaises(LimitExceeded): self.ledger.guard(next_request=True)
        self.assertEqual(self.task['branch_run']['consumption']['requests'], 2)

    def test_cost_reservations_and_known_refunds_not_double_charged(self):
        self.begin()
        self.task['usage']['cost'] = .8
        self.task['usage']['uncertain_requests'] = 1
        self.ledger.guard()
        self.assertEqual(self.task['branch_run']['consumption']['dollars'], .8)
        self.task['usage']['cost'] = .5  # Existing provider reconciliation owns refunds.
        self.ledger.guard()
        self.assertAlmostEqual(self.task['branch_run']['consumption']['dollars'], .5)
        self.task['usage']['cost'] = 1.01
        with self.assertRaises(LimitExceeded): self.ledger.guard()

    def test_exact_worker_action_and_reviewer_token_caps(self):
        self.begin()
        for key, task_key, limit, next_arg in [('worker_turns', 'worker_turns', 10, 'next_worker_turn'), ('tool_actions', 'tool_actions', 20, 'next_action')]:
            self.task[task_key] = limit
            self.ledger.guard()
            with self.assertRaises(LimitExceeded): self.ledger.guard(**{next_arg: True})
        self.task['usage']['reviewer']['tokens'] = 1001
        with self.assertRaises(LimitExceeded): self.ledger.guard()

    def test_watchdog_cancels_blocked_work_without_dispatch(self):
        self.task['branch_run']['limits']['working_seconds'] = .08
        ledger = Ledger(self.runtime, lambda: None, segment_seconds=.04)
        ledger.begin()
        self.assertTrue(self.runtime.stop.wait(1))
        self.assertIsInstance(self.runtime.branch_budget_error, LimitExceeded)
        ledger.end()
        ledger.thread.join(1)
        self.assertFalse(ledger.thread.is_alive())

    def test_persist_failure_blocks_execution_and_unchanged_guard_does_not_save(self):
        self.begin()
        previous = len(self.saved)
        self.ledger.guard()
        self.assertEqual(len(self.saved), previous)
        def failed(): raise OSError('disk unavailable')
        self.ledger.persist = failed
        self.now += 16
        with self.assertRaises(OSError): self.ledger.guard()
        self.assertTrue(self.runtime.stop.is_set())


if __name__ == '__main__': unittest.main()
