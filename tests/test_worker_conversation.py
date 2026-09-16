import copy
import unittest
from cheapos.worker_conversation import append_direction, refresh, receipt


class WorkerConversationTests(unittest.TestCase):
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
