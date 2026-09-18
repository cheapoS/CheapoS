"""Completed tool responses can repair bad argument JSON without executing it."""
import io
import json
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from cheapos.engine import Engine, ToolArgumentsError, extract_fallback_tool_calls, strip_leaked_actions
from cheapos.providers import ChatProvider, ProviderError
from test_engine import LocalCase, call
from test_streaming import chunk


def malformed(name='write_file', arguments='{"path":"unsafe.txt","content":"bad\ntext"}'):
    return {'role':'assistant','content':None,'tool_calls':[{'id':'malformed-1','type':'function','function':{'name':name,'arguments':arguments}}]}


class Response(io.BytesIO):
    def __init__(self, data, content_type='text/event-stream'):
        super().__init__(data)
        self.headers=Message()
        self.headers['Content-Type']=content_type


class ToolArgumentTests(LocalCase):
    def stream(self, message):
        calls=[{'index':i,**c} for i,c in enumerate(message.get('tool_calls',[]))]
        return (chunk({'tool_calls':calls})+chunk(finish='tool_calls')+
                chunk(usage={'prompt_tokens':10,'completion_tokens':5,'cost':0})+b'data: [DONE]\n\n')

    def provider(self):
        return ChatProvider({'base_url':'http://127.0.0.1:11434/v1','model':'fixture','key_env':'CHEAPOS_TEST_KEY'})

    def test_streamed_worker_and_reviewer_arguments_can_be_corrected_before_execution(self):
        task=self.fixture(paid=True)
        task['providers']['reviewer']['model']='test-reviewer'
        task.update(conversational=True,action_pending=True,loop_guidance='Finish the requested edit.')
        self.engine.store.save(task)
        replies=iter([
            malformed(), malformed(), malformed(),
            call('read_file',{'path':'math_utils.py'}),
            call('replace_lines',{'path':'math_utils.py','start_line':2,'end_line':2,'new_text':'    return max(lower, min(value, upper))'}),
            call('checkpoint',{'summary':'Fixed both bounds','uncertainties':''}),
            malformed('review_decision','{"decision":"APPROVE","feedback":"checked"'),
            call('review_decision',{'decision':'APPROVE','feedback':'Both bounds are correct.'}),
        ])
        requests=[]
        def respond(request,**kwargs):
            requests.append(json.loads(request.data))
            if len(requests)==2:
                self.assertFalse((Path(task['workspace'])/'unsafe.txt').exists())
                self.assertIn('return min(value, upper)',(Path(task['workspace'])/'math_utils.py').read_text())
            return Response(self.stream(next(replies)))
        self.engine.provider_factory=lambda role,config:ChatProvider({**self.provider().config,'model':config['model']})
        with patch('cheapos.providers.build_opener') as opener:
            opener.return_value.open.side_effect=respond
            self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'approved',result['error'])
        self.assertEqual(len(requests),8)
        self.assertFalse((Path(task['workspace'])/'unsafe.txt').exists())
        self.assertEqual(result['usage']['uncertain_requests'],0)
        self.assertEqual(result['usage']['worker']['tokens'],90)
        self.assertEqual(result['usage']['reviewer']['tokens'],30)
        errors=[e for e in result['events'] if e['kind']=='tool_error']
        self.assertEqual([e['detail']['tool'] for e in errors],['write_file','write_file','write_file','review_decision'])
        self.assertIn('invalid_tool_arguments',json.dumps(requests[1]['messages']))
        self.assertIn('replace_lines',{t['function']['name'] for t in requests[1]['tools']})
        for index in (7,):
            feedback=requests[index]['messages'][-1]
            if index==1:  # Action recovery adds controller guidance after feedback.
                feedback=next(m for m in reversed(requests[index]['messages']) if m['role']=='tool')
            self.assertEqual(feedback['tool_call_id'],'malformed-1')
            self.assertEqual(json.loads(feedback['content'])['code'],'invalid_tool_arguments')

    def test_pinned_malformed_calls_try_distinct_format_strategy_before_prerequisite(self):
        task=self.fixture(paid=True);task['conversational']=True;self.engine.store.save(task)
        self.engine.provider_factory=lambda *args:self.provider()
        with patch('cheapos.providers.build_opener') as opener:
            opener.return_value.open.side_effect=lambda *args,**kwargs:Response(self.stream(malformed()))
            self.engine.start(task['id']);result=self.finish(task)
            self.assertEqual(opener.return_value.open.call_count,6)
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['error_code'],'progress_limit')
        self.assertIn('pinned model',result['error'])
        self.assertEqual(result['changes'],[])
        self.assertEqual(result['request_worker_turns'],6)
        self.assertEqual(result['usage']['worker']['tokens'],90)

    def test_argument_repair_cannot_extend_worker_allowance(self):
        task=self.fixture(paid=True);task.update(conversational=True)
        task['limits']['worker_turns']=1;self.engine.store.save(task)
        self.engine.provider_factory=lambda *args:self.provider()
        with patch('cheapos.providers.build_opener') as opener:
            opener.return_value.open.side_effect=lambda *args,**kwargs:Response(self.stream(malformed()))
            self.engine.start(task['id']);result=self.finish(task)
            self.assertEqual(opener.return_value.open.call_count,1)
        self.assertEqual(result['error_code'],'worker_turn_limit')
        self.assertEqual(result['changes'],[])

    def test_malformed_stream_and_response_json_are_distinct_and_not_retried(self):
        for body,kind,expected in [(b'data: {broken\n\n','text/event-stream','invalid_stream_json'),(b'{broken','application/json','invalid_response_json')]:
            with self.subTest(kind=kind),patch('cheapos.providers.build_opener') as opener:
                opener.return_value.open.return_value=Response(body,kind)
                with self.assertRaises(ProviderError) as caught:
                    self.provider().complete_with_progress([],[],128,lambda *args:None,lambda:False)
                self.assertEqual(caught.exception.code,expected)
                self.assertIn('line 1, column',str(caught.exception))
                self.assertNotIn('{broken',str(caught.exception))
                opener.return_value.open.assert_called_once()

    def test_empty_arguments_are_normalized_only_for_default_read_tools(self):
        for name in ('list_files', 'get_diff'):
            with self.subTest(name=name):
                self.assertEqual(Engine.parse_call(malformed(name=name, arguments='')['tool_calls'][0]), (name, {}))
            for arguments in (' ', '\n', None, '[]', 'null', '{'):
                with self.subTest(name=name, arguments=arguments), self.assertRaises(ToolArgumentsError):
                    Engine.parse_call(malformed(name=name, arguments=arguments)['tool_calls'][0])
        for name in ('write_file', 'run_checks', 'read_file', 'checkpoint', 'unknown_tool'):
            with self.subTest(name=name), self.assertRaises(ToolArgumentsError):
                Engine.parse_call(malformed(name=name, arguments='')['tool_calls'][0])
        call = malformed(name='get_diff', arguments='')['tool_calls'][0]
        call['id'] = ''
        with self.assertRaises(ProviderError) as caught:
            Engine.parse_call(call)
        self.assertEqual(caught.exception.code, 'invalid_tool_envelope')

    def test_argument_shape_errors_are_repairable_but_missing_identity_is_not(self):
        for args in ('[]','null','"text"','',None):
            with self.subTest(args=args),self.assertRaises(ToolArgumentsError):
                Engine.parse_call(malformed(arguments=args)['tool_calls'][0])
        for c in ({}, {'id':'','function':{'name':'write_file','arguments':'{}'}}, {'id':'id','function':None}):
            with self.subTest(call=c),self.assertRaises(ProviderError) as caught:
                Engine.parse_call(c)
            self.assertEqual(caught.exception.code,'invalid_tool_envelope')

    def test_extract_fallback_tool_calls_xml_and_json(self):
        # Dots format
        dots_xml = ('<dots_function_call>\n'
                    '<invoke name="read_file">\n'
                    '<parameter name="path">cheapos/role_mappings.py</parameter>\n'
                    '</invoke>\n'
                    '</dots_function_call>')
        calls, cleaned = extract_fallback_tool_calls(dots_xml, {'read_file', 'write_file'})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['function']['name'], 'read_file')
        self.assertEqual(json.loads(calls[0]['function']['arguments']), {'path': 'cheapos/role_mappings.py'})
        self.assertIsNone(cleaned)

        # XML with surrounding text
        text_with_invoke = ('I will inspect this file.\n'
                            '<invoke name="read_file">\n'
                            '<parameter name="path">foo.py</parameter>\n'
                            '</invoke>')
        calls, cleaned = extract_fallback_tool_calls(text_with_invoke, {'read_file'})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['function']['name'], 'read_file')
        self.assertEqual(cleaned, 'I will inspect this file.')

        # Tool call JSON tag
        tool_call_tag = '<tool_call>{"name": "read_file", "arguments": {"path": "bar.py"}}</tool_call>'
        calls, cleaned = extract_fallback_tool_calls(tool_call_tag, {'read_file'})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['function']['name'], 'read_file')
        self.assertEqual(json.loads(calls[0]['function']['arguments']), {'path': 'bar.py'})

        # Unoffered tool is not extracted
        calls, cleaned = extract_fallback_tool_calls(dots_xml, {'other_tool'})
        self.assertEqual(calls, [])

    def test_strip_leaked_actions_xml_and_json(self):
        dots_xml = ('Some explanation.\n<dots_function_call>\n<invoke name="read_file">\n'
                    '<parameter name="path">test.py</parameter>\n</invoke>\n</dots_function_call>')
        self.assertEqual(strip_leaked_actions(dots_xml), 'Some explanation.')
        json_call = '```json\n{"action": "read_file", "path": "test.py"}\n```'
        self.assertEqual(strip_leaked_actions(json_call), '')
