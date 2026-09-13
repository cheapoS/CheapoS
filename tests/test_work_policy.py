import json
from pathlib import Path
from unittest.mock import patch
from cheapos import work_policy
from test_engine import LocalCase, call


class WorkPolicyTests(LocalCase):
    def large_case(self, proactive=True):
        task=self.fixture(paid=True);root=Path(task['workspace']);(root/'large.py').write_text('# padding\n'*250+'value = 1\n')
        task['conversational']=True;task['limits']['dollars']=1;task['limits']['worker_turns']=10
        self.engine.store.save(task);requests=[]
        replies=iter([call('read_file',{'path':'large.py','start_line':240,'end_line':260}),
                      call('replace_lines',{'path':'large.py','start_line':251,'end_line':251,'new_text':'value = 2'}),
                      call('read_file',{'path':'large.py','start_line':240,'end_line':260}),
                      call('replace_lines',{'path':'large.py','start_line':251,'end_line':251,'new_text':'value = 3'}),
                      call('ask_user',{'question':'Continue with the remaining sample?'})])
        class Provider:
            def complete(self,messages,tools,maximum):
                requests.append((messages.copy(),[t['function']['name'] for t in tools],maximum))
                response = call('replace_text') if not proactive and len(requests)==2 else next(replies)
                if not proactive and len(requests)==2:response['tool_calls'][0]['function']['arguments']='{\"path\":'
                return response,{'prompt_tokens':10,'completion_tokens':5,'cost':0}
        self.engine.provider_factory=lambda *args:Provider()
        original=work_policy.small_edit_reason
        def policy(value):
            reason=original(value)
            return None if not proactive and reason and 'observed file exceeds' in reason else reason
        with patch('cheapos.work_policy.small_edit_reason',side_effect=policy):
            self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply',result['error'])
        self.assertIn('replace_text',requests[0][1]);self.assertIn('replace_lines',requests[1 if proactive else 2][1]);self.assertNotIn('replace_text',requests[1 if proactive else 2][1])
        self.assertIn('read_file',requests[1][1]);self.assertEqual(requests[0][2],requests[1][2])
        self.assertEqual((root/'large.py').read_text().splitlines()[-1],'value = 3')
        failures=len([e for e in result['events'] if e['kind']=='tool_error'])
        self.assertEqual(failures,0 if proactive else 1)
        self.assertEqual(result['providers'],task['providers'])
        return len(requests),failures

    def test_large_observed_file_avoids_one_failed_whole_edit_request(self):
        self.assertEqual(self.large_case(False),(6,1))
        self.assertEqual(self.large_case(True),(5,0))

    def test_small_ordinary_edit_and_supported_output_allowance_signals(self):
        task=self.fixture();self.assertIsNone(work_policy.small_edit_reason(task))
        task['limits']['output_tokens']=768;self.assertIn('768',work_policy.small_edit_reason(task))
        task['limits']['output_tokens']=2048;task['events'].append({'kind':'tool_error','title':'Bad edit','detail':{'tool':'replace_text'}})
        self.assertIn('observed',work_policy.small_edit_reason(task))

    def test_stage_priorities_keep_every_tool_and_complex_review(self):
        from cheapos.engine import CHAT_TOOLS, REVIEW_TOOLS
        for stage in ('orientation','implementation','verification','review'):
            self.assertEqual({t['function']['name'] for t in work_policy.prioritize(CHAT_TOOLS,stage)}, {t['function']['name'] for t in CHAT_TOOLS})
        self.assertEqual(len(work_policy.prioritize(REVIEW_TOOLS,'review')),len(REVIEW_TOOLS))
        self.assertIn('every active requirement',work_policy.instruction('implementation'))
