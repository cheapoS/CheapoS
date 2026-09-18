"""Work allowance contracts without models, Git workflows or real-time waits."""
import copy
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from cheapos.branch_authorization import digest
from cheapos.branch_budget import Ledger, LimitExceeded
from cheapos.branch_completion import authorization_run
from cheapos.branch_controller import run_limits
from cheapos.branch_runs import validate_plan
from cheapos.engine import Engine, Runtime, WorkingTimeLimit, limits_from
from cheapos.measurement import enabled, is_measurement
from cheapos.providers import BudgetError, reserve


class UncappedWorkTests(unittest.TestCase):
    def task(self):
        limits = run_limits({'worker_turns':200, 'requests':196}, 1)
        plan = validate_plan({'items':[{'id':'one','title':'One','instructions':'Finish',
                                       'acceptance_criteria':['Works']}], 'limits':limits})
        run = {'id':'run','status':'paused','plan':plan,'limits':copy.deepcopy(limits),
               'plan_revision':1,'consumption':{'requests':196},'pause_reason':'exhausted_work',
               'authorization_ref':'approved','items':[{'id':'one','status':'reviewing'}]}
        contract = {'plan':copy.deepcopy(plan),'limits':copy.deepcopy(limits),'plan_revision':1,
                    'model_policy':{'free_only':True},'check_scope':['exact-test-command']}
        run['authorization'] = {'id':'approved','contract':contract,'digest':digest(contract)}
        return {'id':'task','branch_run':run, 'limits':limits_from({'dollars':0,'worker_turns':200}),
                'worker_turns':201,'tool_actions':300,'pending_review':{'review_requests':9},
                'error_code':'exhausted_work','error':'Run limit reached: requests (197 / 196)',
                'usage':{'cost':0,'reviewer':{'tokens':40000,'cost':0},'worker':{'tokens':100000,'cost':0},'uncertain_requests':0},
                'providers':{'worker':'original'},'recovery_blocked':4}

    def engine(self, task):
        self.saved = copy.deepcopy(task)
        def save(value): self.saved = json.loads(json.dumps(value))
        return SimpleNamespace(lock=threading.RLock(),runtimes={},require_active_task=Mock(),
                               store=SimpleNamespace(get=lambda _:copy.deepcopy(self.saved),save=save),event=Mock())

    def test_explicit_boolean_and_worker_allowances_above_200(self):
        self.assertNotIn('uncapped_work', limits_from({}))
        self.assertEqual(limits_from({'worker_turns':1200})['worker_turns'],1200)
        self.assertEqual(run_limits({'worker_turns':12000},1)['worker_turns'],12000)
        task=self.task();task.pop('branch_run');task['limits']['worker_turns']=1200
        self.assertEqual(Engine.boost_headroom(self.engine(task),'task')['limits']['worker_turns'],1210)
        for value in ('true', 1, None):
            with self.assertRaises(ValueError): limits_from({'uncapped_work':value})
            with self.assertRaises(ValueError): validate_plan({**self.task()['branch_run']['plan'],'uncapped_work':value})
        for value in (float('inf'),float('nan'),-1,1.5):
            with self.assertRaises(ValueError): limits_from({'worker_turns':value})

    def test_operator_update_removes_work_caps_preserves_authority_and_accounting(self):
        before = self.task();engine = self.engine(before)
        with self.assertRaises(LimitExceeded):
            Ledger(SimpleNamespace(task=before,stop=threading.Event()),lambda:None).guard(next_request=True)
        result = Engine.update_limits(engine,'task',{'limits':{'uncapped_work':True}})
        self.assertTrue(enabled(result));self.assertFalse(is_measurement(result))
        for key in ('worker_turns','tool_actions','pending_review','providers','usage','recovery_blocked'):
            self.assertEqual(result[key],before[key])
        auth=result['branch_run']['authorization']
        self.assertEqual(auth['digest'],digest(auth['contract']))
        self.assertEqual(auth['contract']['check_scope'],['exact-test-command'])
        self.assertEqual(auth['contract']['model_policy'],{'free_only':True})
        authorization_run(result['branch_run'])
        # Saved/reloaded choice still allows request 197 and worker turn 202.
        restored=json.loads(json.dumps(self.saved))
        ledger=Ledger(SimpleNamespace(task=restored,stop=threading.Event()),lambda:None)
        ledger.guard(next_request=True,next_worker_turn=True,next_action=True)
        self.assertEqual(restored['branch_run']['consumption']['requests'],196)
        self.assertEqual(restored['limits']['dollars'],0)
        self.assertEqual(result['branch_run']['limits']['requests'],196) # no hidden cap multiplier
        restored['usage']['cost']=.01
        with self.assertRaises(LimitExceeded) as failure:ledger.guard()
        self.assertEqual(failure.exception.key,'dollars')
        self.assertEqual(engine.event.call_args.args[3]['origin'],'operator')

    def test_only_operator_can_change_branch_exemption_and_bounded_mode_restores_caps(self):
        task=self.task();task['limits']['uncapped_work']=True
        self.assertFalse(enabled(task))
        task['branch_run']['plan']['uncapped_work']=True
        with self.assertRaisesRegex(ValueError,'uncapped'):authorization_run(task['branch_run'])
        engine=self.engine(self.task())
        Engine.update_limits(engine,'task',{'limits':{'uncapped_work':True}})
        bounded=Engine.update_limits(engine,'task',{'limits':{'uncapped_work':False}})
        self.assertFalse(enabled(bounded));authorization_run(bounded['branch_run'])
        with self.assertRaises(LimitExceeded):
            Ledger(SimpleNamespace(task=bounded,stop=threading.Event()),lambda:None).guard(next_request=True)

    def test_interactive_time_and_token_caps_can_be_removed_but_money_and_output_cannot(self):
        task=self.task();task.pop('branch_run');task['limits']['uncapped_work']=True
        runtime=Runtime(task);runtime.started-=100000
        runtime.guard();runtime.step_turns=999
        engine = Engine.__new__(Engine)
        engine.refresh_changes = Mock(side_effect=lambda t: t.setdefault('patch', ''))
        engine.recover_worker_stall = Mock()
        engine.checkpoint_boundary(runtime)
        self.assertEqual(runtime.step_turns, 0)
        reservation=reserve(task,{'input_rate':0,'output_rate':0},[],[],'reviewer')
        self.assertEqual(reservation['completion_tokens'],task['limits']['output_tokens'])
        with self.assertRaises(BudgetError):reserve(task,{'input_rate':1,'output_rate':1},[],[],'worker')
        task['limits']['uncapped_work']=False
        with self.assertRaises(WorkingTimeLimit):runtime.guard()

    def test_active_run_cannot_change_allowances(self):
        engine=self.engine(self.task());engine.runtimes['task']=SimpleNamespace(thread=SimpleNamespace(is_alive=lambda:True))
        with self.assertRaisesRegex(ValueError,'Pause'):Engine.update_limits(engine,'task',{'limits':{'uncapped_work':True}})
        self.assertFalse(enabled(self.saved))

    def test_interactive_allowance_update_exposes_resume_without_hiding_a_money_blocker(self):
        task=self.task();task.pop('branch_run')
        task.update(status='budget_paused',limit_hit={'key':'run_minutes'},error_code='working_time_limit')
        result=Engine.update_limits(self.engine(task),'task',{'limits':{'uncapped_work':True}})
        self.assertEqual(result['status'],'paused');self.assertIsNone(result['error_code'])
        self.assertNotIn('limit_hit',result)
        task['limit_hit']={'key':'dollars'}
        result=Engine.update_limits(self.engine(task),'task',{'limits':{'uncapped_work':True}})
        self.assertEqual(result['status'],'budget_paused');self.assertEqual(result['limit_hit']['key'],'dollars')
