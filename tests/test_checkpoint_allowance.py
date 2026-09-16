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

    def test_repeated_check_failures_on_checkpoint_pause_loop(self):
        from cheapos.engine import ProgressPause
        engine, runtime = self.setup_run(True)
        def fail_checks(*args):
            c = {'passed': False, 'command': runtime.task['check_command'], 'digest': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}
            runtime.task['checks'].append(c)
            return c
        engine.checks = Mock(side_effect=fail_checks)
        for _ in range(2):
            result = self.run_checkpoint(engine, runtime)
            self.assertEqual(result['decision'], 'REQUEST_CHANGES')
        with self.assertRaisesRegex(ProgressPause, 'Verification has failed 3 consecutive times on unchanged files'):
            self.run_checkpoint(engine, runtime)
