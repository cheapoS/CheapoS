import copy
import json
import unittest
from cheapos.worker_conversation import append_direction, refresh, receipt, LEGACY_ARGUMENT_NOTICE


class WorkerConversationTests(unittest.TestCase):
    def test_bad_arguments_become_retrievable_diagnostics_without_empty_call_examples(self):
        from cheapos.context_evidence import read
        task = {}
        bad = {'id': 'bad', 'function': {'name': 'write_file', 'arguments': '{broken'}}
        good = {'id': 'read', 'function': {'name': 'read_file', 'arguments': '{"path":"app.py"}'}}
        answer = {'role': 'tool', 'tool_call_id': 'read', 'content': '1: working = True'}
        history = [{'role': 'assistant', 'content': 'Keep the existing behavior.', 'tool_calls': [bad, good]},
                   {'role': 'tool', 'tool_call_id': 'bad', 'content': json.dumps({
                       'code': 'invalid_tool_arguments', 'error': 'Bad JSON'})}, answer]
        original = copy.deepcopy(history)
        result = refresh(history, [], task)
        self.assertEqual(history, original)
        assistant = next(m for m in result if m['role'] == 'assistant')
        self.assertEqual(assistant['tool_calls'], [good])
        self.assertEqual(assistant['content'], 'Keep the existing behavior.')
        self.assertIn(answer, result)
        diagnostic = next(m for m in result if m.get('content', '').startswith('Tool argument diagnostic: '))
        self.assertEqual(diagnostic['role'], 'user')
        info = json.loads(diagnostic['content'].split(': ', 1)[1])
        self.assertEqual(info['outcome'], 'Rejected before execution.')
        self.assertEqual(info['feedback'], [{'code': 'invalid_tool_arguments', 'error': 'Bad JSON'}])
        self.assertNotIn('{broken', str(result))
        self.assertEqual(json.loads(read(task, info['context_reference'])['content'])['assistant'], original[0])
        restored = json.loads(json.dumps(task))
        again = refresh(result, [], restored)
        self.assertEqual(sum(m.get('content', '').startswith('Tool argument diagnostic: ') for m in again), 1)
        self.assertEqual(restored['context_evidence'], task['context_evidence'])

    def test_legacy_empty_calls_and_invalid_shapes_do_not_become_assistant_templates(self):
        for raw in ('{}', None, '[]'):
            with self.subTest(raw=raw):
                listing = {'id': 'list', 'function': {'name': 'list_files', 'arguments': '{}'}}
                history = [{'role': 'assistant', 'content': 'Create the file.\n' + LEGACY_ARGUMENT_NOTICE,
                            'tool_calls': [{'id': 'bad', 'function': {'name': 'write_file', 'arguments': raw}}, listing]},
                           {'role': 'tool', 'tool_call_id': 'bad', 'content': '{"error":"Provide a relative file path"}'},
                           {'role': 'tool', 'tool_call_id': 'list', 'content': '["a.py"]'}]
                result = refresh(history, [], {})
                self.assertEqual(result[0]['tool_calls'], [listing])
                self.assertEqual([m for m in result if m['role'] == 'tool'], [history[-1]])
                self.assertEqual(result[0]['content'], 'Create the file.')
                self.assertNotIn(LEGACY_ARGUMENT_NOTICE, str(result))
                self.assertIn('Execution is not established', str(result))

    def test_known_shape_rejection_is_diagnostic_but_valid_interrupted_call_stays_uncertain(self):
        history = [{'role': 'assistant', 'tool_calls': [
            {'id': 'bad', 'function': {'name': 'write_file', 'arguments': '{}'}},
            {'id': 'pending', 'function': {'name': 'write_file', 'arguments': '{"path":"later.py","content":""}'}}]},
            {'role': 'tool', 'tool_call_id': 'bad', 'content': '{"code":"invalid_tool_arguments","executed":false}'}]
        result = refresh(history, [], {})
        self.assertEqual([c['id'] for m in result for c in m.get('tool_calls', [])], ['pending'])
        pending = next(m for m in result if m.get('tool_call_id') == 'pending')
        self.assertIn('outcome is not established', pending['content'])
        self.assertNotIn('bad', [m.get('tool_call_id') for m in result])

    def test_findings_and_exact_tool_results_survive_refresh_and_followup(self):
        history = [{'role': 'system', 'content': 'policy'},
                   {'role': 'user', 'content': 'Fix the button'},
                   {'role': 'assistant', 'content': 'The handler is missing',
                    'tool_calls': [{'id': 'read', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{}'}}]},
                   {'role': 'tool', 'tool_call_id': 'read', 'content': 'version A: no handler'},
                   {'role': 'assistant', 'content': 'Add the handler, then run focused checks.'}]
        original = copy.deepcopy(history)
        result = refresh(history, [{'role': 'system', 'content': 'new policy'}, {'role': 'user', 'content': 'version B: handler added; checks passed'}])
        self.assertEqual(result[1:len(history)], history[1:])
        self.assertEqual(history, original)
        self.assertEqual(result[0]['content'], 'new policy')
        self.assertIn('checks passed', result[-1]['content'])
        append_direction(result, 'Direction: ', 'Continue')
        result.append({'role': 'assistant', 'content': 'Ready for checkpoint'})
        before = copy.deepcopy(result)
        append_direction(result, 'Direction: ', 'Continue')
        self.assertEqual(result, before)
        append_direction(result, 'Direction: ', 'Change the label too')
        self.assertEqual(result[:-1], before)

    def test_interrupted_batch_is_closed_without_claiming_execution_or_replaying(self):
        history = [{'role': 'assistant', 'tool_calls': [{'id': 'a'}, {'id': 'b'}]},
                   {'role': 'tool', 'tool_call_id': 'a', 'content': 'Saved edit'}]
        result = refresh(history, [{'role': 'system', 'content': 'policy'}, {'role': 'user', 'content': 'saved state'}])
        self.assertEqual(result[2], history[1])
        self.assertEqual(result[3]['tool_call_id'], 'b')
        self.assertIn('not established', result[3]['content'])
        self.assertEqual(sum(m.get('role') == 'assistant' for m in result), 1)
        again = refresh(result, [{'role': 'system', 'content': 'policy'}, {'role': 'user', 'content': 'new state'}])
        self.assertEqual(sum(m.get('role') == 'tool' for m in again), 2)

    def test_receipt_detects_lost_history_without_storing_content(self):
        messages = [{'role': 'assistant', 'content': 'private finding'}, {'role': 'tool', 'content': 'private code'}]
        before = receipt(messages)
        self.assertNotIn('private', str(before))
        self.assertEqual(before['assistant_count'], 1)
        self.assertEqual(before['tool_result_count'], 1)
        self.assertNotEqual(before['sha256'], receipt(messages[1:])['sha256'])

class TransitionTests(unittest.TestCase):
    def test_continuation_deduplicates_and_preserves_repair(self):
        from cheapos.worker_conversation import continue_session
        task={'messages':[{'role':'user','content':'Keep the restart endpoint'},
                          {'role':'assistant','content':'Found handler at server.py:40'},
                          {'role':'assistant','tool_calls':[{'id':'edit','function':{'name':'replace_text','arguments':'{}'}}]},
                          {'role':'tool','tool_call_id':'edit','content':'edited'}]}
        base=[{'role':'system','content':'worker'},{'role':'user','content':'{"patch":"new"}'}]
        continue_session(task,base,'review_repair',{'finding':'Add readiness check'})
        count=len(task['messages'])
        continue_session(task,base,'restart',{'finding':'Add readiness check'})
        self.assertEqual(len(task['messages']),count)
        self.assertIn('server.py:40',str(task['messages']))
        self.assertEqual(sum(m.get('tool_call_id')=='edit' for m in task['messages']),1)
        task['workspace_generation']=2
        continue_session(task,base,'post_commit')
        self.assertIn('restart endpoint',str(task['messages']))

    def test_item_sessions_and_uncertain_calls(self):
        from cheapos.worker_conversation import continue_session
        task={'branch_run':{'current_item_id':'one'},'messages':[]}
        base=[{'role':'system','content':'worker'},{'role':'user','content':'{"objective":"one"}'}]
        continue_session(task,base,'start')
        task['messages'].append({'role':'assistant','tool_calls':[{'id':'x','function':{'arguments':'{}'}}]})
        continue_session(task,base,'restart')
        self.assertIn('outcome is not established',task['messages'][-1]['content'])
        task['branch_run']['current_item_id']='two'
        continue_session(task,[base[0],{'role':'user','content':'{"objective":"two"}'}],'next_item')
        self.assertNotIn('tool_calls',str(task['messages']))
        task['branch_run']['current_item_id']='one'
        continue_session(task,base,'resume_item')
        self.assertIn('outcome is not established',str(task['messages']))
