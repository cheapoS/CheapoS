"""Deterministic controller coverage: no Git, subprocesses or model requests."""
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from cheapos.engine import Engine, BudgetError, CheckCommandError


class CheckpointAllowanceTests(unittest.TestCase):
    def setup_run(self, uncapped):
        engine = Engine.__new__(Engine)
        task = dict(limits={'uncapped_work': uncapped, 'iterations': 5},
                    patch='', iterations=0, checks=[], changes=[], checkpoints=[],
                    prompt='Hide samples', providers={}, active_role='worker',
                    check_command=['node', '--check', 'dist/app.js'], review_count=0)
        engine.verification_argv = Mock()
        engine.refresh_changes = Mock()
        engine.checks = Mock(return_value={'passed': True, 'command': task['check_command']})
        engine.event = Mock()
        engine.store = Mock()
        engine.file_tool = Mock(return_value={'text': '.hidden { display:none }'})
        runtime = SimpleNamespace(task=task, observations={}, stop=threading.Event(), guard=Mock())
        def request(*args):
            number = task['review_count']
            name = 'review_decision' if number >= 9 else 'read_file'
            params = {'decision': 'APPROVE', 'feedback': 'Verified hide behavior'} if number >= 9 else {'path': 'dist/styles.css'}
            return {'role': 'assistant', 'tool_calls': [{'id': str(number), 'function': {'name': name, 'arguments': json.dumps(params)}}]}
        engine.request = Mock(side_effect=request)
        return engine, runtime

    def run_checkpoint(self, engine, runtime):
        with patch('cheapos.engine.current_evidence', return_value=False), patch('cheapos.engine.progress.state', return_value={'revision': 0}), patch('cheapos.engine.reconciliation.ensure_resolved'):
            return engine.checkpoint(runtime, {'summary': 'Hide samples'})

    def test_uncapped_review_can_decide_after_eight_turns(self):
        engine, runtime = self.setup_run(True)
        result = self.run_checkpoint(engine, runtime)
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(runtime.task['review_count'], 10)
        self.assertEqual(runtime.guard.call_count, 10)
        self.assertNotIn('pending_review', runtime.task)
        self.assertTrue(any('Avoid repeating' in m.get('content', '') for m in engine.request.call_args.args[1]))
        self.assertTrue(runtime.task['checkpoints'][0]['messages'])

    def test_bounded_review_retains_limit_and_saved_exchanges(self):
        engine, runtime = self.setup_run(False)
        with self.assertRaises(BudgetError):
            self.run_checkpoint(engine, runtime)
        self.assertEqual(runtime.task['review_count'], 8)
        self.assertEqual(len(runtime.task['pending_review']['messages']), 17)

    def test_uncapped_review_still_obeys_pause(self):
        engine, runtime = self.setup_run(True)
        runtime.stop.set()
        with self.assertRaises(InterruptedError):
            self.run_checkpoint(engine, runtime)
        engine.request.assert_not_called()

    def test_bad_saved_command_returns_to_worker(self):
        engine, runtime = self.setup_run(True)
        runtime.task.update(status='reviewing', pending_checkpoint={}, pending_review={})
        engine.checkpoint = Mock(side_effect=CheckCommandError('Choose executable checks'))
        self.assertEqual(engine.checkpoint_feedback(runtime, {})['code'], 'invalid_check_command')
        self.assertEqual(runtime.task['status'], 'running')
        self.assertNotIn('pending_review', runtime.task)
        self.assertNotIn('pending_checkpoint', runtime.task)

    def test_repeated_checkpoint_failures_keep_repair_evidence_without_operator_pause(self):
        engine, runtime = self.setup_run(True)
        def fail_checks(*args):
            c = {'passed': False, 'command': runtime.task['check_command'], 'digest': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}
            runtime.task['checks'].append(c)
            return c
        engine.checks = Mock(side_effect=fail_checks)
        for _ in range(6):
            result = self.run_checkpoint(engine, runtime)
            self.assertEqual(result['decision'], 'REQUEST_CHANGES')
            self.assertFalse(result['checks']['passed'])
            self.assertIn('repair_context', result['checks'])
        self.assertEqual(engine.request.call_count, 0)  # Failed checks cannot enter review.

    def test_repeated_worker_check_failures_continue_with_focused_evidence(self):
        engine, runtime = self.setup_run(True)
        engine.checks = Mock(return_value={'passed': False, 'output': 'test failure', 'command': runtime.task['check_command']})
        for i in range(7):
            res = engine.worker_checks(runtime, {})
            self.assertIn('test failure', res['output'])
            self.assertIn('repair_context', res)
            if i >= 2:
                self.assertIn('change the repair approach', res['guidance'])
                self.assertNotIn('complete, correct implementation', res['guidance'])
        self.assertEqual(runtime.task['consecutive_worker_check_failures'], 7)

    def test_json_checkpoint_text_dispatches_feedback_directly(self):
        import hashlib
        from cheapos.engine import limits_from
        engine, runtime = self.setup_run(True)
        task = runtime.task
        task['status'] = 'running'
        task['limits'] = limits_from({})
        task['branch_run'] = {'items': [{'id': 'item1', 'review_repair': None}], 'current_item_id': 'item1'}
        task['patch'] = 'diff --git a/test b/test\n+fix'
        digest = hashlib.sha256(task['patch'].encode()).hexdigest()
        task['checks'] = [{'passed': True, 'digest': digest}]
        task['messages'] = []
        task['no_call_turns'] = 0
        task['turn_start_patch'] = task['patch']
        task['turn'] = 0
        task['worker_turns'] = 0
        task['request_worker_turns'] = 0
        runtime.started = 0
        runtime.step_turns = 0
        runtime.steer_queue = []
        engine.fit_worker_context = Mock()
        engine.deliver_loop_guidance = Mock()
        engine.validate_offered_tools = Mock()
        json_content = json.dumps({
            "repair_dispositions": [{"candidate_id": "c1", "finding_id": "f1", "disposition": "disproved", "evidence": "Test"}],
            "summary": "Fixed issue and passing tests.",
            "uncertainties": "None"
        })
        checkpoint_called = []
        def mock_cp(rt, args):
            checkpoint_called.append(args)
            task['status'] = 'paused'
            return {'decision': 'APPROVE'}
        engine.checkpoint_feedback = Mock(side_effect=mock_cp)
        engine.request = Mock(return_value={'role': 'assistant', 'content': json_content, 'tool_calls': []})
        runtime.edit_versions = {}

        engine._run_until_pause(runtime)
        self.assertEqual(len(checkpoint_called), 1)
        self.assertEqual(checkpoint_called[0]['summary'], 'Fixed issue and passing tests.')
        self.assertEqual(checkpoint_called[0]['repair_dispositions'][0]['disposition'], 'disproved')
        self.assertTrue(any('Submitting verified changes for review' in str(call) for call in engine.event.call_args_list))


    def test_unattended_recovery_text_continues_to_read_edit_and_checkpoint(self):
        import copy
        import tempfile
        from pathlib import Path
        from cheapos.engine import Runtime, ACTION_GUIDANCE, limits_from
        from cheapos.workspace import Workspace
        engine, _ = self.setup_run(False)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'app.js'
            target.write_text('// context\n' * 1900 + '// wire manager here\n')
            workspace = Workspace(directory)
            task = dict(status='running', workspace=directory, active_role='worker',
                        limits=limits_from({'worker_turns':200}), conversational=True,
                        worker_turns=53, request_worker_turns=14,
                        tool_actions=0, patch='', checks=[], changes=[], checkpoints=[],
                        prompt='Implement Project Manager logic', events=[],
                        action_pending=True, loop_guidance=ACTION_GUIDANCE, providers={},
                        branch_run={'authorization_ref':'approved', 'current_item_id':'4',
                                    'items':[{'id':'4','status':'working','acceptance_criteria':['Wire manager']}]},
                        messages=[{'role':'system','content':ACTION_GUIDANCE}])
            limits = copy.deepcopy(task['limits'])
            runtime = Runtime(task)
            runtime.action_context_ready = True
            engine.lock = threading.RLock()
            engine.fit_worker_context = Mock()
            engine.deliver_loop_guidance = Mock()
            engine.refresh_worker_conversation = Mock()
            engine.file_tool = lambda task,name,args,runtime=None: getattr(workspace,name)(**args)
            requested = []
            responses = iter([
                {'role':'assistant','content':"I'll wire the Project Manager now."},
                {'role':'assistant','tool_calls':[{'id':'read','function':{'name':'read_file','arguments':json.dumps({'path':'app.js','start_line':1900})}}]},
                {'role':'assistant','tool_calls':[{'id':'edit','function':{'name':'append_text','arguments':json.dumps({'path':'app.js','text':'wireProjectManager();\n'})}}]},
                {'role':'assistant','tool_calls':[{'id':'checkpoint','function':{'name':'checkpoint','arguments':'{"summary":"Manager wired"}'}}]},
            ])
            def request(rt, messages, tools, role):
                requested.append(copy.deepcopy(messages))
                self.assertEqual(role,'worker')
                self.assertIn('read_file',{tool['function']['name'] for tool in tools})
                self.assertNotIn('Do not request read_file',str(messages))
                return next(responses)
            engine.request = Mock(side_effect=request)
            def checkpoint(rt,args):
                # Existing verification/review executors are covered separately;
                # this case proves the worker loop reaches them without rescue.
                self.assertIn('wireProjectManager();',target.read_text())
                task['status']='approved'
                return {'decision':'APPROVE'}
            engine.checkpoint_feedback = Mock(side_effect=checkpoint)
            engine._run_until_pause(runtime)
            self.assertEqual(task['status'],'approved', task.get('error'))
            self.assertEqual(len(requested),4)
            read_result = next(m for m in requested[2] if m.get('tool_call_id')=='read')
            self.assertIn('1901: // wire manager here',read_result['content'])
            engine.checkpoint_feedback.assert_called_once_with(runtime, {'summary':'Manager wired'})
            self.assertEqual(task['limits'],limits)
            self.assertEqual(task['worker_turns'],57)
            self.assertFalse(task['action_pending'])

    def test_stop_still_prevents_dispatch_during_action_recovery(self):
        from cheapos.engine import Runtime, limits_from
        engine,_ = self.setup_run(False)
        task=dict(status='running',active_role='worker',limits=limits_from({}),
                  action_pending=True,patch='',checks=[],changes=[],events=[])
        runtime=Runtime(task);runtime.stop.set()
        engine.request=Mock()
        engine._run_until_pause(runtime)
        engine.request.assert_not_called()
        self.assertEqual(task['status'],'paused')
        self.assertEqual(task['error'],'Task stopped')

    def test_budget_error_survives_worker_wrapper_for_branch_pause(self):
        from cheapos import branch_pause
        engine, runtime = self.setup_run(False)
        task = runtime.task
        task.update(status='running', branch_run={'schema_version':1,'id':'run','event_sequence':0,
                    'events':[], 'status':'running','current_item_id':'5',
                    'items':[{'id':'5','status':'reviewing'}]},
                    request_metrics=[{'id':'blocked','role':'reviewer','model':'fixture/reviewer'}])
        runtime.guard.side_effect = BudgetError('Request cannot fit', 'reviewer_tokens', 159110, 200000)
        engine._run_until_pause(runtime)
        self.assertEqual(task['status'],'budget_paused')
        self.assertEqual(task['error_code'],'budget_exceeded')
        engine.request.assert_not_called()
        detail = branch_pause.apply(task, ValueError(task['error']))
        self.assertEqual(detail['cause'],'exhausted_work')
        self.assertEqual(detail['role'],'reviewer')
        self.assertIn('159110',detail['explanation'])

    def test_interactive_review_also_pages_large_inventories(self):
        from cheapos.providers import reserve, reconcile
        from tests.test_review_inventory import inventory
        engine,runtime=self.setup_run(False)
        runtime.task['limits'].update(output_tokens=8192, reviewer_tokens=200000, dollars=0)
        runtime.task['usage']={'reviewer':{'tokens':159110,'cost':0},'cost':0,
                               'uncertain_requests':0,'estimated_requests':0}
        engine.file_tool.return_value=inventory()
        def request(rt,messages,tools,role):
            if engine.request.call_count==1:
                return {'role':'assistant','tool_calls':[{'id':'listing','function':{'name':'list_files','arguments':'{}'}}]}
            self.assertEqual(json.loads(messages[-1]['content'])['file_count'],900)
            config={'input_rate':0,'output_rate':0}
            reservation=reserve(runtime.task,config,messages,tools,role)
            reconcile(runtime.task,config,reservation,{'prompt_tokens':1000,'completion_tokens':500})
            return {'role':'assistant','tool_calls':[{'id':'decision','function':{'name':'review_decision',
                    'arguments':json.dumps({'decision':'APPROVE','feedback':'Checked current source and verification.'})}}]}
        engine.request=Mock(side_effect=request)
        self.assertEqual(self.run_checkpoint(engine,runtime)['decision'],'APPROVE')
        self.assertEqual(engine.request.call_count,2)
        self.assertEqual(runtime.task['limits']['reviewer_tokens'],200000)
