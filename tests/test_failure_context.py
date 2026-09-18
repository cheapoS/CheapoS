"""Small prompt projections and dispatch doubles; no model/Git requests or waits."""
import copy
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from cheapos.context_evidence import read
from cheapos.failure_context import project


def failed(identity, **changes):
    result = {'code': 'syntax_edit_rejected', 'updated': False, 'changed': False,
              'rolled_back': True, 'syntax_warning': 'unexpected indent', 'hash': 'version-a',
              'current_file': {'hash': 'version-a', 'content': '    source line\n' * 100},
              'attempts': identity, **changes}
    return [{'role': 'assistant', 'content': 'Trying this replacement', 'tool_calls': [
                {'id': str(identity), 'type': 'function', 'function': {'name': 'replace_lines',
                 'arguments': json.dumps({'path': 'app.py', 'start_line': 2, 'end_line': 2,
                                           'new_text': 'def f():'})}}]},
            {'role': 'tool', 'tool_call_id': str(identity), 'content': json.dumps(result)}]


class FailureContextTests(unittest.TestCase):
    def test_duplicate_history_folds_without_losing_exact_evidence_or_authority(self):
        history = [{'role': 'system', 'content': 'Respect permissions'},
                   {'role': 'user', 'content': 'Fix the handler; preserve accessibility'}]
        for index in range(30):
            history.extend(failed(index))
        task = {'messages': history, 'limits': {'uncapped_work': True, 'dollars': 0},
                'usage': {'worker': {'tokens': 9000}}, 'progress_state': {'revision': 2},
                'pending_review': {'feedback': 'Preserve accessibility'}}
        original = copy.deepcopy(task)
        projected, info = project(task, history)
        self.assertEqual(info['omitted_exchanges'], 28)
        self.assertLess(info['after_bytes'], info['before_bytes'] / 5)
        self.assertEqual(projected[:4], history[:4])
        self.assertEqual(projected[-2:], history[-2:])
        for key, value in original.items():
            self.assertEqual(task[key], value)
        summary = json.loads(projected[4]['content'].split(': ', 1)[1])
        restored = json.loads(json.dumps(task))
        for index, reference in enumerate(summary['context_references'], 1):
            self.assertEqual(json.loads(read(restored, reference)['content']), failed(index))
        count = len(restored['context_evidence'])
        again, second_info = project(restored, restored['messages'])
        self.assertEqual(again, projected)
        self.assertEqual(second_info, info)
        self.assertEqual(len(restored['context_evidence']), count)

    def test_changed_evidence_and_directions_break_duplicate_runs(self):
        boundaries = [
            [{'role': 'user', 'content': 'Keep the revised requirement'}],
            [{'role': 'system', 'content': 'Coordinator: try exact text instead'}],
            failed('different-version', hash='version-b'),
            failed('different-defect', syntax_warning='unclosed bracket'),
            failed('saved-edit', updated=True, changed=True, code=None),
            failed('generic-error', code='tool_error', rolled_back=False, error='Outcome unknown'),
            failed('incomplete')[:1],
        ]
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                history = failed(1) + failed(2) + boundary + failed(3) + failed(4)
                result, info = project({}, history)
                self.assertEqual(info['omitted_exchanges'], 0)
                self.assertEqual(result, history)

    def test_legacy_rollbacks_fold_but_mixed_or_ambiguous_batches_do_not(self):
        history = sum((failed(n, code=None) for n in range(8)), [])
        self.assertEqual(project({}, history)[1]['omitted_exchanges'], 6)
        for kind in ('mixed', 'orphan', 'malformed', 'bad-call', 'bad-function', 'bad-list'):
            history = []
            for n in range(8):
                group = failed(n)
                if kind == 'mixed':
                    group[0]['tool_calls'].append({'id': 'read' + str(n), 'function': {
                        'name': 'read_file', 'arguments': '{"path":"requirements.md"}'}})
                    group.append({'role': 'tool', 'tool_call_id': 'read' + str(n), 'content': 'New evidence'})
                elif kind == 'orphan':
                    group[1]['tool_call_id'] = 'unknown'
                elif kind == 'malformed':
                    group[0]['tool_calls'][0]['function']['arguments'] = '{'
                elif kind == 'bad-call':
                    group[0]['tool_calls'] = [None]
                elif kind == 'bad-function':
                    group[0]['tool_calls'][0]['function'] = None
                else:
                    group[0]['tool_calls'] = {'id': 'invalid'}
                history.extend(group)
            self.assertEqual(project({}, history)[0], history)

    def test_worker_dispatch_uses_projection_and_reviewer_keeps_full_evidence(self):
        from cheapos.engine import Engine
        from cheapos.context_budget import payload_bytes
        task = {'prompt': 'Fix handler', 'messages': sum((failed(n) for n in range(8)), []),
                'worker_turns': 8, 'tool_actions': 8, 'status': 'running'}
        original = copy.deepcopy(task['messages'])
        runtime = SimpleNamespace(task=task, stop=threading.Event())
        engine = Engine.__new__(Engine)
        engine.provider_factory = Mock()
        engine.store = Mock()
        engine._resolve_provider_config = Mock(return_value={
            'model': 'fixture', 'base_url': 'http://local.invalid', 'input_rate': 0, 'output_rate': 0})
        engine._perform_request = Mock(return_value={'role': 'assistant', 'content': 'Use the current file.'})
        engine._request_attempt(runtime, task['messages'], [], 'worker')
        dispatched = engine._perform_request.call_args.args[1]
        metric = task['request_metrics'][-1]
        self.assertEqual(metric['failure_history']['omitted_exchanges'], 6)
        self.assertEqual(metric['context_payload_bytes'], payload_bytes(dispatched, []))
        self.assertEqual(task['messages'], original)
        engine._request_attempt(runtime, task['messages'], [], 'reviewer')
        self.assertNotIn('failure_history', task['request_metrics'][-1])
        self.assertEqual(engine._perform_request.call_args.args[1], original)

    def test_unknown_capacity_still_folds_failures_before_budget_estimation(self):
        from cheapos.engine import Engine
        task = {'messages': sum((failed(n) for n in range(8)), []), 'active_role': 'worker',
                'limits': {'output_tokens': 2048}}
        runtime = SimpleNamespace(task=task)
        engine = Engine.__new__(Engine)
        engine.event = Mock()
        engine._resolve_provider_config = Mock(return_value={'model': 'fixture', 'base_url': 'http://local.invalid'})
        engine.fit_worker_context(runtime, [])
        expected = project(task, task['messages'])[0]
        from cheapos.context_budget import payload_bytes
        self.assertIsNone(task['context_budget']['capacity_tokens'])
        self.assertFalse(task['context_budget']['compact'])
        self.assertEqual(task['context_budget']['payload_bytes'], payload_bytes(expected, []))
