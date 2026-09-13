"""Completed tool responses can repair bad argument JSON without executing it."""
import io
import json
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from cheapos.engine import Engine, ToolArgumentsError
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
        task.update(conversational=True,action_pending=True,loop_guidance='Finish the requested edit.')
        self.engine.store.save(task)
        replies=iter([
            malformed(),
            call('replace_text',{'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}),
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
        self.engine.provider_factory=lambda *args:self.provider()
        with patch('cheapos.providers.build_opener') as opener:
            opener.return_value.open.side_effect=respond
            self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'approved',result['error'])
        self.assertEqual(len(requests),5)
        self.assertFalse((Path(task['workspace'])/'unsafe.txt').exists())
        self.assertEqual(result['usage']['uncertain_requests'],0)
        self.assertEqual(result['usage']['worker']['tokens'],45)
        self.assertEqual(result['usage']['reviewer']['tokens'],30)
        errors=[e for e in result['events'] if e['kind']=='tool_error']
        self.assertEqual([e['detail']['tool'] for e in errors],['write_file','review_decision'])
        for index in (1,4):
            feedback=requests[index]['messages'][-1]
            if index==1:  # Action recovery adds controller guidance after feedback.
                feedback=next(m for m in reversed(requests[index]['messages']) if m['role']=='tool')
            self.assertEqual(feedback['tool_call_id'],'malformed-1')
            self.assertEqual(json.loads(feedback['content'])['code'],'invalid_tool_arguments')

    def test_three_malformed_calls_pause_without_executing_or_unbounded_requests(self):
        task=self.fixture(paid=True);task['conversational']=True;self.engine.store.save(task)
        self.engine.provider_factory=lambda *args:self.provider()
        with patch('cheapos.providers.build_opener') as opener:
            opener.return_value.open.side_effect=lambda *args,**kwargs:Response(self.stream(malformed()))
            self.engine.start(task['id']);result=self.finish(task)
            self.assertEqual(opener.return_value.open.call_count,3)
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['error_code'],'progress_limit')
        self.assertIn('three times',result['error'])
        self.assertEqual(result['changes'],[])
        self.assertEqual(result['request_worker_turns'],3)
        self.assertEqual(result['usage']['worker']['tokens'],45)

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

    def test_argument_shape_errors_are_repairable_but_missing_identity_is_not(self):
        for args in ('[]','null','"text"','',None):
            with self.subTest(args=args),self.assertRaises(ToolArgumentsError):
                Engine.parse_call(malformed(arguments=args)['tool_calls'][0])
        for c in ({}, {'id':'','function':{'name':'write_file','arguments':'{}'}}, {'id':'id','function':None}):
            with self.subTest(call=c),self.assertRaises(ProviderError) as caught:
                Engine.parse_call(c)
            self.assertEqual(caught.exception.code,'invalid_tool_envelope')
