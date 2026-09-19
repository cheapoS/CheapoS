"""In-memory conversation contracts plus one existing small repository fixture."""
import copy
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import discussion
from cheapos.engine import Engine, Runtime
from cheapos.providers import ProviderError


def saved_task():
    return {'id': 'chat', 'status': 'paused', 'prompt': 'Fix the bug',
            'requests': ['Fix the bug'], 'patch': 'saved patch', 'events': [],
            'providers': {'worker': {'model': 'worker'}}, 'checks': [{'passed': True, 'digest': 'candidate'}],
            'pending_review': {'candidate': 'candidate', 'attempts': [1, 2]},
            'pending_approval': {'id': 'permission'}, 'error': 'Review incomplete',
            'error_code': 'review_stall', 'limit_hit': {'key': 'worker_turns'},
            'limits': {'worker_turns': 0, 'run_minutes': 0},
            'discussion': [{'id': 'question', 'message': 'Why this approach?', 'status': 'queued'}]}


class DiscussionTests(unittest.TestCase):
    def test_opening_greeting_is_not_a_work_request_or_attachment(self):
        task = {'conversational': True, 'execution': {'mode': 'remote'},
                'prompt': 'hi there', 'requests': ['hi there']}
        self.assertTrue(discussion.opening_greeting(task))
        for message in ('hello cheapoS!', 'Hi', 'Good morning'):
            self.assertTrue(discussion.is_greeting(message))
        for message in ('hi, fix README', 'hey can you explain this?', 'hi\nrun tests', 'hi there; delete it'):
            self.assertFalse(discussion.is_greeting(message))
        for extra in ({'attachments': [{'filename': 'image.png'}]}, {'branch_run': {'id': 'run'}},
                      {'worker_turns': 1}, {'changes': ['file']}, {'execution': {'mode': 'local'}},
                      {'requests': ['hi there', 'Fix it']}, {'demo': True}):
            self.assertFalse(discussion.opening_greeting({**task, **extra}))

    def test_greeting_followup_needs_no_tools_or_work_packet(self):
        task = saved_task(); runtime = Runtime(task)
        engine = Mock()
        engine.request.return_value = {'content': 'Hello again!'}
        self.assertTrue(discussion.is_discussion('hi there'))
        self.assertEqual(discussion.answer(engine, runtime, {'id': 'hello', 'message': 'hi there'}), 'Hello again!')
        args = engine.request.call_args.args
        self.assertEqual(args[2], [])
        self.assertEqual(args[3], 'worker')
        self.assertNotIn('saved patch', json.dumps(args[1]))

    def test_discussion_does_not_classify_actual_changes_as_questions(self):
        for message in ('Why did you change that?', 'Can you show me a Python example?',
                        'What should we improve next?', 'Explain the fix', 'thanks!',
                        'How would we implement this?', 'Thoughts?'):
            self.assertTrue(discussion.is_discussion(message), message)
        for message in ('Can you fix this?', 'Please update README', 'continue',
                        'Why is this broken? Fix it.', 'Explain it and then implement it.',
                        'Why did it fail? Please patch it.',
                        'When I restart the app, this window opens. Only show it on first launch.',
                        'Show me an example, then update the file.'):
            self.assertFalse(discussion.is_discussion(message), message)

    def test_reply_preserves_work_review_permissions_and_failures_in_both_modes(self):
        for branch in (False, True):
            for status in ('running', 'reviewing', 'paused', 'approved', 'completed'):
                task = saved_task()
                task['status'] = status
                if branch:
                    task['branch_run'] = {'id': 'run', 'status': 'merged', 'readiness': {'candidate': 'candidate'}}
                runtime = Runtime(task)
                before = copy.deepcopy(task)
                engine = SimpleNamespace(lock=threading.RLock(), store=Mock())
                with patch.object(discussion, 'answer', return_value='Here is why.'):
                    discussion.drain(engine, runtime)
                self.assertEqual(task['discussion'][0]['answer'], 'Here is why.')
                self.assertEqual(task['discussion'][0]['status'], 'answered')
                for key in before.keys() - {'discussion'}:
                    self.assertEqual(task[key], before[key], key)
                self.assertFalse(runtime.answering_chat)

    def test_reply_failure_does_not_replace_actual_work_blocker(self):
        task = saved_task()
        runtime = Runtime(task)
        engine = SimpleNamespace(lock=threading.RLock(), store=Mock())
        def fail(*args):
            task.update(error='Provider failed', status='error', limit_hit={'key': 'other'})
            raise ProviderError('Provider unavailable', code='http_503')
        with patch.object(discussion, 'answer', side_effect=fail):
            discussion.drain(engine, runtime)
        self.assertEqual(task['status'], 'paused')
        self.assertEqual(task['error'], 'Review incomplete')
        self.assertEqual(task['limit_hit'], {'key': 'worker_turns'})
        self.assertEqual(task['discussion'][0]['error_code'], 'http_503')
        self.assertIn('Provider unavailable', task['discussion'][0]['answer'])

    def test_reply_uses_separate_recovery_state_and_excludes_time_only_once(self):
        for status in ('running', 'waiting_approval'):
            task = saved_task(); task['status'] = status
            runtime = Runtime(task); runtime.started = 100
            runtime.handoffs = 2; runtime.observations = {'file': 'retained'}
            engine = SimpleNamespace(lock=threading.RLock(), store=Mock())
            with patch('time.monotonic', return_value=200) as clock:
                def reply(engine, answering, turn):
                    self.assertIsNot(answering, runtime)
                    self.assertIs(answering.stop, runtime.stop)
                    self.assertEqual(answering.handoffs, 0)
                    answering.handoffs += 1
                    answering.observations.clear()
                    clock.return_value = 220
                    return 'Here is why.'
                with patch.object(discussion, 'answer', side_effect=reply):
                    discussion.drain(engine, runtime)
            self.assertEqual(runtime.handoffs, 2)
            self.assertEqual(runtime.observations, {'file': 'retained'})
            self.assertEqual(runtime.started, 100 if status == 'waiting_approval' else 120)

    def test_directions_received_during_reply_are_delivered_in_order_without_new_authority(self):
        task = saved_task(); task['discussion'] = []
        engine = Engine.__new__(Engine)
        engine.lock = threading.RLock(); engine.require_active_task = Mock()
        engine.store = Mock(); engine.store.get.side_effect = lambda _: copy.deepcopy(task)
        engine.store.save.side_effect = lambda value: task.update(copy.deepcopy(value))
        runtime = Runtime(copy.deepcopy(task)); runtime.discussion_only = True
        runtime.thread = Mock(); runtime.thread.is_alive.return_value = True
        engine.runtimes = {task['id']: runtime}
        directions = [{'message': 'Update the title'}, {'message': 'Then add a short example'}]
        for values in directions:
            result = engine.chat_message(task['id'], values)
            self.assertEqual(result['discussion'][-1]['status'], 'work_queued')
            self.assertEqual(result['discussion'][-1]['after_event'], len(task['events']))
        self.assertEqual(len(task['chat_work_queue']), 2)
        engine.chat_message = Mock(return_value={'id': task['id']})
        discussion.finish(engine, runtime)
        self.assertEqual([call.args[1] for call in engine.chat_message.call_args_list], directions)
        self.assertTrue(all(t['status'] == 'directed' for t in task['discussion']))
        self.assertEqual(task['limits'], saved_task()['limits'])

    def test_late_question_is_handed_off_and_planning_keeps_conversation(self):
        task = saved_task(); runtime = Runtime(task)
        engine = SimpleNamespace(lock=threading.RLock(), store=Mock(), runtimes={task['id']: runtime})
        with patch.object(discussion.threading, 'Thread') as thread:
            discussion.finish(engine, runtime)
        self.assertTrue(runtime.discussion_finished)
        successor = engine.runtimes[task['id']]
        self.assertIsNot(successor, runtime)
        self.assertTrue(successor.discussion_only)
        self.assertIs(successor.task, task)
        thread.return_value.start.assert_called_once()
        prepared = {'status': 'awaiting_authorization', 'branch_run': {'new_plan': True}}
        task['discussion_requests'] = {'planner': 2}
        discussion.preserve(task, prepared)
        self.assertEqual(prepared['discussion'], task['discussion'])
        self.assertIsNot(prepared['discussion'], task['discussion'])
        self.assertEqual(prepared['discussion_requests'], {'planner': 2})
        self.assertEqual(prepared['status'], 'awaiting_authorization')

    def test_answer_uses_normal_accounted_request_and_only_read_tools(self):
        task = saved_task()
        task['workspace'] = '/unused'
        runtime = Runtime(task)
        engine = Mock()
        engine.validate_offered_tools = Engine.validate_offered_tools
        calls = [{'id': 'read', 'type': 'function', 'function': {'name': 'read_file', 'arguments': json.dumps({'path': 'app.py'})}}]
        engine.request.side_effect = [
            {'role': 'assistant', 'tool_calls': calls},
            {'role': 'assistant', 'content': 'Example only:\n```python\nprint("hello")\n```'}]
        with patch('cheapos.workspace.Workspace') as workspace:
            workspace.return_value.read_file.return_value = {'content': 'print("hello")'}
            answer = discussion.answer(engine, runtime, task['discussion'][0])
            workspace.return_value.read_file.assert_called_once_with(path='app.py')
        self.assertIn('```python', answer)
        for request in engine.request.call_args_list:
            self.assertEqual(request.kwargs, {'purpose': 'chat_reply'})
            names = {t['function']['name'] for t in request.args[2]}
            self.assertEqual(names, {'read_file', 'list_files', 'search', 'outline_file'})
        self.assertEqual(task['checks'], [{'passed': True, 'digest': 'candidate'}])
        from cheapos.metrics import action_totals
        from cheapos.work_budgets import usage
        self.assertEqual(action_totals(task)['counts']['tools'], 1)
        self.assertEqual(usage(task)['work_tools'], 0)

    def test_repeated_read_becomes_answer_from_evidence_not_work_recovery(self):
        task = saved_task(); task['workspace'] = '/unused'
        runtime = Runtime(task); engine = Mock()
        engine.validate_offered_tools = Engine.validate_offered_tools
        read = {'role': 'assistant', 'tool_calls': [{'id': 'read', 'type': 'function', 'function': {'name': 'list_files', 'arguments': '{}'}}]}
        engine.request.side_effect = [read, read, {'content': 'The files explain it.'}]
        with patch('cheapos.workspace.Workspace') as workspace:
            workspace.return_value.list_files.return_value = ['app.py']
            self.assertEqual(discussion.answer(engine, runtime, task['discussion'][0]), 'The files explain it.')
            workspace.return_value.list_files.assert_called_once()
        self.assertEqual(engine.request.call_args_list[-1].args[2], [])

    def test_existing_task_question_does_not_call_start_steer_or_recovery(self):
        engine = Engine.__new__(Engine)
        engine.start = Mock(); engine.steer = Mock(); engine.branch = Mock()
        with patch.object(discussion, 'enqueue', return_value={'id': 'task'}) as enqueue:
            result = engine.chat_message('task', {'message': 'Why did the reviewer reject this?'})
        self.assertEqual(result, {'id': 'task'})
        enqueue.assert_called_once_with(engine, 'task', 'Why did the reviewer reject this?')
        engine.start.assert_not_called(); engine.steer.assert_not_called(); engine.branch.message.assert_not_called()

    def test_active_work_receives_discussion_context_without_changing_requirements_or_history(self):
        task = saved_task()
        task['discussion'][0].update(status='answered', answer='Option one is small; option two is easier to maintain.')
        runtime = Runtime(task)
        messages = [{'role': 'user', 'content': 'Use the second option.'}]
        before = copy.deepcopy(task)
        for role, purpose in [('worker', None), ('planner', 'branch_planning')]:
            with patch('cheapos.reviewer_recovery.request', return_value={'content': 'Understood'}) as request, patch('cheapos.work_policy.refresh_edit_recovery'):
                Engine.request(Mock(), runtime, messages, [], role, purpose=purpose)
            sent = request.call_args.args[2]
            self.assertIn('Option one', sent[-1]['content'])
            self.assertIn('not additional scope', sent[-1]['content'])
        self.assertEqual(len(messages), 1, 'Do not append duplicate context to durable worker messages')
        self.assertEqual(task, before)

    def test_chat_can_answer_at_work_limit_without_granting_more_work(self):
        runtime = Runtime(saved_task())
        runtime.answering_chat = True
        runtime.guard()
        runtime.answering_chat = False
        with self.assertRaises(Exception):
            runtime.guard()

    def test_answer_cannot_edit_or_submit_a_checkpoint(self):
        for name in ('replace_text', 'run_checks', 'checkpoint'):
            task = saved_task(); runtime = Runtime(task); engine = Mock()
            engine.validate_offered_tools = Engine.validate_offered_tools
            engine.request.return_value = {'tool_calls': [{'id': 'bad', 'function': {'name': name, 'arguments': '{}'}}]}
            with self.assertRaises(ProviderError):
                discussion.answer(engine, runtime, task['discussion'][0])

    def test_reply_counts_in_session_usage_but_not_work_allowance_or_authorship(self):
        from cheapos.metrics import dispatched_action, action_totals
        from cheapos.work_budgets import usage
        from cheapos.served_identity import review_workers
        task = saved_task()
        task['request_metrics'] = []
        for purpose in ('chat_reply', 'probe'):
            record = {'id': purpose, 'role': 'worker', 'purpose': purpose, 'request_context': 'chat_reply', 'dispatched': True}
            dispatched_action(task, record)
            task['request_metrics'].append(record)
        self.assertEqual(action_totals(task)['counts']['worker'], 2)
        self.assertEqual(usage(task)['work_requests'], 0)
        self.assertEqual(usage(task)['work_turns'], 0)
        self.assertEqual(review_workers(task, {}), [])


from tests.test_engine import LocalCase


class DiscussionRequestTests(LocalCase):
    def test_paused_chat_reply_is_accounted_and_respects_spending_without_resetting_work(self):
        task = self.fixture(paid=True)
        task.update(conversational=True, status='paused', error='Review needs attention', error_code='review_stall', no_call_turns=3)
        task['limits'].update(dollars=1, worker_turns=1)
        task['worker_turns'] = 1
        task['usage']['reviewer']['tokens'] = task['limits']['reviewer_tokens'] + 1
        self.engine.store.save(task)
        provider = Mock()
        provider.complete.return_value = ({'role': 'assistant', 'content': 'Here is an example:\n```python\nprint(1)\n```'},
                                          {'prompt_tokens': 10, 'completion_tokens': 5})
        self.engine.provider_factory = lambda *args: provider
        self.engine.chat_message(task['id'], {'message': 'Can you show me an example?'})
        saved = self.finish(task)
        self.assertEqual(saved['discussion'][-1]['status'], 'answered')
        self.assertEqual(saved['usage']['worker']['tokens'], 15)
        self.assertEqual(saved['request_metrics'][-1]['purpose'], 'chat_reply')
        self.assertEqual(saved['status'], 'paused')
        self.assertEqual(saved['error'], 'Review needs attention')
        self.assertEqual(saved['no_call_turns'], 3)
        self.assertEqual(saved['worker_turns'], 1)
        self.assertEqual(saved['requests'], task['requests'])
        self.assertEqual(saved['checks'], task['checks'])
        self.assertEqual(saved['checkpoints'], task['checkpoints'])
        saved['limits']['dollars'] = 0
        self.engine.store.save(saved)
        self.engine.chat_message(task['id'], {'message': 'Why this example?'})
        result = self.finish(task)
        self.assertEqual(result['discussion'][-1]['status'], 'failed')
        self.assertEqual(provider.complete.call_count, 1, 'No paid request after spending authority is exhausted')
        self.assertEqual(result['status'], 'paused')
        from cheapos.storage import Store
        result['discussion'].append({'id': 'interrupted', 'message': 'Explain the last check', 'status': 'queued'})
        self.engine.store.save(result)
        restarted = Store(self.engine.store.root).get(task['id'])
        self.assertEqual(restarted['discussion'][-1]['status'], 'interrupted')
        self.assertEqual(restarted['status'], 'paused')
