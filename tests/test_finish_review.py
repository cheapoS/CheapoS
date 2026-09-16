"""Review admission/state tests without Git, subprocesses, sockets or models."""
import copy
import hashlib
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos.engine import Engine, worker_system
from cheapos import work_policy


class FinishReviewTests(unittest.TestCase):
    def setUp(self):
        self.task = {
            'id': 'saved', 'prompt': 'Fix the bug.', 'conversational': True,
            'demo': False, 'status': 'awaiting_reply', 'active_role': 'coordinator',
            'execution': {'mode': 'delegate'}, 'providers': {}, 'events': [],
            'patch': 'saved diff', 'turn_start_patch': 'saved diff', 'changes': [{}],
            'check_command': ['python3', '-m', 'unittest'], 'checks': [],
            'worker_turns': 17, 'request_worker_turns': 17, 'iterations': 2,
            'limits': {'worker_turns': 20}, 'usage': {'cost': 0.04},
        }
        self.engine = SimpleNamespace(lock=threading.RLock(), runtimes={},
            require_active_task=Mock(), startup=Mock(), admission=Mock(),
            store=Mock(), refresh_changes=Mock(), event=Mock(),
            initial_messages=Mock(return_value=[]), _run=Mock())
        self.engine.startup.busy.return_value = False
        self.engine.store.get.return_value = self.task

    def start(self, changes=None, needs_review=True):
        with patch('cheapos.engine.needs_patch_review', return_value=needs_review), \
             patch('cheapos.engine.Runtime'), patch('cheapos.engine.threading.Thread'):
            return Engine.start(self.engine, 'saved', changes or {'finish_review': True})

    def test_known_command_queues_review_without_resetting_usage_or_authority(self):
        before = copy.deepcopy(self.task)
        result = self.start()
        self.assertEqual(result['active_role'], 'worker')
        self.assertTrue(result['finish_review'])
        self.assertIn('pending_checkpoint', result)
        for key in ('patch', 'checks', 'worker_turns', 'request_worker_turns', 'iterations', 'limits', 'usage'):
            self.assertEqual(result[key], before[key], key)
        self.assertNotIn('auto_approve_checks', result)
        self.assertNotIn('requests', result)
        self.assertNotIn('commit_pending', result)

    def test_missing_command_keeps_worker_in_verification_instead_of_orientation(self):
        self.task['check_command'] = []
        result = self.start()
        self.assertNotIn('pending_checkpoint', result)
        self.assertEqual(work_policy.stage(result), 'verification')
        self.assertIn('even if you make no new edits', worker_system(result))
        result['checks'] = [{'passed': True, 'digest': hashlib.sha256(result['patch'].encode()).hexdigest(),
                            'verification_identity': 'fixture', 'generation': 0}]
        self.assertEqual(work_policy.stage(result), 'review')
        result.pop('finish_review')
        self.assertEqual(work_policy.stage(result), 'orientation')

    def test_saved_review_is_preserved_and_double_click_does_not_dispatch_again(self):
        self.task['pending_review'] = {'messages': ['retained reviewer context']}
        self.task['pending_checkpoint'] = {'summary': 'Original candidate'}
        before = copy.deepcopy(self.task)
        self.start()
        self.assertEqual(self.task['pending_review'], before['pending_review'])
        self.assertEqual(self.task['pending_checkpoint'], before['pending_checkpoint'])
        self.engine.event.reset_mock()
        self.start()
        self.engine.event.assert_not_called()

    def test_already_reviewed_patch_needs_no_dispatch(self):
        before = copy.deepcopy(self.task)
        self.start(needs_review=False)
        self.assertEqual(self.task, before)
        self.engine.event.assert_not_called()
        self.assertFalse(self.engine.runtimes)

    def test_finish_review_cannot_override_recovery_or_command_permission(self):
        for status in ('paused', 'budget_paused', 'waiting_approval', 'takeover_requested'):
            with self.subTest(status=status):
                self.task['status'] = status
                with self.assertRaisesRegex(ValueError, 'recovery or approval control'):
                    self.start()
                self.assertFalse(self.engine.runtimes)
        self.task['status'] = 'awaiting_reply'
        self.task['environment_setup'] = {'status': 'missing'}
        with self.assertRaisesRegex(ValueError, 'Re-check the task environment'):
            self.start()

    def test_finish_review_rejects_mixed_options_and_read_only_requests(self):
        for changes in ({'finish_review': 'yes'}, {'finish_review': True, 'message': 'new scope'},
                        {'finish_review': True, 'limits': {'worker_turns': 100}}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'Finish review cannot'):
                self.start(changes)
        self.task['prompt'] = work_policy.READ_ONLY_STARTERS[0]
        with self.assertRaisesRegex(ValueError, 'read-only'):
            self.start()
