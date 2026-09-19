from cheapos.routing import PROBE_MARKER
"""Placement, tool isolation, free selection, and bounded progress without inference."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from cheapos.engine import Engine, Runtime, ProgressPause
from cheapos.routing import PROBE_MESSAGES, execution_from
from cheapos.providers import ProviderError
from test_engine import LocalCase, call, wait_for


def model(name, **extra):
    return {'id':name, 'free':True, 'local':False, 'tool_calling':True, **extra}


class RoutingTests(LocalCase):
    def test_opening_greeting_skips_probe_but_following_work_still_qualifies(self):
        task = self.chat('remote', prompt='hi there')
        requests = self.responses([{'role': 'assistant', 'content': 'Hi! What would you like to work on?'},
                                   call('ask_user', {'question': 'Which behavior should change?'})])
        self.engine.start(task['id'])
        result = self.finish(task)
        self.assertEqual(result['status'], 'awaiting_reply', result['error'])
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]['tools'], [])
        self.assertNotIn('math_utils.py', json.dumps(requests[0]['messages']))
        self.assertEqual(result['request_metrics'][0]['purpose'], 'chat_reply')
        self.assertEqual(result['usage']['worker']['tokens'], 15)
        self.assertFalse(result['route']['ready'])
        self.assertIsNone(result['providers']['worker'])
        self.assertEqual(result['checks'], [])
        self.assertEqual(result['changes'], [])
        self.engine.start(task['id'], {'message': 'Change clamp behavior.'})
        result = self.finish(task)
        self.assertEqual(result['status'], 'awaiting_reply', result['error'])
        self.assertEqual([r['purpose'] for r in result['request_metrics']], ['chat_reply', 'probe', 'work'])
        self.assertEqual(requests[1]['messages'], PROBE_MESSAGES)
        self.assertTrue(requests[2]['tools'])

    def test_text_chat_prefers_responding_route_and_restores_work_selection(self):
        task = self.chat('remote'); runtime = Runtime(task)
        base = task['route']['base_url']
        policy = task.get('access_policy') or {}
        revision = policy.get('connection_revision')
        self.engine.gateway.pool.record(base, 'b:free', 'worker', seconds=1, connection_revision=revision)
        self.engine.gateway.catalog.return_value['models'].extend([
            model('paid-fast', free=False), model('local-fast', local=True), model('no-tools', tool_calling=False)])
        for name in ('paid-fast', 'local-fast', 'no-tools'):
            self.engine.gateway.pool.record(base, name, 'worker', seconds=.01, connection_revision=revision)
        task['route']['preferred']['worker'] = 'a:free'
        recovery = {'from': 'a:free', 'reason': 'Saved work recovery'}
        task['route']['recovery'] = {'worker': recovery.copy()}
        requests = self.responses([{'content': 'Hello'}])
        self.engine.request(runtime, [{'role': 'user', 'content': 'Hi'}], [], 'worker', purpose='chat_reply')
        self.assertEqual([r['model'] for r in requests], ['b:free'])
        self.assertIsNone(task['providers']['worker'])
        self.assertFalse(task['route']['ready'])
        self.assertEqual(task['route']['recovery']['worker'], recovery)
        self.assertFalse(runtime.text_only_route)
        self.assertFalse(self.engine.gateway.pool.observation(base, 'b:free', revision).get('tool_check_passed'))

    def test_text_reply_respects_explicit_only_model(self):
        from cheapos.providers import validate_provider
        task = self.chat('remote'); runtime = Runtime(task)
        cfg = validate_provider({'base_url': task['route']['base_url'], 'gateway': 'omniroute',
                                 'model': 'a:free', 'input_rate': 0, 'output_rate': 0}, 'worker')
        if task.get('gateway_connections'):
            from cheapos import access_policy
            entry = task['gateway_connections'][0]
            cfg['connection_id'] = entry['connection_id']
            cfg['access_binding'] = access_policy.connection_policy(entry)
        task['providers']['worker'] = cfg
        task['settings_snapshot']['values']['roles']['worker']['strategy'] = 'only'
        task['route']['ready'] = True
        requests = self.responses([{'content': 'Hello'}])
        self.engine.request(runtime, [{'role': 'user', 'content': 'Hi'}], [], 'worker', purpose='chat_reply')
        self.assertEqual([r['model'] for r in requests], ['a:free'])
        self.assertEqual(task['providers']['worker'], cfg)
        self.assertTrue(task['route']['ready'])

    def test_text_reply_provider_failure_hands_off_without_tool_probes(self):
        task = self.chat('remote'); runtime = Runtime(task)
        models = []
        class Provider:
            def __init__(self, config): self.config = config
            def complete(self, messages, tools, maximum, tool_choice=None):
                models.append(self.config['model'])
                if self.config['model'] == 'a:free':
                    raise ProviderError('Temporarily unavailable', code='http_503')
                return {'content': 'Hello'}, {'prompt_tokens': 10, 'completion_tokens': 5, 'cost': 0}
        self.engine.provider_factory = lambda role, cfg: Provider(cfg)
        response = self.engine.request(runtime, [{'role': 'user', 'content': 'Hi'}], [], 'worker', purpose='chat_reply')
        self.assertEqual(response['content'], 'Hello')
        self.assertEqual(models, ['a:free', 'b:free'])
        self.assertEqual([r['purpose'] for r in task['request_metrics']], ['chat_reply', 'chat_reply'])
        self.assertIsNone(task['providers']['worker'])

    def test_unattended_requests_select_free_roles_and_keep_accounting_purpose(self):
        task = self.chat('remote')
        requests = self.responses([{'content': 'Plan'}, {'content': 'Review'}, {'content': 'Final'}])
        runtime = Runtime(task)
        messages = [{'role': 'user', 'content': 'Prepare the bounded job.'}]
        for role, purpose in [('worker', 'branch_planning'), ('reviewer', None), ('reviewer', 'branch_final')]:
            self.engine.request(runtime, messages, [], role, purpose=purpose)
        self.assertEqual(task['providers']['worker']['model'], 'a:free')
        self.assertEqual(task['providers']['reviewer']['model'], 'b:free')
        self.assertEqual([r['model'] for r in requests], ['a:free', 'a:free', 'b:free', 'b:free', 'b:free'])
        self.assertEqual([r['purpose'] for r in task['request_metrics']], ['probe', 'branch_planning', 'probe', 'work', 'branch_final'])
        self.assertEqual(task['usage']['cost'], 0)
        self.assertEqual(sum(task['usage'][role]['tokens'] for role in ('worker', 'reviewer')), 53)

    def test_unattended_final_request_revalidates_free_model_pricing(self):
        task = self.chat('remote')
        requests = self.responses([{'content': 'Plan'}, {'content': 'Review'}, {'content': 'Final'}])
        runtime = Runtime(task)
        messages = [{'role': 'user', 'content': 'Inspect the candidate.'}]
        self.engine.request(runtime, messages, [], 'worker', purpose='branch_planning')
        self.engine.request(runtime, messages, [], 'reviewer')
        self.engine.gateway.catalog.return_value['models'] = [model('a:free'), model('b:free', free=False), model('c:free')]
        self.engine.request(runtime, messages, [], 'reviewer', purpose='branch_final')
        self.assertEqual(task['providers']['reviewer']['model'], 'c:free')
        self.assertEqual(requests[-1]['model'], 'c:free')
        self.assertEqual(task['request_metrics'][-1]['purpose'], 'branch_final')

    def chat(self, mode='delegate', prompt='Fix the lower bound.'):
        source=self.fixture()['source']
        self.engine.save_preferences({'execution':{'mode':mode,'local_model':'local-chat'}})
        self.engine.gateway.catalog=Mock(return_value={'status':'ready','models':[model('a:free'),model('b:free')], 'revision':1})
        self.engine.gateway.snapshot=Mock(return_value={'status':'ready','busy':False})
        return self.engine.create({'repository':source,'prompt':prompt,'conversational':True})

    def responses(self, replies, probe_fail=None):
        queue=iter(replies);requests=[]
        class Provider:
            def __init__(self, role, config):self.role,self.config=role,config
            def complete(self, messages, tools, maximum, tool_choice=None):
                requests.append({'role':self.role,'model':self.config['model'],'messages':copy.deepcopy(messages),'tools':copy.deepcopy(tools),'maximum':maximum,'tool_choice':tool_choice})
                if messages==PROBE_MESSAGES:
                    if probe_fail and self.config['model'] in probe_fail:
                        return {'content':'No tools.'},{'prompt_tokens':3,'completion_tokens':1,'cost':0}
                    return call('routing_ready', {'marker': PROBE_MARKER}),{'prompt_tokens':3,'completion_tokens':1,'cost':0}
                return next(queue),{'prompt_tokens':10,'completion_tokens':5,'cost':0}
        self.engine.provider_factory=lambda role,cfg:Provider(role,cfg)
        return requests

    def test_planning_closes_discovery_without_turning_stale_reads_into_route_failures(self):
        from cheapos.branch_planner import TOOLS
        task=self.chat('remote');runtime=Runtime(task)
        stale=call('inspect_project_file', {'path':'README.md'})
        requests=self.responses([stale])
        choice={'type':'function','function':{'name':'propose_branch_plan'}}
        result=self.engine.request(runtime,[{'role':'user','content':'Propose from the saved evidence.'}],TOOLS[:1],
                                   'planner',purpose='branch_planning',tool_choice=choice)
        self.assertEqual(result,stale)  # Planner repair owns this non-executed response.
        self.assertEqual(len(requests),2)  # One isolated probe, one planning request.
        self.assertEqual(requests[-1]['tool_choice'],choice)
        self.assertIsNone(requests[0]['tool_choice'])
        self.assertEqual(runtime.handoffs,0)
        self.assertFalse(task['route'].get('recovery'))
        with self.assertRaisesRegex(ProviderError,'not available'):
            self.engine.validate_offered_tools(stale,TOOLS[:1])

    def test_local_chat_has_no_project_tools_or_context_and_stops_after_one_reply(self):
        task=self.chat(prompt='Hi')
        requests=self.responses([{'content':'Hi!'}])
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0]['role'],'coordinator')
        self.assertLessEqual(requests[0]['maximum'],512)
        self.assertEqual([t['function']['name'] for t in requests[0]['tools']],['delegate_work'])
        self.assertNotIn('math_utils.py',json.dumps(requests[0]['messages']))
        self.assertEqual(result['usage']['coordinator']['tokens'],15)
        self.assertFalse(result['route']['ready'])

    def test_delegation_edit_verification_and_different_reviewer_complete(self):
        task=self.chat()
        requests=self.responses([call('delegate_work',{'summary':'Fix clamp.'}),
            call('replace_text',{'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}),
            call('run_checks',{'command':sys.executable+' -m unittest discover -v'}),
            call('checkpoint',{'summary':'Fixed clamp.','uncertainties':''}),
            call('review_decision',{'decision':'APPROVE','feedback':'Bounds fixed; checks passed.'})])
        self.engine.start(task['id'])
        for n in [0]:
            wait_for(lambda:self.engine.store.get(task['id'])['status']=='waiting_approval' and len(self.engine.store.get(task['id'])['checks'])==n)
            self.engine.approve_check(task['id'],True)
            wait_for(lambda:len(self.engine.store.get(task['id'])['checks'])>n)
        result=self.finish(task)
        self.assertEqual(result['status'],'approved',result['error'])
        self.assertEqual(result['providers']['worker']['model'],'a:free')
        self.assertEqual(result['providers']['reviewer']['model'],'b:free')
        self.assertEqual(sum(r['role']=='coordinator' for r in requests),1)
        self.assertTrue(result['changes'])
        self.assertEqual(len([e for e in result['events'] if e['kind']=='handoff']),2)
        self.assertEqual((Path(task['source'])/'math_utils.py').read_text(),'def clamp(value, lower, upper):\n    return min(value, upper)\n')
        self.assertTrue(all('math_utils.py' not in json.dumps(r['messages']) for r in requests if r['messages']==PROBE_MESSAGES))
        self.assertEqual(result['usage']['cost'],0)

    def test_offline_gateway_pauses_delegation_without_local_edits(self):
        task=self.chat();self.engine.gateway.catalog.return_value['status']='offline'
        requests=self.responses([call('delegate_work',{'summary':'Edit the file.'})])
        self.engine.start(task['id'])
        from test_engine import wait_for
        wait_for(lambda:self.engine.store.get(task['id'])['status']=='waiting_retry')
        self.engine.stop(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['changes'],[])
        self.assertEqual(len(requests),1)

    def test_local_coordinator_cannot_execute_a_forged_file_tool(self):
        task=self.chat();self.responses([call('write_file',{'path':'forged.txt','content':'bad'})])
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'paused')
        self.assertFalse((Path(task['workspace'])/'forged.txt').exists())
        self.assertEqual(result['changes'],[])

    def test_free_selection_skips_paid_local_unknown_and_broken_models(self):
        task=self.chat('remote')
        self.engine.gateway.catalog.return_value['models']=[model('paid',free=False),model('local',local=True),model('unknown',tool_calling=None),model('auto/free'),model('a:free'),model('b:free'),model('c:free')]
        requests=self.responses([{'content':'Ready.'}],probe_fail={'a:free'})
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply',result['error'])
        self.assertEqual(result['providers']['worker']['model'],'b:free')
        self.assertIsNone(result['providers']['reviewer'])
        self.assertEqual({r['model'] for r in requests},{'a:free','b:free'})
        self.assertEqual(sum(r['role']=='coordinator' for r in requests),0)

    def test_readonly_chat_needs_only_one_free_model(self):
        task=self.chat('remote');self.engine.gateway.catalog.return_value['models']=[model('a:free')]
        requests=self.responses([call('read_file',{'path':'math_utils.py'}),{'content':'The lower bound is missing.'}])
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertEqual(len(requests),3)
        self.assertEqual(result['providers']['worker']['model'],'a:free')
        self.assertIsNone(result['providers']['reviewer'])
        self.assertEqual(requests[0]['maximum'],1024)
        self.assertTrue(all(r['role']=='worker' for r in requests))
        self.assertEqual(result['changes'],[])

    def test_missing_reviewer_preserves_edits_and_resume_retries_only_review(self):
        task=self.chat('remote');self.engine.gateway.catalog.return_value['models']=[model('a:free')]
        task['check_command']=[sys.executable,'-m','unittest','discover','-v'];task['auto_approve_checks']=True
        self.engine.store.save(task)
        requests=self.responses([
            call('replace_text',{'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}),
            call('checkpoint',{'summary':'Fixed clamp.','uncertainties':''})])
        self.engine.start(task['id']);paused=self.finish(task)
        self.assertEqual(paused['status'],'paused',paused['error'])
        self.assertEqual(paused['route']['waiting_for'],'reviewer')
        self.assertEqual(paused['providers']['worker']['model'],'a:free')
        self.assertIsNone(paused['providers']['reviewer'])
        self.assertEqual(paused['iterations'],0)
        self.assertEqual(paused['pending_checkpoint']['summary'],'Fixed clamp.')
        self.assertTrue(paused['changes']);self.assertEqual(len(requests),3)
        # Reload durable state, and exhaust worker turns: resume must still review.
        paused['limits']['worker_turns']=paused['worker_turns'];self.engine.store.save(paused)
        self.engine=Engine(self.engine.store.root)
        self.engine.gateway.catalog=Mock(return_value={'status':'ready','models':[model('a:free'),model('b:free')]})
        self.engine.gateway.snapshot=Mock(return_value={'status':'ready','busy':False})
        requests=self.responses([call('review_decision',{'decision':'APPROVE','feedback':'Verified.'})])
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'approved',result['error'])
        self.assertTrue(all(r['role']=='reviewer' and r['model']=='b:free' for r in requests))
        self.assertEqual(result['patch'],paused['patch']);self.assertEqual(result['worker_turns'],paused['worker_turns'])
        self.assertEqual(result['iterations'],1);self.assertNotIn('pending_checkpoint',result)

    def test_failed_reviewer_probes_are_bounded_and_keep_worker_and_checkpoint(self):
        task=self.chat('remote')
        task['check_command']=[sys.executable,'-m','unittest'];self.engine.store.save(task)
        names=['a:free']+[str(i) for i in range(8)]
        task['route']['preferred']['worker']='a:free';self.engine.store.save(task)
        self.engine.gateway.catalog.return_value['models']=[model(n) for n in names]
        requests=self.responses([call('checkpoint',{'summary':'Ready.'})],probe_fail=set(names[1:]))
        with patch.object(self.engine,'wait_for_route',side_effect=InterruptedError('Trial paused at round boundary')):
            self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['providers']['worker']['model'],'a:free')
        self.assertEqual(len([r for r in requests if r['role']=='reviewer']),4)
        self.assertEqual(len(result['route']['failures']),4)
        self.assertTrue(all(f['role']=='reviewer' and f['error'] for f in result['route']['failures']))
        self.assertIn('pending_checkpoint',result)

    def test_probe_attempts_are_bounded(self):
        task=self.chat('remote');self.engine.gateway.catalog.return_value['models']=[model(str(i)) for i in range(8)]
        requests=self.responses([],probe_fail=set(str(i) for i in range(8)))
        with patch.object(self.engine,'wait_for_route',side_effect=InterruptedError('Trial paused at round boundary')):
            self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'paused');self.assertEqual(len(requests),4)

    def test_all_local_never_discovers_or_dispatches_remote_models(self):
        task=self.chat('local',prompt='Hi');self.engine.gateway.catalog=Mock(side_effect=AssertionError('Remote discovery'))
        requests=self.responses([{'content':'Hello.'}]);self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertEqual(result['providers']['worker']['base_url'],'http://127.0.0.1:11434/v1')
        self.assertEqual({r['model'] for r in requests},{'local-chat'})
        self.engine.gateway.catalog.assert_not_called()

    def test_preferences_do_not_rewrite_existing_tasks(self):
        task=self.chat('local');before=copy.deepcopy(task)
        self.engine.save_preferences({'execution':{'mode':'remote'}})
        self.assertEqual(self.engine.store.get(task['id']),before)
        self.assertEqual(Engine(self.engine.store.root).preferences()['execution']['mode'],'remote')

    def test_three_identical_reads_allow_one_answer_request_without_tools(self):
        task=self.chat('local');requests=self.responses([call('read_file',{'path':'math_utils.py'})]*4)
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['error_code'],'progress_limit');self.assertEqual(result['status'],'paused')
        self.assertEqual(len(requests),4);self.assertFalse(result['checkpoints'])
        self.assertTrue(result['answer_pending'])
        self.assertEqual(sum(e['title']=='read file' for e in result['events']),3)

    def test_legacy_checkpoint_turn_limit_bounds_even_changing_edits(self):
        task=self.chat('local');task.pop('checkpoint_policy');task['limits'].update(checkpoint_turns=2,worker_turns=100);self.engine.store.save(task)
        requests=self.responses([call('write_file',{'path':'new1.py','content':'one'}),call('write_file',{'path':'new2.py','content':'two'}),{'content':'Never called'}])
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'paused');self.assertEqual(len(result['changes']),2);self.assertEqual(len(requests),2)
        self.assertIn('2-turn checkpoint limit',result['error'])
        self.assertIn('2 of 100 worker turns',result['error'])
        self.assertEqual(result['error_code'],'checkpoint_turn_limit')

    def test_expired_run_stops_before_inference(self):
        task=self.chat('local');runtime=Runtime(task);runtime.started-=10000
        self.engine.provider_factory=Mock(side_effect=AssertionError('No call'))
        with self.assertRaises(ProgressPause):self.engine.request(runtime,[],[],'worker')
        self.engine.provider_factory.assert_not_called()

    def test_invalid_execution_is_rejected(self):
        for value in [{'mode':'paid-auto'},{'mode':'local','local_model':False},None,{'mode':'local','download':True}]:
            with self.assertRaises(ValueError):execution_from(value)

    def test_local_metadata_blocks_cloud_alias_and_unreachable_ollama(self):
        from cheapos.routing import verify_local,local_config,RoutingPause
        for info in [{'remote_host':'https://ollama.com','capabilities':['completion','tools']},{'capabilities':['completion']}]:
            with patch('cheapos.startup.local_json',return_value=info),self.assertRaises(RoutingPause):verify_local(local_config('alias','worker'))
        with patch('cheapos.startup.local_json',side_effect=OSError()),self.assertRaises(RoutingPause):verify_local(local_config('alias','worker'))

    def test_paid_probe_response_stops_before_another_candidate_or_file_tool(self):
        task=self.chat('remote');calls=[]
        class Paid:
            def complete(self,*args):
                calls.append(1)
                return call('routing_ready', {'marker': PROBE_MARKER}),{'prompt_tokens':10,'completion_tokens':2,'cost':.1}
        self.engine.provider_factory=lambda *args:Paid()
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'budget_paused');self.assertEqual(len(calls),1)
        self.assertAlmostEqual(result['usage']['cost'],.1);self.assertEqual(result['changes'],[])

    def test_followup_keeps_remote_pair_and_returns_to_local_chat(self):
        task=self.chat();requests=self.responses([call('delegate_work',{'summary':'Explain clamp.'}),{'content':'Clamp has a lower bound bug.'},{'content':'You are welcome!'}])
        self.engine.start(task['id']);first=self.finish(task)
        self.engine.start(task['id'],{'message':'Thanks'});result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertEqual(result['providers'],first['providers'])
        self.assertEqual([r['role'] for r in requests],['coordinator','worker','worker','coordinator'])

    def test_remote_mode_startup_never_queries_local_discovery(self):
        self.chat('remote');self.engine.startup._omni=Mock(return_value=[])
        with patch('cheapos.startup.local_candidates',side_effect=AssertionError('Local discovery')):
            self.assertEqual(list(self.engine.startup._candidates(None)),[])

    def test_local_mode_startup_never_falls_back_to_cloud(self):
        self.chat('local');self.engine.startup._omni=Mock(side_effect=AssertionError('Cloud discovery'))
        with patch('cheapos.startup.local_candidates',return_value=[]):
            self.assertEqual(list(self.engine.startup._candidates(None)),[])

    def test_compaction_deduplicates_unchanged_read_payloads(self):
        task=self.chat('local')
        for _ in range(3):self.engine.file_tool(task,'read_file',{'path':'math_utils.py'})
        summary=json.loads(self.engine.initial_messages(task)[1]['content'])
        self.assertEqual(sum(a['action']=='read file' for a in summary['recent_activity']),1)

    def test_coordinator_cannot_exceed_cumulative_turn_limit_during_handoff(self):
        task=self.chat();task['limits']['worker_turns']=1;self.engine.store.save(task)
        requests=self.responses([call('delegate_work',{'summary':'Do work.'})])
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'budget_paused');self.assertEqual(len(requests),1)
        self.assertEqual(result['worker_turns'],1);self.assertFalse(result['route']['ready'])

    def test_invalid_checkpoints_cannot_reset_the_progress_limit(self):
        task=self.chat('local');task['limits']['checkpoint_turns']=2;self.engine.store.save(task)
        requests=self.responses([call('checkpoint',{'summary':'Done','uncertainties':''})]*3)
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['error_code'],'progress_limit');self.assertEqual(len(requests),2)
        self.assertEqual(result['checkpoints'],[])

    def test_probe_rejected_model_is_skipped_on_next_task(self):
        task = self.chat('remote')
        runtime = Runtime(task)
        endpoint = task['route']['base_url']
        revision = (task['route'].get('access_policy') or {}).get('connection_revision')
        self.engine.gateway.pool.record(endpoint, 'dead-candidate:free', 'worker',
                                       error=ProviderError('Model dead', code='http_400'),
                                       connection_revision=revision,
                                       failure_context={'caller_error': False, 'candidate_rejected': True})
        self.engine.gateway.catalog.return_value['models'] = [
            model('dead-candidate:free'),
            model('good-candidate:free'),
        ]
        requests = self.responses([{'content': 'Work'}])
        messages = [{'role': 'user', 'content': 'Do work'}]
        self.engine.request(runtime, messages, [], 'worker')
        self.assertEqual(task['providers']['worker']['model'], 'good-candidate:free')
        self.assertNotIn('dead-candidate:free', [r['model'] for r in requests])
