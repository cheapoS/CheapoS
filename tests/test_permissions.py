"""Session approvals reuse exact commands without widening their scope."""
import shlex
import sys
import threading
from unittest.mock import Mock

from cheapos.engine import Engine
from test_engine import LocalCase, call, wait_for


COMMAND = shlex.join([sys.executable, '-m', 'unittest', 'test_math_utils.ClampTests.test_above'])
OTHER = shlex.join([sys.executable, '-m', 'unittest', 'test_math_utils.ClampTests.test_inside'])


class SessionPermissionTests(LocalCase):
    def task(self):
        task = self.fixture(paid=True)
        task.update(conversational=True, auto_approve_checks=False)
        self.engine.store.save(task)
        return task

    def replies(self, messages):
        queue = iter(messages)
        provider = Mock()
        provider.complete.side_effect = lambda *args: (next(queue), {'prompt_tokens': 10, 'completion_tokens': 5, 'cost': 0})
        self.engine.provider_factory = lambda *args: provider

    def waiting(self, task, checks=0):
        wait_for(lambda: self.engine.store.get(task['id'])['status'] == 'waiting_approval' and len(self.engine.store.get(task['id'])['checks']) == checks)
        return self.engine.store.get(task['id'])['pending_approval']['id']

    def remember(self, task):
        request_id = self.waiting(task)
        self.engine.approve_check(task['id'], True, remember=True, approval_id=request_id)

    def grant_and_finish(self, task):
        self.replies([call('run_checks', {'command': COMMAND}), {'content': 'Checks finished.'}])
        self.engine.start(task['id'])
        self.remember(task)
        self.assertEqual(self.finish(task)['status'], 'awaiting_reply')

    def test_checkpoint_reuses_checks_and_session_permission_covers_explicit_followup(self):
        task = self.task()
        self.replies([call('run_checks', {'command': COMMAND}), call('checkpoint', {'summary': 'Verified the existing upper-bound test.'}), call('review_decision', {'decision': 'APPROVE', 'feedback': 'Checks pass.'})])
        self.engine.start(task['id']); self.remember(task)
        result = self.finish(task)
        self.assertEqual(result['status'], 'approved', result['error'])
        self.assertEqual(len(result['checks']), 1)
        self.assertEqual(sum(e['title'] == 'Permission needed to run the verification command' for e in result['events']), 1)
        self.assertFalse(result['auto_approve_checks'])
        self.replies([call('run_checks', {'command': COMMAND}), {'content': 'Checked again.'}])
        self.engine.start(task['id'], {'message': 'Run the same check again.'})
        result = self.finish(task)
        self.assertEqual(result['status'], 'awaiting_reply')
        self.assertEqual(len(result['checks']), 2)
        self.assertEqual(self.engine.session_permissions(task['id'])['commands'], [shlex.split(COMMAND)])

    def test_changed_arguments_and_another_chat_still_ask(self):
        task = self.task(); self.grant_and_finish(task)
        self.replies([call('run_checks', {'command': OTHER})])
        self.engine.start(task['id'], {'message': 'Run a different test.'})
        request_id = self.waiting(task, checks=1)
        self.engine.approve_check(task['id'], False, approval_id=request_id)
        self.assertEqual(len(self.finish(task)['checks']), 1)
        # A different chat of the same source repository cannot inherit the grant.
        self.engine.save_preferences({'execution': {'mode': 'manual'}})
        self.engine.configure({role: {'base_url': 'http://127.0.0.1:11434/v1', 'model': 'fixture-'+role, 'input_rate': 0, 'output_rate': 0} for role in ['worker', 'reviewer']})
        other = self.engine.create({'repository': task['source'], 'prompt': 'Check again', 'conversational': True})
        self.replies([call('run_checks', {'command': COMMAND})])
        self.engine.start(other['id']); self.waiting(other)
        self.engine.approve_check(other['id'], False)
        self.assertEqual(self.finish(other)['checks'], [])
        self.assertEqual(self.engine.session_permissions(other['id'])['commands'], [])

    def test_once_asks_again_and_stale_approval_cannot_grant_permission(self):
        task = self.task()
        self.replies([call('run_checks', {'command': COMMAND})] * 2)
        self.engine.start(task['id']); first_id = self.waiting(task)
        with self.assertRaises(ValueError):
            self.engine.approve_check(task['id'], True, remember=True)
        self.engine.approve_check(task['id'], True, approval_id=first_id)
        second_id = self.waiting(task, checks=1)
        self.assertNotEqual(first_id, second_id)
        with self.assertRaises(ValueError):
            self.engine.approve_check(task['id'], True, remember=True, approval_id=first_id)
        with self.assertRaises(ValueError):
            self.engine.approve_check(task['id'], False, remember=True, approval_id=second_id)
        self.assertEqual(self.engine.session_permissions(task['id'])['commands'], [])
        self.engine.approve_check(task['id'], False, approval_id=second_id)
        self.assertEqual(len(self.finish(task)['checks']), 1)

    def test_clearing_session_permissions_makes_next_run_ask(self):
        task = self.task(); self.grant_and_finish(task)
        self.assertEqual(self.engine.clear_session_permissions(task['id'])['commands'], [])
        self.replies([call('run_checks', {'command': COMMAND})])
        self.engine.start(task['id'], {'message': 'Check again.'}); self.waiting(task, checks=1)
        self.engine.approve_check(task['id'], False)
        self.assertEqual(len(self.finish(task)['checks']), 1)

    def test_server_restart_expires_grants_even_with_saved_approval_events(self):
        task = self.task(); self.grant_and_finish(task)
        self.engine.shutdown()
        self.engine = Engine(self.engine.store.root)
        self.assertEqual(self.engine.session_permissions(task['id'])['commands'], [])
        self.replies([call('run_checks', {'command': COMMAND})])
        self.engine.start(task['id'], {'message': 'Check again.'}); self.waiting(task, checks=1)
        self.engine.approve_check(task['id'], False)
        self.assertEqual(len(self.finish(task)['checks']), 1)

    def test_changed_workspace_cannot_reuse_the_same_chat_permission(self):
        task = self.task(); self.grant_and_finish(task)
        current = self.engine.store.get(task['id'])
        current['workspace'] = self.fixture()['workspace']
        self.engine.store.save(current)
        self.assertEqual(self.engine.session_permissions(task['id'])['commands'], [])
        self.replies([call('run_checks', {'command': COMMAND})])
        self.engine.start(task['id'], {'message': 'Check again.'}); self.waiting(task, checks=1)
        self.engine.approve_check(task['id'], False)
        self.assertEqual(len(self.finish(task)['checks']), 1)


    def test_exact_command_grant_survives_actual_pause_and_resume(self):
        task=self.task();entered=threading.Event();release=threading.Event();calls=[]
        def complete(*args):
            calls.append(1)
            if len(calls)==1:return call('run_checks',{'command':COMMAND}), {'prompt_tokens':1,'completion_tokens':1,'cost':0}
            entered.set();release.wait(5)
            return {'content':'Finished.'},{'prompt_tokens':1,'completion_tokens':1,'cost':0}
        provider=Mock();provider.complete.side_effect=complete
        self.engine.provider_factory=lambda *args:provider
        self.engine.start(task['id']);self.remember(task)
        self.assertTrue(entered.wait(5));self.engine.stop(task['id']);release.set()
        self.assertEqual(self.finish(task)['status'],'paused')
        self.replies([call('run_checks',{'command':COMMAND}),{'content':'Checked again.'}])
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(len(result['checks']),2)
        self.assertEqual(sum(e['title']=='Permission needed to run the verification command' for e in result['events']),1)
        self.assertTrue(any(e['title']=='Running tests · allowed for this session' for e in result['events']))
