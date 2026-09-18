import unittest
from cheapos.continuation_policy import decide, is_continue, record, implementation_handoff
from cheapos import progress, work_policy
class ContinuationPolicyTests(unittest.TestCase):
    def test_stalled_review_selects_recovery_instead_of_replaying_exhausted_step(self):
        task={'branch_run':{'current_item_id':'one'},'execution':{'mode':'remote'},'route':{'base_url':'gateway'},
              'providers':{'reviewer':{'model':'reviewer'}},'pending_review':{'stop_diagnostic':{'kind':'review_stall'}}}
        self.assertEqual(decide(task)['action'],'recover_review')
        task['operator_reviewer_model']='reviewer'
        self.assertEqual(decide(task)['action'],'choose_reviewer')
        task['pending_approval']={'command':['test']}
        self.assertEqual(decide(task)['action'],'approve_command')

    def test_final_stall_respects_saved_routing_and_authority(self):
        task={'branch_run':{},'execution':{'mode':'remote'},'route':{'base_url':'gateway'},
              'providers':{'reviewer':{'model':'reviewer'}}}
        self.assertEqual(decide(task,'final_review_stall')['action'],'recover_review')
        task['operator_reviewer_model']='reviewer'
        self.assertEqual(decide(task,'final_review_stall')['action'],'choose_reviewer')
        task['pending_approval']={'command':['test']}
        self.assertEqual(decide(task,'final_review_stall')['action'],'approve_command')
        task.pop('pending_approval');task['limit_hit']={'key':'dollars'}
        self.assertEqual(decide(task,'final_review_stall')['action'],'review_limits')

    def test_actions_and_idempotent_episode(self):
        for patch, action in [({'pending_approval':{'command':['test']}},'approve_command'),({'environment_setup':{'status':'missing'}},'repair_environment'),({'limit_hit':{'key':'dollars'}},'review_limits'),({'pending_review':{'id':'x'}},'continue_review'),({'error_code':'http_429'},'route_recovery')]:
            task={'prompt':'Fix',**patch};self.assertEqual(decide(task)['action'],action)
            record(task,'button');record(task,'chat');self.assertEqual(len(task['continuation_episodes']),1)
        self.assertTrue(is_continue('Continue please!'));self.assertFalse(is_continue('Continue and delete everything'))
        self.assertTrue(is_continue('plan approved, continue'))
        self.assertTrue(is_continue('Plan approved. Continue'))
        self.assertTrue(is_continue('approved'))
        self.assertTrue(is_continue('start'))
        self.assertTrue(is_continue('looks good, continue'))
        self.assertTrue(is_continue('i approve'))
        self.assertTrue(is_continue('I approve this plan'))
        self.assertTrue(is_continue('approve it'))
        self.assertTrue(is_continue('please approve'))
        self.assertTrue(is_continue('looks good to me'))
        self.assertTrue(is_continue('lgtm'))
        self.assertTrue(is_continue('good to go'))
        self.assertTrue(is_continue('go for it'))
        self.assertTrue(is_continue('proceed with the plan'))
        self.assertTrue(is_continue('yes, go ahead'))
        self.assertFalse(is_continue('Also support YAML files'))
        self.assertFalse(is_continue('do not approve'))
        self.assertFalse(is_continue("don't approve this plan"))
        self.assertFalse(is_continue('not approved'))
    def test_new_ranges_not_rewords_or_todos(self):
        task={'prompt':'Explain','patch':''};progress.state(task)
        self.assertTrue(progress.inspection(task,'file','v1',{1,2}))
        revision=progress.state(task)['revision']
        self.assertFalse(progress.inspection(task,'file','v1',{2,1}))
        task['working_states']={'interactive':{'revision':99}};self.assertFalse(progress.observe(task))
        self.assertEqual(progress.state(task)['revision'],revision)
        self.assertTrue(progress.inspection(task,'file','v1',{3}))
    def test_large_files_keep_tools_and_review_is_not_worker_handoff(self):
        task={'limits':{'output_tokens':8192},'events':[{'kind':'tool','title':'read file','detail':{'result':{'total_lines':10000}}}]}
        self.assertIsNone(work_policy.small_edit_reason(task))
        task.update(status='paused',error_code='progress_limit',active_role='worker',pending_review={'id':'x'})
        self.assertFalse(implementation_handoff(task,{'status':'working'}))
    def test_worker_error_status_recovers_via_implementation_handoff(self):
        task={'prompt':'Implement feature','active_role':'worker','status':'error','error_code':'stream_interrupted'}
        self.assertTrue(implementation_handoff(task,{'status':'working'}))
        task['status'] = 'paused'
        task['error_code'] = 'progress_limit'
        self.assertTrue(implementation_handoff(task,{'status':'working'}))
        task['error_code'] = 'worker_turn_limit'
        self.assertFalse(implementation_handoff(task,{'status':'working'}))
        task['error_code'] = 'environment_setup'
        self.assertFalse(implementation_handoff(task,{'status':'working'}))
    def test_repeated_clicks_do_not_dispatch_or_renew(self):
        from threading import RLock
        from types import SimpleNamespace
        from unittest.mock import Mock
        from cheapos.engine import Engine
        from cheapos.branch_controller import BranchController
        task={'id':'saved','requests':['Fix'],'usage':{'tokens':42}}
        runtime=SimpleNamespace(thread=SimpleNamespace(is_alive=lambda:True))
        engine=SimpleNamespace(lock=RLock(),runtimes={'saved':runtime},store=SimpleNamespace(get=lambda _:task),
                               require_active_task=Mock(),admission=Mock())
        engine.startup=SimpleNamespace(busy=lambda:False)
        # Branch and interactive busy paths return the saved state before admission.
        controller=SimpleNamespace(engine=engine)
        self.assertIs(BranchController.resume(controller,'saved',{})['task'],task)
        self.assertIs(Engine.start(engine,'saved',{'message':'continue'}),task)
        engine.admission.require.assert_not_called()
        self.assertEqual(task['usage']['tokens'],42)

    def test_repeated_evidence_decision_for_interactive_and_read_only(self):
        # Implementation prompt transitions to act
        task_fix = {'prompt': 'Lets fix these issues', 'patch': ''}
        self.assertEqual(decide(task_fix, trigger='repeated_evidence')['action'], 'act')

        # Read only prompt transitions to answer
        read_only_prompt = work_policy.READ_ONLY_STARTERS[0]
        task_read = {'prompt': read_only_prompt, 'patch': '', 'conversational': True}
        self.assertEqual(decide(task_read, trigger='repeated_evidence')['action'], 'answer')

        # Development mode must not loop on continue_worker
        task_dev = {'prompt': 'Lets fix these issues', 'patch': '', 'execution': {'development_mode': True}}
        self.assertEqual(decide(task_dev, trigger='repeated_evidence')['action'], 'act')

    def test_conditional_ui_request_remains_implementation_before_first_edit(self):
        prompt = 'When I restart the app, the project manager window pops up. We need to stop that. Only show that if no project exists.'
        task = {'prompt': prompt, 'conversational': True, 'patch': ''}
        self.assertEqual(decide(task, 'repeated_evidence')['action'], 'act')
        self.assertEqual(work_policy.stage(task), 'implementation')
        for question in ('Why does it only show if no project exists?',
                         'Explain how to hide the project manager.',
                         'Only show it if no project exists, without making changes.'):
            with self.subTest(question=question):
                self.assertEqual(decide({**task, 'prompt': question}, 'repeated_evidence')['action'], 'answer')

class DurableStrategyTests(__import__('unittest').TestCase):
    def test_episode_survives_reload_without_renewing_attempts_or_usage(self):
        import json
        from cheapos.continuation_policy import strategy_episode
        task={'usage':{'cost':1},'worker_turns':9}
        first=strategy_episode(task,'worker','invalid_json','candidate',['format','handoff'])
        self.assertEqual(first['next_action'],'format')
        task=json.loads(json.dumps(task))
        self.assertEqual(strategy_episode(task,'worker','invalid_json','candidate',['format','handoff'])['next_action'],'handoff')
        self.assertEqual(strategy_episode(task,'worker','invalid_json','candidate',['format','handoff'])['next_action'],'prerequisite')
        self.assertEqual(task['usage'],{'cost':1});self.assertEqual(task['worker_turns'],9)
