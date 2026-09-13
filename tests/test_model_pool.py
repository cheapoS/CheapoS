"""Automatic free recovery preserves work, accounting, and human control."""
import copy
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cheapos.engine import Engine
from cheapos.model_pool import FreeModelPool
from cheapos.omniroute import OmniRouteManager
from cheapos.providers import ProviderError
from cheapos.routing import PROBE_MESSAGES
from test_engine import LocalCase, call
import test_routing as routing_fixture
from test_routing import model


class PoolTests(unittest.TestCase):
    def test_cooldowns_survive_restart_expire_and_remain_endpoint_scoped(self):
        with tempfile.TemporaryDirectory() as directory, patch('cheapos.model_pool.time.time', return_value=1000):
            pool=FreeModelPool(directory)
            pool.record('http://localhost:20128/v1','a','worker',error='Broken stream')
            pool=FreeModelPool(directory)
            self.assertTrue(pool.observation('http://127.0.0.1:20128/v1','a')['cooling_down'])
            self.assertFalse(pool.observation('http://127.0.0.1:2222/v1','a')['cooling_down'])
            with patch('cheapos.model_pool.time.time',return_value=1901):
                self.assertFalse(pool.observation('http://localhost:20128/v1','a')['cooling_down'])
            pool.record('http://localhost:20128/v1','a','worker',probe=True)
            self.assertFalse(pool.observation('http://localhost:20128/v1','a')['cooling_down'])

    def test_selection_uses_role_observations_then_metadata_without_size_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            pool=FreeModelPool(directory);endpoint='http://localhost:20128/v1'
            models=[model('a-mini-8b',reasoning=False),model('z-550b',reasoning=True)]
            self.assertEqual(sorted(models,key=lambda m:pool.rank(endpoint,m,'reviewer'))[0]['id'],'z-550b')
            pool.record(endpoint,'a-mini-8b','reviewer',seconds=1)
            self.assertEqual(sorted(models,key=lambda m:pool.rank(endpoint,m,'reviewer'))[0]['id'],'a-mini-8b')

    def test_stale_catalog_replaces_removed_models_and_does_not_serve_stale_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            manager=OmniRouteManager(directory)
            try:
                manager.models=[model('removed')];manager.state='ready';manager.checked_at=time.monotonic()-400
                manager._probe=Mock(return_value=[model('new')])
                self.assertEqual([m['id'] for m in manager.catalog(fresh=True)['models']],['new'])
                self.assertEqual(manager._probe.call_count,1)
                manager.catalog(fresh=True)
                self.assertEqual(manager._probe.call_count,1)
                manager.checked_at=time.monotonic()-400
                manager._probe.side_effect=ProviderError('Unavailable');manager._port_open=Mock(return_value=True)
                self.assertEqual(manager.catalog(fresh=True)['models'],[])
            finally: manager.shutdown()


class FailoverTests(LocalCase):
    chat=routing_fixture.RoutingTests.chat

    def responding(self, replies, names=('a','b','c','d')):
        self.engine.gateway.catalog.return_value['models']=[model(n) for n in names]
        queue=iter(replies);requests=[]
        class Provider:
            def __init__(self,role,cfg):self.role,self.cfg=role,cfg
            def complete(self,messages,tools,maximum):
                requests.append({'role':self.role,'model':self.cfg['model'],'messages':copy.deepcopy(messages),'tools':copy.deepcopy(tools)})
                if messages==PROBE_MESSAGES:return call('routing_ready'),{'prompt_tokens':3,'completion_tokens':1,'cost':0}
                reply=next(queue)
                if isinstance(reply,Exception):raise reply
                return reply,{'prompt_tokens':10,'completion_tokens':5,'cost':0}
        self.engine.provider_factory=lambda role,cfg:Provider(role,cfg)
        return requests

    def test_worker_and_reviewer_handoffs_preserve_patch_checks_and_context(self):
        task=self.chat('remote')
        task['check_command']=[sys.executable,'-m','unittest','discover','-v'];task['auto_approve_checks']=True
        self.engine.store.save(task)
        edit=call('replace_text',{'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'})
        requests=self.responding([edit,ProviderError('Worker stream broke',code='stream_error'),
            call('checkpoint',{'summary':'Fixed clamp.'}),ProviderError('Reviewer stream broke',code='invalid_response_json'),
            call('review_decision',{'decision':'APPROVE','feedback':'Verified.'})])
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'approved',result['error'])
        self.assertEqual(result['providers']['worker']['model'],'b')
        self.assertEqual(result['providers']['reviewer']['model'],'d')
        self.assertEqual(len(result['checks']),1);self.assertEqual(result['iterations'],1)
        self.assertEqual(result['usage']['uncertain_requests'],2)
        self.assertEqual(result['usage']['cost'],0);self.assertEqual(result['limits'],task['limits'])
        self.assertNotIn('pending_checkpoint',result);self.assertNotIn('pending_review',result)
        self.assertEqual(sum(e['kind']=='tool' and e['title']=='replace text' for e in result['events']),1)
        actual=[r for r in requests if r['messages']!=PROBE_MESSAGES]
        self.assertEqual([r['model'] for r in actual],['a','a','b','c','d'])
        self.assertEqual(actual[1]['messages'],actual[2]['messages'])
        self.assertEqual(actual[3]['messages'],actual[4]['messages'])
        self.assertIn('return min(value, upper)',(Path(task['source'])/'math_utils.py').read_text())

    def test_two_handoffs_then_pause_and_resume_skips_cooling_models(self):
        task=self.chat('remote')
        requests=self.responding([ProviderError('Broken',code='stream_error') for _ in range(3)])
        self.engine.start(task['id']);paused=self.finish(task)
        self.assertEqual(paused['status'],'paused');self.assertEqual(paused['error_code'],'routing_unavailable')
        self.assertEqual(len([r for r in requests if r['messages']!=PROBE_MESSAGES]),3)
        self.assertEqual(paused['usage']['uncertain_requests'],3)
        requests=self.responding([{'content':'Recovered.'}])
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply',result['error'])
        self.assertEqual({r['model'] for r in requests},{'d'})
        self.assertEqual(result['usage']['uncertain_requests'],3)

    def test_worker_turn_cap_stops_before_replacement_probe(self):
        task=self.chat('remote');task['limits']['worker_turns']=1;self.engine.store.save(task)
        requests=self.responding([ProviderError('Broken',code='stream_error')])
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'budget_paused');self.assertEqual(result['error_code'],'worker_turn_limit')
        self.assertEqual({r['model'] for r in requests},{'a'});self.assertEqual(result['worker_turns'],1)

    def test_auth_output_limits_and_refusals_do_not_trigger_handoffs(self):
        for code in ['http_401','http_402','http_403','output_limit','model_refusal']:
            with self.subTest(code=code):
                task=self.chat('remote');requests=self.responding([ProviderError('Stopped',code=code)])
                self.engine.start(task['id']);result=self.finish(task)
                self.assertEqual(result['status'],'error');self.assertEqual(result['error_code'],code)
                self.assertEqual({r['model'] for r in requests},{'a'})

    def test_repriced_or_removed_pinned_model_is_not_dispatched_on_followup(self):
        task=self.chat('remote');self.responding([{'content':'Hi'}]);self.engine.start(task['id']);self.finish(task)
        requests=self.responding([{'content':'Switched'}])
        self.engine.gateway.catalog.return_value['models']=[model('a',free=False),model('b')]
        self.engine.start(task['id'],{'message':'Continue'});result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply',result['error'])
        self.assertEqual({r['model'] for r in requests},{'b'})

    def test_existing_failed_automatic_chat_switches_on_explicit_resume(self):
        task=self.chat('remote');self.responding([{'content':'Hi'}]);self.engine.start(task['id']);task=self.finish(task)
        task.update(status='error',error_code='stream_error',error='Old failed request')
        self.engine.store.save(task)
        requests=self.responding([{'content':'Recovered'}]);self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply',result['error'])
        self.assertEqual({r['model'] for r in requests},{'b'})

    def test_failed_review_resumes_only_review_without_repeating_checks_or_edits(self):
        task=self.chat('remote');task['check_command']=[sys.executable,'-m','unittest','discover','-v'];task['auto_approve_checks']=True
        self.engine.store.save(task)
        self.responding([call('replace_text',{'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}),
            call('checkpoint',{'summary':'Fixed'}),ProviderError('Broken',code='stream_error')],names=('a','b'))
        self.engine.start(task['id']);paused=self.finish(task)
        self.assertEqual(paused['status'],'paused',paused['error']);self.assertTrue(paused['pending_review'])
        self.engine=Engine(self.engine.store.root)
        self.engine.gateway.catalog=Mock(return_value={'status':'ready','models':[]})
        self.engine.gateway.snapshot=Mock(return_value={'status':'ready','busy':False})
        requests=self.responding([call('review_decision',{'decision':'APPROVE','feedback':'Verified'})],names=('a','b','c'))
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'approved',result['error'])
        self.assertEqual(result['worker_turns'],paused['worker_turns'])
        self.assertEqual(len(result['checks']),1);self.assertEqual(result['iterations'],1)
        self.assertEqual(len(result['checkpoints']),1);self.assertEqual(result['checkpoints'][0]['decision'],'APPROVE')
        self.assertTrue(all(r['role']=='reviewer' and r['model']=='c' for r in requests))

    def test_manual_and_local_requests_do_not_switch(self):
        for mode in ['manual','local']:
            task=self.fixture(paid=True);task['execution']={'mode':mode}
            self.engine.store.save(task)
            provider=Mock();provider.complete.side_effect=ProviderError('Broken',code='stream_error')
            self.engine.provider_factory=lambda *args:provider
            self.engine.start(task['id']);result=self.finish(task)
            self.assertEqual(result['status'],'error');self.assertEqual(provider.complete.call_count,1)

    def test_reviewer_cannot_be_a_previous_worker_that_authored_edits(self):
        from cheapos.engine import Runtime
        from cheapos.routing import select_remote
        task=self.chat('remote');requests=self.responding([])
        task['events'].append({'kind':'tool','title':'write file','detail':{'model':'a'}})
        select_remote(self.engine,Runtime(task),'reviewer')
        self.assertEqual(task['providers']['reviewer']['model'],'b')
        self.assertEqual({r['model'] for r in requests},{'b'})

    def test_reviewer_eight_turn_cap_includes_failed_response(self):
        task=self.chat('remote');task['check_command']=[sys.executable,'-m','unittest','discover','-v'];task['auto_approve_checks']=True
        self.engine.store.save(task)
        requests=self.responding([call('replace_text',{'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}),
            call('checkpoint',{'summary':'Fixed'}),ProviderError('Broken',code='stream_error')]+[{'content':'Still reviewing'}]*8)
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'budget_paused',result['error'])
        self.assertEqual(len([r for r in requests if r['role']=='reviewer' and r['messages']!=PROBE_MESSAGES]),8)
        self.assertTrue(result['pending_review'])

    def test_user_stop_during_failure_never_dispatches_replacement(self):
        task=self.chat('remote');requests=self.responding([])
        def stop_and_fail(*args):
            self.engine.runtimes[task['id']].stop.set()
            raise ProviderError('Broken while stopping',code='stream_error')
        self.engine.provider_factory=lambda *args:Mock(complete=stop_and_fail)
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'paused')
        self.assertFalse(any(e['kind']=='handoff' for e in result['events']))

    def test_unavailable_read_during_action_recovery_hands_off_without_executing_any_calls(self):
        from cheapos.engine import ACTION_GUIDANCE
        task=self.chat('remote')
        self.engine.file_tool(task,'write_file',{'path':'notes.txt','content':'Saved work'})
        task.update(action_pending=True,loop_guidance=ACTION_GUIDANCE)
        self.engine.store.save(task)
        mixed=call('write_file',{'path':'unwanted.txt','content':'Must not execute'})
        mixed['tool_calls']+=call('read_file',{'path':'notes.txt'})['tool_calls']
        requests=self.responding([mixed,call('replace_text',{'path':'notes.txt','old_text':'Saved work','new_text':'Corrected work'}),call('ask_user',{'question':'Which example next?'})])
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply',result['error'])
        self.assertEqual(result['providers']['worker']['model'],'b')
        self.assertFalse((Path(task['workspace'])/'unwanted.txt').exists())
        self.assertFalse(any(e['kind']=='tool' and e['title']=='read file' for e in result['events']))
        self.assertIn('Corrected work',result['patch'])
        self.assertEqual(result['usage']['uncertain_requests'],0)
        actual=[r for r in requests if r['messages']!=PROBE_MESSAGES]
        self.assertEqual([r['model'] for r in actual],['a','b','b'])
        import json
        evidence=json.loads(actual[1]['messages'][1]['content'])
        self.assertEqual(evidence['current_files'][0]['content'],'Saved work')
        self.assertEqual(result['request_worker_turns'],3)

    def test_legacy_unavailable_read_pause_switches_model_on_resume(self):
        from cheapos.engine import ACTION_GUIDANCE
        task=self.chat('remote');self.responding([{'content':'Hi'}]);self.engine.start(task['id']);task=self.finish(task)
        self.engine.file_tool(task,'write_file',{'path':'notes.txt','content':'Saved work'})
        task.update(status='paused',error_code='progress_limit',action_pending=True,
                    error='The worker tried to repeat inspection after the read loop stopped. Saved edits are intact.',
                    loop_guidance='Old guidance')
        self.engine.store.save(task)
        requests=self.responding([call('ask_user',{'question':'Which example next?'})])
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply',result['error'])
        self.assertEqual({r['model'] for r in requests},{'b'})
        self.assertIn(ACTION_GUIDANCE,[m['content'] for m in requests[-1]['messages']])
