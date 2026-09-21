"""Edit recovery covers the shared mutation registry without model or Git work."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from cheapos import work_policy
from cheapos.edit_history import MUTATIONS
from cheapos.engine import Engine, ToolArgumentsError


class EditArgumentRecoveryTests(unittest.TestCase):
    def test_first_empty_edit_call_enters_recovery_only_for_automatic_worker(self):
        for name in sorted(MUTATIONS):
            for role, status, pinned in [('worker', 'running', False),
                                         ('worker', 'running', True),
                                         ('reviewer', 'reviewing', False),
                                         ('worker', 'reviewing', False)]:
                with self.subTest(tool=name, role=role, status=status, pinned=pinned):
                    task = {'active_role': role, 'status': status,
                            'execution': {'mode': 'remote'}, 'route': {'mode': 'remote'}}
                    if pinned:
                        task['settings_snapshot'] = {'values': {'roles': {'worker': {'strategy': 'only'}}}}
                    runtime = SimpleNamespace(task=task, argument_failures=0, compact_context_ready=True)
                    engine = object.__new__(Engine)
                    engine.event = Mock()
                    engine.file_tool = Mock()
                    tool_call = {'id': 'bad-edit', 'function': {'name': name, 'arguments': '{}'}}
                    with self.assertRaises(ToolArgumentsError) as caught:
                        engine.parse_call(tool_call)
                    result = engine.tool_argument_feedback(runtime, caught.exception)
                    recovering = role == 'worker' and status == 'running' and not pinned
                    self.assertEqual(bool(work_policy.small_edit_reason(task)), recovering)
                    self.assertEqual(runtime.compact_context_ready, not recovering)
                    self.assertEqual(task['progress_state']['malformed_attempts'], 1)
                    self.assertEqual(runtime.argument_failures, 1)
                    self.assertFalse(result['executed'])
                    self.assertFalse(result['changed'])
                    engine.file_tool.assert_not_called()

    def test_edit_attempts_include_every_mutation_and_exclude_read_activity(self):
        for name in sorted(MUTATIONS | {'read_file', 'outline_file', 'search'}):
            for kind in ('tool', 'tool_error', 'assistant'):
                for detail, title in [({'tool': name}, 'Model needs to correct tool arguments'),
                                      ({}, name.replace('_', ' '))]:
                    with self.subTest(tool=name, kind=kind, detail=detail):
                        task = {'events': [{'kind': kind, 'title': title, 'detail': detail}]}
                        self.assertEqual(work_policy.attempted_edit(task),
                                         name in MUTATIONS and kind != 'assistant')
