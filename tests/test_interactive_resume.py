"""Saved Interactive continuation, entirely in memory: no Git or model calls."""
import copy
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import progress
from cheapos.engine import Engine, limits_from
from cheapos.worker_conversation import continue_session


def call(name, arguments):
    return {'role': 'assistant', 'tool_calls': [{'id': name, 'type': 'function',
            'function': {'name': name, 'arguments': json.dumps(arguments)}}]}


class InteractiveResumeTests(unittest.TestCase):
    def setup_run(self, uncapped=True):
        engine = Engine.__new__(Engine)
        prompt = 'When I restart the app, the project manager pops up. Only show it if no project exists.'
        task = dict(id='saved', prompt=prompt, requests=[prompt], conversational=True,
                    status='paused', error_code='progress_limit', error='Coordinator reassessment failed',
                    workspace='/unused', demo=False, providers={}, active_role='worker',
                    limits=limits_from({'uncapped_work':uncapped}), worker_turns=41,
                    request_worker_turns=41, turn=41, iterations=0, review_count=0,
                    patch='', turn_start_patch='', changes=[], checks=[], checkpoints=[],
                    check_command=['node', '--check', 'dist/app.js'], events=[],
                    usage={'worker':{'tokens':500}, 'uncertain_requests':1},
                    answer_pending=True, action_pending=False,
                    operator_continue={'status':'blocked', 'reason':'Old exhausted recovery'},
                    execution={'coordinator_assistance':True},
                    messages=[{'role':'system','content':'Worker instructions'},
                              {'role':'user','content':'Saved finding: dist/app.js opens the project manager on startup.'}],
                    coordinator_recovery=[{'key':'previous', 'state':'failed',
                                           'error_code':'coordinator_path_reference'}])
        progress.state(task).update(answer_attempts=1, handoffs=2, inspected={'old-version':[559,560,561,562]})
        task['recovery_blocked'] = progress.state(task)['revision']
        engine.lock = threading.RLock()
        engine.runtimes = {}
        engine.startup = SimpleNamespace(busy=lambda:False)
        engine.store = SimpleNamespace(get=lambda _:task, save=Mock())
        engine.require_active_task = Mock()
        engine.admission = Mock()
        engine.event = Mock()
        engine.refresh_changes = Mock()
        engine.initial_messages = Mock(return_value=[{'role':'system','content':'Worker instructions'},
                                                    {'role':'user','content':prompt}])
        engine.refresh_worker_conversation = lambda rt: continue_session(task, engine.initial_messages(task), 'recovery')
        engine.fit_worker_context = Mock()
        engine.checkpoint_boundary = Mock()
        engine.verification_argv = Mock()
        engine.checks = Mock(return_value={'passed':True, 'command':task['check_command']})
        engine._run = engine._run_until_pause
        return engine, task

    def start_inline(self, engine, task, message='continue'):
        def thread(target, args, **kwargs):
            return SimpleNamespace(start=lambda:target(*args), is_alive=lambda:False)
        with patch('cheapos.engine.threading.Thread', side_effect=thread), patch('cheapos.engine.reconciliation.ensure_resolved'):
            return engine.start(task['id'], {'message':message})

    def test_continue_after_uncapping_reaches_independent_review_without_new_request(self):
        for message in ('continue', 'try again', None):
            with self.subTest(message=message):
                engine, task = self.setup_run()
                original = copy.deepcopy(task)
                seen = []
                def edit(rt, name, args, *unused):
                    if name == 'read_file':
                        return {'path':'dist/app.js', 'content':'unchanged startup condition'}
                    self.assertEqual(name, 'replace_text')
                    task.update(patch='diff: corrected startup condition', changes=[{'path':'dist/app.js'}])
                    return {'path':'dist/app.js', 'changed':True}
                engine.worker_file_tool = Mock(side_effect=edit)
                repeated_reads = 6 if message is None else 0
                responses = iter([call('read_file', {'path':'dist/app.js'})] * repeated_reads +
                                 [call('replace_text', {'path':'dist/app.js','old':'old','new':'new'}),
                                  call('checkpoint', {'summary':'Corrected startup behavior'}),
                                  call('review_decision', {'decision':'APPROVE','feedback':'Startup condition and check evidence satisfy the request.'})])
                def request(rt, messages, tools, role):
                    seen.append((role, copy.deepcopy(messages), {t['function']['name'] for t in tools}))
                    return next(responses)
                engine.request = Mock(side_effect=request)
                with patch('cheapos.coordinator_dispatch.consult', return_value=False):
                    result = self.start_inline(engine, task, message)
                self.assertEqual(result['status'], 'approved', result.get('error'))
                self.assertEqual([r[0] for r in seen], ['worker'] * (2 + repeated_reads) + ['reviewer'])
                self.assertIn('replace_text', seen[0][2])
                self.assertIn('Saved finding:', json.dumps(seen[0][1]))
                self.assertEqual(task['requests'], original['requests'])
                self.assertEqual(task['operator_continue']['status'], 'running')
                self.assertEqual(task['usage'], original['usage'])
                self.assertEqual(task['limits'], original['limits'])
                self.assertEqual(task['coordinator_recovery'], original['coordinator_recovery'])
                self.assertEqual(progress.state(task)['answer_attempts'], 1)
                self.assertEqual(progress.state(task)['handoffs'], 2)
                self.assertEqual(task['worker_turns'], 43 + repeated_reads)
                engine.checks.assert_called_once()
                self.assertEqual(task['checkpoints'][-1]['decision'], 'APPROVE')

    def test_uncapped_resume_preserves_pending_command_and_environment_gates(self):
        for pending in ({'pending_approval':{'command':['test']}},
                        {'environment_setup':{'status':'missing'}}):
            with self.subTest(pending=pending):
                engine, task = self.setup_run()
                task.update(pending)
                engine.request = Mock()
                with self.assertRaises(ValueError):
                    self.start_inline(engine, task)
                engine.request.assert_not_called()
                for key, value in pending.items():
                    self.assertEqual(task[key], value)

    def test_saved_answer_only_step_returns_to_implementation(self):
        engine, task = self.setup_run()
        engine.request = Mock()
        engine.finish_answer(SimpleNamespace(task=task))
        engine.request.assert_not_called()
        self.assertFalse(task['answer_pending'])
        self.assertTrue(task['action_pending'])

    def test_new_action_recovery_queues_existing_authorized_worker_handoff(self):
        engine, task = self.setup_run()
        engine.defer_route = Mock()
        engine._run = Mock()
        with patch('cheapos.engine.automatic', return_value=True):
            self.start_inline(engine, task)
        engine.defer_route.assert_called_once()
        self.assertEqual(engine.defer_route.call_args.args[1], 'worker')
        self.assertTrue(task['action_pending'])
        self.assertFalse(task['answer_pending'])
