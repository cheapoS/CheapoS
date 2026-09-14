"""Deterministic brief transport guards: no sockets, sleeps or live inference."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from contextlib import nullcontext
from cheapos.providers import BriefResponseGuard, ChatProvider, ProviderError, reserve, reconcile


class BriefTransportTests(unittest.TestCase):
    def test_cancel_shuts_socket_before_close_and_joins_active_guard(self):
        actions=[];stopped=[False]
        sock=SimpleNamespace(shutdown=lambda _:actions.append('shutdown'))
        response=SimpleNamespace(fp=SimpleNamespace(raw=SimpleNamespace(_sock=sock)),close=lambda:actions.append('close'))
        thread=Mock()
        with patch('cheapos.providers.threading.Thread',return_value=thread):
            guard=BriefResponseGuard(response,lambda:stopped[0],30,clock=lambda:0)
            with self.assertRaises(InterruptedError):
                with guard:
                    # A blocked-read test double observes socket shutdown; no real wait.
                    stopped[0]=True;guard.poll()
                    raise OSError('read released by shutdown')
        self.assertEqual(actions,['shutdown','close'])
        thread.start.assert_called_once();thread.join.assert_called_once()
        self.assertTrue(guard.done.is_set())
        guard.poll();self.assertEqual(actions,['shutdown','close'])

    def test_deadline_closes_response_without_polling_after_completion(self):
        clock=[0];response=Mock();thread=Mock()
        with patch('cheapos.providers.threading.Thread',return_value=thread):
            guard=BriefResponseGuard(response,lambda:False,60,clock=lambda:clock[0])
            with self.assertRaises(ProviderError) as failure:
                with guard:clock[0]=60;guard.poll()
        self.assertEqual(failure.exception.code,'model_timeout')
        response.close.assert_called_once();thread.join.assert_called_once()
        response=Mock()
        with patch('cheapos.providers.threading.Thread',return_value=Mock()):
            with BriefResponseGuard(response,lambda:False,30,clock=lambda:0) as success:pass
        success.poll();response.close.assert_not_called()

    def test_recovery_gets_512_tokens_but_greeting_remains_128(self):
        cfg={'model':'local','base_url':'http://127.0.0.1:11434/v1','input_rate':0,'output_rate':0}
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.return_value=json.dumps({'choices':[{'message':{'content':'reply'}}],'usage':{'prompt_tokens':1,'completion_tokens':1}}).encode()
        opener=Mock();opener.open.return_value=response
        with patch('cheapos.providers.build_opener',return_value=opener),patch('cheapos.providers.BriefResponseGuard',return_value=nullcontext()) as guard:
            ChatProvider(dict(cfg,_coordinator_recovery=True)).complete_brief([],[],512,None,lambda:False)
            body=json.loads(opener.open.call_args.args[0].data);self.assertEqual(body['max_tokens'],512)
            self.assertEqual(opener.open.call_args.kwargs['timeout'],30)
            self.assertEqual(guard.call_args.args[2],30)
            ChatProvider(cfg).greet([],None,lambda:False)
            self.assertEqual(json.loads(opener.open.call_args.args[0].data)['max_tokens'],128)

    def test_new_coordinator_bucket_preserves_existing_accounting(self):
        task={'limits':{'output_tokens':512,'dollars':1},'usage':{'worker':{'tokens':7,'cost':.2},'reviewer':{'tokens':9,'cost':.1},'cost':.3,'uncertain_requests':0,'estimated_requests':0}}
        cfg={'input_rate':0,'output_rate':0}
        reservation=reserve(task,cfg,[],[],'coordinator')
        reconcile(task,cfg,reservation,{'prompt_tokens':20,'completion_tokens':30,'cost':0})
        self.assertEqual(task['usage']['coordinator'],{'tokens':50,'cost':0})
        self.assertEqual(task['usage']['worker'],{'tokens':7,'cost':.2})
        self.assertEqual(task['usage']['cost'],.3)
