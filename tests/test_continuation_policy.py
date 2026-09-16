import unittest
from cheapos.continuation_policy import decide, is_continue, record, implementation_handoff
from cheapos import progress, work_policy
class ContinuationPolicyTests(unittest.TestCase):
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
