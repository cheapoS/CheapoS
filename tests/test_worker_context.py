"""Item-scoped context and recovery requests: no Git, network or real waits."""
import copy
import json
import unittest
from unittest.mock import Mock, patch

from cheapos.context_compaction import compact
from cheapos.context_evidence import read
from cheapos.engine import Engine, worker_system
from cheapos.instructions.runtime import text
from cheapos.recovery_context import packet
from cheapos.tools import CHAT_TOOLS, UNATTENDED_TOOLS, WORKER_TOOLS
from cheapos.worker_context import active_events, context_events, clear_read_guidance, repeated_read_guidance
from cheapos.worker_conversation import continue_session


OLD_NOTICE = "This read returned the same information twice. Answer the user's question from the evidence, use read_url for a supplied web link, or report_blocker to explain what is missing. Do not edit just to reset the loop guard. Another identical read ends research for this run."


def task_events():
    return [
        {'id': 1, 'kind': 'tool', 'title': 'write file', 'item_id': 'done',
         'detail': {'arguments': {'path': 'old.css'}, 'result': {'changed': True}}},
        {'id': 2, 'kind': 'assistant', 'title': 'Worker', 'item_id': 'done', 'detail': 'Old layout complete'},
        # The controller emits this marker before updating the active item ID.
        {'id': 3, 'kind': 'branch_item', 'item_id': 'done', 'detail': {'item_id': 'repair'}},
        {'id': 4, 'kind': 'tool', 'title': 'replace text',
         'detail': {'arguments': {'path': 'report.md'}, 'result': {'changed': True}}},
        {'id': 5, 'kind': 'assistant', 'title': 'Worker', 'item_id': 'repair', 'detail': 'Check the corrected report'},
        {'id': 6, 'kind': 'tool', 'title': 'write file', 'item_id': 'other',
         'detail': {'arguments': {'path': 'unrelated.py'}, 'result': {'changed': True}}},
    ]


class WorkerContextTests(unittest.TestCase):
    def task(self):
        return {'prompt': 'Maintain the project', 'requests': ['Maintain the project'],
                'branch_run': {'id': 'run', 'current_item_id': 'repair', 'authorization_ref': 'approved',
                               'items': [{'id': 'done', 'status': 'committed', 'outcome_summary': 'Layout complete'},
                                         {'id': 'repair', 'status': 'working', 'title': 'Repair report',
                                          'instructions': 'Resolve the missing source in the report',
                                          'acceptance_criteria': ['Source is cited'], 'required_checks': []}]},
                'events': task_events(), 'checks': [], 'patch': '', 'checkpoints': [],
                'workspace': '/unused', 'source': '/unused', 'changes': [], 'check_command': ['check']}

    def test_events_require_current_item_provenance_and_preserve_journal(self):
        task = self.task(); original = copy.deepcopy(task)
        self.assertEqual([e['id'] for e in active_events(task)], [4, 5])
        self.assertEqual(context_events(task), active_events(task))
        task['events'].pop(2)  # No boundary: only explicitly owned evidence is current.
        self.assertEqual([e['id'] for e in active_events(task)], [5])
        self.assertEqual(context_events(task), active_events(task))
        task['events'] = original['events']; task.pop('branch_run')
        task['events'].insert(4, {'id': 7, 'kind': 'user', 'detail': 'Next question'})
        self.assertEqual([e['id'] for e in active_events(task)], [5, 6])
        self.assertEqual(context_events(task), task['events'])
        self.assertEqual(len(task['events']), 7)

    def test_initial_action_and_compacted_snapshots_do_not_claim_old_item_edits(self):
        task = self.task(); app = Engine.__new__(Engine)
        app.carto = Mock(); app.carto.context.return_value = {'status': 'disabled'}
        workspace = Mock(); workspace.list_files.return_value = []
        workspace.patch.return_value = ''
        with patch('cheapos.engine.Workspace', return_value=workspace), \
                patch('cheapos.project_context.brief', return_value={}), \
                patch('cheapos.project_context.continuation', return_value={}):
            base = app.initial_messages(task)
            self.assertNotIn('old.css', str(base))
            self.assertNotIn('unrelated.py', str(base))
            self.assertIn('report.md', str(base))
            task['compact_edits'] = True
            action = app.action_messages(task)
            self.assertNotIn('old.css', str(action))
            self.assertIn('report.md', str(action))
        before = copy.deepcopy(task['events'])
        result = compact(task, base, [])
        memory = json.loads(result[1]['content'])['working_memory']
        self.assertEqual(memory['item_id'], 'repair')
        self.assertEqual([a['path'] for a in memory['recent_completed_actions']], ['report.md'])
        self.assertEqual(memory['recent_completed_actions'][0]['event_id'], 4)
        self.assertEqual(packet(task)['prior_worker_statements_unverified'], ['Check the corrected report'])
        self.assertEqual(packet(task)['completed_items'][0]['id'], 'done')
        self.assertEqual(task['events'], before)

    def test_saved_notice_refreshes_at_provider_boundary_through_compaction_and_handoff(self):
        from tests.test_transport import TransportTests
        app, runtime, _ = TransportTests().harness()
        runtime.task.update(self.task(), loop_guidance=OLD_NOTICE,
                            progress_state={'handoffs': 2}, usage=runtime.task['usage'])
        task = runtime.task
        observation = {'path': 'report.md', 'content': 'Verified sources', 'hash': 'source-hash'}
        task['messages'] = [
            {'role': 'system', 'content': worker_system(task)},
            {'role': 'user', 'content': 'Controller direction: ' + OLD_NOTICE},
            {'role': 'assistant', 'tool_calls': [{'id': 'source', 'type': 'function',
              'function': {'name': 'read_file', 'arguments': '{"path":"report.md"}'}}]},
            {'role': 'tool', 'tool_call_id': 'source',
             'content': json.dumps({'observation': observation, 'guidance': OLD_NOTICE})},
        ]
        limits = copy.deepcopy(task['limits']); events = copy.deepcopy(task['events'])
        Engine.deliver_loop_guidance(task)
        projected = copy.deepcopy(task['messages'])
        Engine.deliver_loop_guidance(task)
        self.assertEqual(task['messages'], projected)
        base = [{'role': 'system', 'content': worker_system(task)},
                {'role': 'user', 'content': json.dumps({'recovery_continuation': packet(task)})},
                {'role': 'user', 'content': 'Controller direction: ' + task['loop_guidance']}]
        task['messages'] = compact(task, base, task['messages'])
        runtime.task = task = json.loads(json.dumps(task))
        continue_session(task, base, 'worker_handoff')
        Engine.deliver_loop_guidance(task)
        captured = []
        provider = Mock()
        provider.streams_output = False
        provider.complete = lambda sent, tools, maximum: (captured.append((sent, tools)) or
            ({'role': 'assistant', 'content': 'Ready for checkpoint'},
             {'prompt_tokens': 2, 'completion_tokens': 3, 'cost': 0}))
        app.provider_factory = lambda *args: provider
        app._request_attempt(runtime, task['messages'], UNATTENDED_TOOLS, 'worker')
        sent, offered = captured[-1]
        self.assertNotIn(OLD_NOTICE, str(sent))
        self.assertEqual(str(sent).count(text('recovery.repeated_read_work')), 1)
        self.assertIn('checkpoint', {t['function']['name'] for t in offered})
        self.assertIn('report_blocker', {t['function']['name'] for t in offered})
        result = next(m for m in sent if m.get('tool_call_id') == 'source')
        self.assertEqual(json.loads(result['content'])['observation'], observation)
        self.assertEqual(task['limits'], limits)
        self.assertEqual(task['progress_state'], {'handoffs': 2})
        self.assertEqual(task['events'][:len(events)], events)
        self.assertTrue(any(OLD_NOTICE in read(task, ref)['content']
                            for ref in task['worker_context_refresh']['notice_references']))

    def test_progress_clears_only_read_notice_and_retains_operator_direction(self):
        task = self.task(); task['loop_guidance'] = repeated_read_guidance(task)
        task['messages'] = [{'role': 'user', 'content': 'User direction: Keep the table'}]
        Engine.deliver_loop_guidance(task)
        clear_read_guidance(task); Engine.deliver_loop_guidance(task)
        self.assertEqual(task['messages'], [{'role': 'user', 'content': 'User direction: Keep the table'}])
        task['loop_guidance'] = 'Repair the captured failing assertion'
        clear_read_guidance(task)
        self.assertEqual(task['loop_guidance'], 'Repair the captured failing assertion')

    def test_read_only_and_interactive_work_keep_distinct_goals_and_tools(self):
        from cheapos.work_policy import READ_ONLY_STARTERS, offered_tools
        for prompt, conversational, expected, available in (
            (READ_ONLY_STARTERS[0], True, 'research', CHAT_TOOLS),
            ('Fix the button', True, 'work', CHAT_TOOLS),
            ('Repair the report', False, 'work', WORKER_TOOLS),
        ):
            task = {'prompt': prompt, 'conversational': conversational, 'loop_guidance': OLD_NOTICE}
            Engine.deliver_loop_guidance(task)
            self.assertEqual(task['loop_guidance'], text('recovery.repeated_read_' + expected))
            names = {t['function']['name'] for t in offered_tools(task, available)}
            self.assertEqual('checkpoint' in names, expected == 'work')
            self.assertNotIn('report_blocker', names)
