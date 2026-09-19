import io
import json
import threading
import time
import unittest
from contextlib import nullcontext
from email.message import Message
from unittest.mock import patch
from urllib.error import URLError

from cheapos.providers import ChatProvider, ProviderError
from cheapos.streaming import read_chat_stream, normalize_reasoning
from test_engine import LocalCase, call


def chunk(delta=None, finish=None, usage=None):
    value={'choices':[{'index':0,'delta':delta or {},'finish_reason':finish}]}
    if usage is not None:value['usage']=usage
    return ('data: '+json.dumps(value)+'\n\n').encode()


class InlineThinkingTests(unittest.TestCase):
    def test_streamed_tags_never_enter_answer_at_any_split_boundary(self):
        text=' \n<think>Consider the greeting.\n</think>\n\nHello!'
        fragments=[[text[:i], text[i:]] for i in range(1, len(text))] + [list(text)]
        for pieces in fragments:
            seen=[]
            data=b''.join(chunk({'content':piece}) for piece in pieces)
            data+=chunk(finish='stop', usage={'prompt_tokens':12, 'completion_tokens':7})+b'data: [DONE]\n\n'
            result=read_chat_stream(io.BytesIO(data), lambda *part:seen.append(part), lambda:False, ProviderError)
            message=result['choices'][0]['message']
            self.assertEqual(message['content'], 'Hello!')
            self.assertEqual(message['reasoning'], 'Consider the greeting.\n')
            self.assertEqual(''.join(text for kind,text in seen if kind=='answer'), 'Hello!')
            self.assertEqual(''.join(text for kind,text in seen if kind=='thinking'), message['reasoning'])
            self.assertEqual(result['usage'], {'prompt_tokens':12, 'completion_tokens':7})

    def test_normal_answers_and_code_examples_are_preserved(self):
        for text in ('Hello!', '  Hello!', '<thread>example</thread>', '<',
                     'Use <think> for the example.', '```xml\n<think>literal</think>\n```',
                     '`<think>literal</think>`'):
            with self.subTest(text=text):
                self.assertEqual(normalize_reasoning({'content':text}), {'content':text})
                seen=[]
                data=b''.join(chunk({'content':c}) for c in text)+chunk(finish='stop')+b'data: [DONE]\n\n'
                message=read_chat_stream(io.BytesIO(data),lambda kind,text:seen.append((kind,text)),lambda:False,ProviderError)['choices'][0]['message']
                self.assertEqual(message['content'], text)
                self.assertNotIn('reasoning', message)
                self.assertEqual(''.join(text for kind,text in seen if kind=='answer'), text)

    def test_complete_replies_preserve_structured_reasoning_tools_and_details(self):
        tools=[call('read_file', {'path':'README.md'})]
        original={'content':'<THINKING>Inline thought</THINKING>\nAnswer', 'reasoning_content':'Structured thought',
                  'tool_calls':tools, 'reasoning_details':[{'type':'fixture'}]}
        result=normalize_reasoning(original)
        self.assertEqual(result['content'], 'Answer')
        self.assertEqual(result['reasoning'], 'Structured thought\n\nInline thought')
        self.assertEqual(result['tool_calls'], tools)
        self.assertEqual(result['reasoning_details'], original['reasoning_details'])
        self.assertTrue(original['content'].startswith('<THINKING>'))

    def test_provider_json_and_sse_keep_thinking_out_of_the_answer(self):
        for streaming in (False, True):
            for content, answer, fallback in (
                ('<think>Consider greeting</think>\nHello!', 'Hello!', False),
                ('<think>Consider greeting', 'Consider greeting', True),
                ('<think>Consider greeting</think>', 'Consider greeting', True),
                ('<think>First</think><think>literal answer</think>', '<think>literal answer</think>', False),
            ):
                with self.subTest(streaming=streaming, content=content):
                    data=(chunk({'content':content})+chunk(finish='stop',usage={'completion_tokens':7})+b'data: [DONE]\n\n'
                          if streaming else json.dumps({'choices':[{'message':{'content':content}}], 'usage':{'completion_tokens':7}}).encode())
                    response=io.BytesIO(data)
                    response.headers=Message()
                    response.headers['Content-Type']='text/event-stream' if streaming else 'application/json'
                    provider=ChatProvider({'base_url':'http://127.0.0.1:11434/v1', 'model':'fixture'})
                    seen=[]
                    with patch('cheapos.providers.build_opener') as opener, patch('cheapos.providers.pacer.throttle', return_value=nullcontext()):
                        opener.return_value.open.return_value=response
                        if streaming:
                            result,usage=provider.complete_with_progress([],[],128,lambda *part:seen.append(part),lambda:False)
                        else:
                            result,usage=provider.complete([],[],128)
                    self.assertEqual(result['content'], answer)
                    self.assertEqual(bool(result.get('reasoning_fallback')), fallback)
                    self.assertEqual(usage['completion_tokens'], 7)
                    if fallback:
                        self.assertFalse(any(kind=='answer' for kind,_ in seen))


class StreamingTests(LocalCase):
    def parse(self, data, emit=lambda *args:None, stopped=lambda:False):
        return read_chat_stream(io.BytesIO(data),emit,stopped,ProviderError)

    def test_thinking_answer_split_tools_and_usage_are_assembled(self):
        data=chunk({'reasoning':'Let me inspect '})+chunk({'reasoning':'the file.'})+chunk({'content':'Reading it now.'})
        data+=chunk({'tool_calls':[{'index':0,'id':'read-1','function':{'name':'read_file','arguments':'{"path":'}}]})
        data+=chunk({'tool_calls':[{'index':0,'function':{'arguments':'"README.md"}'}}]})
        data+=chunk(finish='tool_calls')+chunk(usage={'prompt_tokens':10,'completion_tokens':20})+b'data: [DONE]\n\n'
        seen=[]
        result=self.parse(data,lambda kind,text:seen.append((kind,text)))
        self.assertEqual(result['_wire_bytes'],len(data)-1)  # Read through DONE; trailing blank remains unread.
        message=result['choices'][0]['message']
        self.assertEqual(message['reasoning'],'Let me inspect the file.')
        self.assertEqual(message['content'],'Reading it now.')
        self.assertEqual(json.loads(message['tool_calls'][0]['function']['arguments']),{'path':'README.md'})
        self.assertEqual(result['usage']['completion_tokens'],20)
        self.assertEqual(seen[0],('thinking','Let me inspect '))
        self.assertTrue(any(kind=='answer' for kind,text in seen))

    def test_incomplete_or_truncated_stream_never_returns_tools(self):
        tool=chunk({'tool_calls':[{'index':0,'id':'edit','function':{'name':'write_file','arguments':'{"path":"unsafe.py","content":"x"}'}}]})
        for suffix in [b'',chunk(finish='stop'),chunk(finish='length')+b'data: [DONE]\n\n']:
            with self.assertRaises(ProviderError):self.parse(tool+suffix)

    def test_output_limit_retains_final_usage_without_returning_partial_calls(self):
        partial=chunk({'tool_calls':[{'index':0,'id':'edit','function':{'name':'write_file','arguments':'{"path":"unsafe.py"'}}]})
        usage={'prompt_tokens':12,'completion_tokens':4096,'cost':.02}
        with self.assertRaises(ProviderError) as caught:
            self.parse(partial+chunk(finish='length')+chunk(usage=usage)+b'data: [DONE]\n\n')
        self.assertEqual(caught.exception.code,'output_limit')
        self.assertEqual(caught.exception.usage,usage)

    def test_unsuccessful_finish_reason_is_visible_and_partial_tools_never_return(self):
        tool=chunk({'tool_calls':[{'index':0,'id':'edit','function':{'name':'write_file','arguments':'{"path":"unsafe.py","content":"x"}'}}]})
        for reason,label in [('error','error'),('content_filter','content_filter'),('unknown_native_reason','unknown_native_reason'),('unsafe\nvalue','unrecognized'),({'invalid':'shape'},'unrecognized')]:
            with self.subTest(reason=reason),self.assertRaises(ProviderError) as caught:
                self.parse(tool+chunk(finish=reason)+b'data: [DONE]\n\n')
            self.assertEqual(caught.exception.code,'stream_error' if reason=='error' else 'model_refusal')
            self.assertIn('finish_reason='+label,str(caught.exception))
            self.assertIn('Partial tool calls were not executed',str(caught.exception))

    def test_stream_cancellation_stops_before_completion(self):
        stopped=threading.Event()
        def emit(kind,text):stopped.set()
        with self.assertRaises(InterruptedError):
            self.parse(chunk({'reasoning':'Waiting'})+chunk({'content':'Should not appear'})+chunk(finish='stop')+b'data: [DONE]\n\n',emit,stopped.is_set)

    def test_missing_usage_is_not_fabricated(self):
        result=self.parse(chunk({'content':'Hello'})+chunk(finish='stop')+b'data: [DONE]\n\n')
        self.assertEqual(result['usage'],{})

    def test_daily_quota_stream_error_is_provider_wide_without_raw_details(self):
        for failure in ({'code':429,'message':'Rate limit exceeded: free-models-per-day-high-balance. secret-account'}, '[429]: Rate limit exceeded: free-models-per-day-high-balance.'):
            data=('data: '+json.dumps({'error':failure})+'\n\n').encode()
            with self.assertRaises(ProviderError) as caught:self.parse(data)
            self.assertEqual(caught.exception.code,'gateway_cooldown')
            self.assertEqual(caught.exception.scope,'provider')
            self.assertIsNone(caught.exception.retry_after)
            self.assertIn('daily free-model quota',str(caught.exception))
            self.assertNotIn('secret-account',str(caught.exception))

    def test_structured_rate_limit_is_model_scoped_and_never_returns_partial_tools(self):
        partial=chunk({'tool_calls':[{'index':0,'id':'edit','function':{'name':'write_file','arguments':'{"path":"unsafe.py"'}}]})
        for failure in ({'type':'rate_limit_error','message':'secret-account'}, {'code':'rate_limit_exceeded','message':'secret-account'}):
            with self.subTest(failure=failure),self.assertRaises(ProviderError) as caught:
                self.parse(partial+('data: '+json.dumps({'error':failure})+'\n\n').encode())
            self.assertEqual(caught.exception.code,'gateway_cooldown')
            self.assertEqual(caught.exception.scope,'model')
            self.assertIsNone(caught.exception.retry_after)
            self.assertIn('Partial tool calls were not executed',str(caught.exception))
            self.assertNotIn('secret-account',str(caught.exception))
        with self.assertRaises(ProviderError) as caught:
            self.parse(b'data: {"error":{"type":"server_error","code":"unknown","message":"secret-account"}}\n\n')
        self.assertEqual(caught.exception.code,'stream_error')

    def test_timeout_and_connection_errors_have_distinct_codes(self):
        provider=ChatProvider({'base_url':'http://127.0.0.1:11434/v1','model':'fixture','key_env':'CHEAPOS_TEST_KEY'})
        for error,code in [(TimeoutError(),'model_timeout'),(URLError(TimeoutError()),'model_timeout'),(URLError(ConnectionRefusedError()),'model_connection')]:
            with patch('cheapos.providers.build_opener') as opener:
                opener.return_value.open.side_effect=error
                with self.assertRaises(ProviderError) as caught:provider.complete([],[],128)
                self.assertEqual(caught.exception.code,code)
                self.assertEqual(opener.return_value.open.call_count,1)

    def test_engine_publishes_thinking_before_return_and_keeps_it_out_of_reviewer_context(self):
        task=self.fixture(paid=True)
        task['conversational']=True
        self.engine.store.save(task)
        release=threading.Event()
        emitted=threading.Event()
        class StreamingProvider:
            streams_output=True
            def complete_with_progress(self,messages,tools,maximum,emit,stopped):
                emit('thinking','I will answer the question without editing.')
                emitted.set()
                release.wait(15)
                emit('answer','Ready.')
                return {'role':'assistant','content':'Ready.'},{'prompt_tokens':10,'completion_tokens':10,'cost':0}
        self.engine.provider_factory=lambda *args:StreamingProvider()
        self.engine.start(task['id'])
        try:
            self.assertTrue(emitted.wait(10), self.engine.store.get(task['id']).get('error'))
            live=self.engine.store.get(task['id'])
            self.assertEqual(live['status'],'running')
            self.assertIn('without editing',live['stream']['thinking'])
            self.assertEqual(live['changes'],[])
        finally:
            release.set()
        result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertIsNone(result['stream'])
        thinking=[e for e in result['events'] if e['kind']=='generation']
        self.assertEqual(len(thinking),1)
        self.assertFalse(thinking[0]['detail']['interrupted'])
        self.assertNotIn('without editing',json.dumps(self.engine.initial_messages(result)))
        self.assertEqual(result['usage']['uncertain_requests'],0)

    def test_interrupted_stream_preserves_preview_but_does_not_execute_an_edit(self):
        task=self.fixture(paid=True)
        class StreamingProvider:
            streams_output=True
            def complete_with_progress(self,messages,tools,maximum,emit,stopped):
                emit('thinking','Preparing an edit.')
                emit('answer','A partial answer')
                raise ProviderError('Stream interrupted',code='stream_interrupted')
        self.engine.provider_factory=lambda *args:StreamingProvider()
        self.engine.start(task['id'])
        result=self.finish(task)
        self.assertEqual(result['status'],'error')
        self.assertEqual(result['error_code'],'stream_interrupted')
        self.assertEqual(result['changes'],[])
        self.assertEqual(result['usage']['uncertain_requests'],1)
        generation=next(e for e in result['events'] if e['kind']=='generation')
        self.assertTrue(generation['detail']['interrupted'])
        self.assertEqual(generation['detail']['content'],'A partial answer')

    def test_stop_is_visible_while_provider_is_pending(self):
        task=self.fixture(paid=True)
        release=threading.Event();entered=threading.Event()
        class Provider:
            def complete(self,*args):
                entered.set()
                release.wait(5)
                return call('write_file',{'path':'should-not-exist.py','content':'no'}),{'prompt_tokens':10,'completion_tokens':10,'cost':0}
        self.engine.provider_factory=lambda *args:Provider()
        self.engine.start(task['id'])
        self.assertTrue(entered.wait(5))
        self.engine.stop(task['id'])
        self.assertEqual(self.engine.store.get(task['id'])['status'],'stopping')
        release.set()
        result=self.finish(task)
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['changes'],[])
