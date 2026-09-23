from tests.test_review_assessment import fixture_review_call
"""Conversation routing, continuity, command approval, and local project setup."""
import json
import sys
from pathlib import Path
from unittest.mock import Mock

from cheapos.engine import Engine, request_worker_turns
from cheapos.storage import Store
from cheapos.workspace import Workspace
from test_engine import LocalCase, call, wait_for


class ChatTests(LocalCase):
    def chat(self, prompt='Explain clamp.'):
        source = self.fixture()['source']
        self.engine.save_preferences({'execution': {'mode': 'manual'}})
        self.engine.configure({role: {'base_url':'http://127.0.0.1:11434/v1','model':'fixture-' + role,'input_rate':0,'output_rate':0} for role in ['worker','reviewer']})
        return self.engine.create({'repository':source, 'prompt':prompt, 'conversational':True})

    def provider(self, responses):
        requests=[]
        queue=iter(responses)
        class Provider:
            def complete(self, messages, tools, maximum):
                requests.append((json.loads(json.dumps(messages)), tools))
                return fixture_review_call(next(queue), messages), {'prompt_tokens':10,'completion_tokens':5,'cost':0}
        self.engine.provider_factory=lambda role, config: Provider()
        return requests

    def test_open_project_is_local_and_remembered_without_starting_a_task(self):
        source=self.fixture()['source']
        factory=Mock()
        self.engine.provider_factory=factory
        count=len(self.engine.store.list())
        project=self.engine.open_project({'repository':source})
        self.assertEqual(project['path'], source)
        self.assertEqual(len(self.engine.store.list()),count)
        factory.assert_not_called()
        restored=Engine(self.engine.store.root)
        self.assertEqual(restored.projects()[0]['path'],source)
        for value in ['', '  ', None]:
            with self.assertRaises(ValueError):
                self.engine.open_project({'repository':value})
        restored.shutdown()

    def test_question_and_followup_use_same_workspace_and_cumulative_usage(self):
        task=self.chat()
        requests=self.provider([call('read_file', {'path':'math_utils.py'}), {'role':'assistant','content':'It caps the upper bound.'}, {'role':'assistant','content':'The lower bound is currently ignored.'}])
        self.engine.start(task['id'])
        first=self.finish(task)
        self.assertEqual(first['status'],'awaiting_reply')
        self.assertEqual(first['review_count'],0)
        self.assertEqual(first['checks'],[])
        self.assertEqual(first['changes'],[])
        self.engine.start(task['id'], {'message':'What about the lower bound?'})
        second=self.finish(task)
        self.assertEqual(second['workspace'],task['workspace'])
        self.assertEqual(second['usage']['worker']['tokens'],45)
        self.assertEqual(second['worker_turns'],3)
        context=json.loads(requests[-1][0][-1]['content'])
        self.assertEqual(context['latest_message'],'What about the lower bound?')
        self.assertIn('It caps the upper bound.',json.dumps(context))
        self.assertEqual(context['recovery_continuation']['prior_worker_statements_unverified'],
                         ['It caps the upper bound.'])
        self.assertIn('math_utils.py', [f['path'] for f in context['continuation_record']['files']])
        restored=Store(self.engine.store.root).get(task['id'])
        self.assertEqual(restored['requests'], ['Explain clamp.','What about the lower bound?'])
        rebuilt=json.loads(self.engine.initial_messages(restored)[1]['content'])
        self.assertIn('It caps the upper bound.',json.dumps(rebuilt))
        self.assertIn('The lower bound is currently ignored.',json.dumps(rebuilt))
        self.assertEqual(restored['checks'],[])
        self.assertEqual(restored['review_count'],0)

    def test_edits_cannot_finish_as_a_plain_answer_or_skip_review(self):
        task=self.chat('Fix the lower bound.')
        self.provider([call('replace_text', {'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}), {'role':'assistant','content':'Done.'},call('ask_user', {'question':'What check should I use?'})])
        self.engine.start(task['id'])
        result=self.finish(task)
        self.assertEqual(result['worker_turns'],3)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertTrue(result['changes'])
        self.assertEqual(result['review_count'],0)
        self.assertEqual(result['checkpoints'],[])
        self.assertEqual(result['events'][-1]['detail'],'What check should I use?')
        # An explicit review request must not become another conversation-only
        # turn, even when the worker first describes the checks in plain text.
        result['turn_start_patch']=result['patch']
        self.engine.store.save(result)
        self.provider([
            {'role':'assistant','content':'I will verify the saved change and request review.'},
            call('run_checks',{'command':sys.executable+' -m unittest discover -v'}),
            {'role':'assistant','content':'Checks passed. The saved change is ready for review.'},
            call('review_decision',{'decision':'APPROVE','feedback':'The requested lower bound fix is verified.'}),
        ])
        self.engine.start(task['id'],{'finish_review':True})
        wait_for(lambda:self.engine.store.get(task['id'])['status']=='waiting_approval')
        self.assertEqual(self.engine.store.get(task['id'])['checks'],[])
        self.engine.approve_check(task['id'],True)
        reviewed=self.finish(task)
        self.assertEqual(reviewed['status'],'approved',reviewed['error'])
        self.assertEqual(len(reviewed['checks']),1)
        self.assertEqual(reviewed['review_count'],1)
        self.assertEqual(reviewed['patch'],result['patch'])
        self.assertEqual(reviewed['request_worker_turns'],6)
        self.assertNotIn('finish_review',reviewed)
        self.assertIn('return min(value, upper)',(Path(task['source'])/'math_utils.py').read_text())

    def test_proposed_command_waits_for_permission_and_decline_executes_nothing(self):
        task=self.chat('Run the appropriate checks.')
        self.provider([call('run_checks',{'command':sys.executable+' -c "open(\'should-not-exist\', \'w\').write(\'bad\')"'})])
        self.engine.start(task['id'])
        wait_for(lambda:self.engine.store.get(task['id'])['status']=='waiting_approval')
        self.assertFalse((Path(task['workspace'])/'should-not-exist').exists())
        with self.assertRaisesRegex(ValueError,'already running'):
            self.engine.start(task['id'],{'message':'another message'})
        self.engine.approve_check(task['id'],False)
        result=self.finish(task)
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['check_command'],[])
        self.assertEqual(result['checks'],[])
        self.assertFalse((Path(task['workspace'])/'should-not-exist').exists())

    def test_edit_check_review_then_followup_is_a_continuous_chat(self):
        task=self.chat('Explain clamp. Do not edit yet.')
        requests=self.provider([
            {'role':'assistant','content':'It currently limits only the upper bound.'},
            call('replace_text',{'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}),
            call('run_checks',{'command':sys.executable+' -m unittest discover -v'}),
            call('ask_user',{'question':'Shall I submit the saved changes for review?'}),
            call('review_decision',{'decision':'APPROVE','feedback':'The change meets the request and checks pass.'}),
            {'role':'assistant','content':'It uses max for the lower bound and min for the upper.'}
        ])
        self.engine.start(task['id'])
        self.assertEqual(self.finish(task)['status'],'awaiting_reply')
        self.engine.start(task['id'],{'message':'Now fix the lower bound.'})
        # Checkpoint reuses the controller's passing check for the same patch.
        for expected in [1]:
            wait_for(lambda:self.engine.store.get(task['id'])['status']=='waiting_approval' and len(self.engine.store.get(task['id'])['checks'])==expected-1)
            self.engine.approve_check(task['id'],True)
            wait_for(lambda:len(self.engine.store.get(task['id'])['checks'])>=expected)
        waiting=self.finish(task)
        self.assertEqual(waiting['status'],'awaiting_reply')
        # Reproduce the old Finish review detour: no extra worker/coordinator
        # round trip or test execution is needed when current checks passed.
        self.engine.start(task['id'],{'finish_review':True})
        first=self.finish(task)
        self.assertEqual(first['worker_turns'],waiting['worker_turns'])
        self.assertEqual(first['request_worker_turns'],waiting['request_worker_turns'])
        self.assertEqual(first['status'],'approved')
        self.assertEqual(first['review_count'],1)
        self.assertEqual(len(first['checks']),1)
        self.assertTrue(first['checks'][-1]['passed'])
        self.assertEqual(first['checkpoints'][-1]['user_messages'],['Explain clamp. Do not edit yet.','Now fix the lower bound.'])
        self.engine.start(task['id'],{'message':'Explain the fix without making more changes.'})
        second=self.finish(task)
        self.assertEqual(second['status'],'awaiting_reply')
        self.assertEqual(second['patch'],first['patch'])
        self.assertEqual(second['review_count'],1)
        self.assertEqual(second['checks'],first['checks'])
        self.assertEqual(second['usage']['worker']['tokens'],first['usage']['worker']['tokens']+15)
        self.assertEqual(second['providers'],first['providers'])
        self.assertEqual(second['limits'],first['limits'])

    def test_followup_does_not_bypass_budget_or_authorize_takeover(self):
        task=self.chat()
        task['status']='takeover_requested'
        task['worker_turns']=task['limits']['worker_turns']
        task['usage']['cost']=.01
        self.engine.store.save(task)
        factory=Mock()
        self.engine.provider_factory=factory
        self.engine.start(task['id'],{'message':'Explain why you need help.'})
        result=self.finish(task)
        self.assertEqual(result['status'],'budget_paused')
        self.assertEqual(result['active_role'],'worker')
        factory.assert_not_called()

    def test_followup_gets_own_worker_turns_but_resume_and_restart_do_not_reset_them(self):
        task=self.chat();task['limits']['worker_turns']=1
        task['limits'].pop('work_policy_version', None)  # Exercise the saved legacy allowance.
        self.engine.store.save(task)
        self.provider([call('read_file',{'path':'math_utils.py'})])
        self.engine.start(task['id']);first=self.finish(task)
        self.assertEqual(first['error_code'],'worker_turn_limit')
        self.assertEqual(first['request_worker_turns'],1)
        self.engine.shutdown();self.engine=Engine(self.engine.store.root)
        factory=Mock();self.engine.provider_factory=factory
        self.engine.start(task['id']);resumed=self.finish(task)
        self.assertEqual(resumed['error_code'],'worker_turn_limit');factory.assert_not_called()
        self.provider([{'content':'The function caps values at the upper bound.'}])
        self.engine.start(task['id'],{'message':'Explain briefly.'});second=self.finish(task)
        self.assertEqual(second['status'],'awaiting_reply')
        self.assertEqual(second['request_worker_turns'],1)
        self.assertEqual(second['worker_turns'],2)
        self.assertEqual(second['usage']['worker']['tokens'],first['usage']['worker']['tokens']+15)
        self.assertEqual(second['limits'],first['limits'])

    def test_legacy_chat_recovers_request_turns_without_counting_route_probes(self):
        task=self.chat();task.pop('request_worker_turns')
        task['worker_turns']=8
        task['events']=[{'kind':'model','title':'Requesting worker: old'}]*5+[
            {'kind':'user','title':'You'},
            {'kind':'routing','title':'Checking a free worker'},
            {'kind':'model','title':'Requesting worker: probe'},
            {'kind':'model','title':'Requesting coordinator: local'},
            {'kind':'model','title':'Requesting worker: new'},
            {'kind':'model','title':'Requesting worker: new'}]
        self.assertEqual(request_worker_turns(task),3)
        task['worker_turns']=9
        self.assertEqual(request_worker_turns(task),4)

    def test_followup_does_not_reset_reviewer_token_budget(self):
        task=self.chat();task['usage']['reviewer']['tokens']=task['limits']['reviewer_tokens']+1
        task['limits'].pop('work_policy_version', None)  # Exercise the saved legacy allowance.
        self.engine.store.save(task);factory=Mock();self.engine.provider_factory=factory
        self.engine.start(task['id'],{'message':'A new request.'});result=self.finish(task)
        self.assertEqual(result['status'],'budget_paused');factory.assert_not_called()

    def test_new_chat_defaults_to_zero_spend_and_limit_edits_do_not_run_models(self):
        task=self.chat()
        self.assertEqual(task['limits']['dollars'],0)
        self.engine.update_limits(task['id'], {'limits':{**task['limits'],'worker_turns':60}})
        result=self.engine.store.get(task['id'])
        self.assertEqual(result['status'],'ready')
        self.assertEqual(result['worker_turns'],0)
        self.assertEqual(result['limits']['worker_turns'],60)
        self.assertEqual(result['usage']['cost'],0)
        self.engine.save_preferences({'limits':{**task['limits'],'output_tokens':4096}})
        self.assertEqual(self.engine.preferences()['limits']['output_tokens'],4096)

    def test_new_command_cannot_inherit_a_legacy_command_permission(self):
        task=self.chat('Choose a suitable check.')
        task['check_command']=[sys.executable,'-m','unittest','discover','-v']
        task['auto_approve_checks']=True
        self.engine.store.save(task)
        self.provider([call('run_checks',{'command':sys.executable+' -c "print(123)"'})])
        self.engine.start(task['id'])
        wait_for(lambda:self.engine.store.get(task['id'])['status']=='waiting_approval')
        self.assertEqual(self.engine.store.get(task['id'])['checks'],[])
        self.engine.approve_check(task['id'],False)
        self.assertEqual(self.finish(task)['status'],'paused')
