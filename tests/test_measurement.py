import copy
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from test_engine import LocalCase
from cheapos.providers import ChatProvider
from cheapos.branch_budget import Ledger, LimitExceeded
from cheapos.branch_completion import authorization_run
from cheapos.branch_runs import validate_plan
from cheapos.engine import Engine, Runtime
from cheapos.providers import reserve, reconcile, BudgetError
from cheapos.workspace import Workspace
import test_branch_execution as execution


class MeasurementTests(unittest.TestCase):
    def task(self):
        return {'branch_run': {'plan': {'measurement': True}, 'limits': {'working_seconds':1,'requests':1,'worker_turns':1,'tool_actions':1,'reviewer_tokens':1,'dollars':0},'consumption':{}},
                'limits': {'reviewer_tokens':1,'output_tokens':2048,'dollars':0,'worker_turns':1,'checkpoint_turns':2},
                'worker_turns':4,'tool_actions':5,'checks':[{'duration':2.5}],
                'request_metrics':[{'id':'a'},{'id':'b'}],
                'usage':{'uncertain_requests':0,'estimated_requests':0,'worker':{'tokens':40,'cost':0},'reviewer':{'tokens':50,'cost':0},'cost':0}}

    def test_measured_usage_survives_limits_and_restart_but_money_stays_bounded(self):
        task=self.task(); now=[0]; rt=SimpleNamespace(task=task,stop=threading.Event())
        ledger=Ledger(rt,lambda:None,clock=lambda:now[0]);ledger.begin(start_watchdog=False)
        now[0]=4000;ledger.guard(next_request=True,next_worker_turn=True,next_action=True);ledger.end()
        self.assertEqual(task['branch_run']['consumption']['working_seconds'],4000)
        self.assertEqual(task['branch_run']['consumption']['worker_tokens'],40)
        self.assertEqual(task['branch_run']['consumption']['check_seconds'],2.5)
        restored=json.loads(json.dumps(task));rt.task=restored
        resumed=Ledger(rt,lambda:None,clock=lambda:now[0]);resumed.begin(start_watchdog=False);now[0]+=20;resumed.end()
        self.assertEqual(restored['branch_run']['consumption']['working_seconds'],4020)
        restored['usage']['cost']=.01
        with self.assertRaises(LimitExceeded):resumed.guard()
        restored['usage']['cost']=0;restored['branch_run']['plan']['measurement']=False
        with self.assertRaises(LimitExceeded):Ledger(rt,lambda:None).guard()

    def test_reviewer_reservations_still_account_and_checkpoint_intervals_do_not_stop(self):
        task=self.task();cfg={'input_rate':0,'output_rate':0}
        reservation=reserve(task,cfg,[{'role':'user','content':'Evidence'*1000}],[], 'reviewer')
        self.assertGreater(task['usage']['reviewer']['tokens'],50)
        self.assertEqual(reservation['completion_tokens'],2048)
        task.update(requests=['Work'],prompt='Work',patch='',request_worker_turns=500)
        rt=Runtime(task);rt.step_turns=999;rt.guard=lambda:None
        engine = Engine.__new__(Engine)
        engine.refresh_changes = Mock()
        engine.recover_worker_stall = Mock(return_value=True)
        engine.checkpoint_boundary(rt)
        engine.recover_worker_stall.assert_called_once()
        self.assertEqual(rt.step_turns, 0)
        self.assertEqual(task['request_worker_turns'], 500)
        task['branch_run']['plan']['measurement']=False
        with self.assertRaises(BudgetError): reserve(task,cfg,[],[],'reviewer')

    def test_check_without_deadline_still_honors_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); workspace=Workspace(root);stop=threading.Event()
            result=workspace.run_checks([sys.executable,'-c','print("real check")'],stop,timeout=None)
            self.assertTrue(result['passed']);self.assertIn('real check',result['output'])
            stop.set();result=workspace.run_checks([sys.executable,'-c','import time; time.sleep(10)'],stop,timeout=None)
            self.assertFalse(result['passed']);self.assertEqual(result['reason'],'cancelled')

    def test_measurement_must_be_explicit_and_cannot_change_after_authorization(self):
        plan={'items':[{'id':'one','title':'One','instructions':'Work','acceptance_criteria':['Works']}],'limits':{'dollars':0},'measurement':True}
        self.assertTrue(validate_plan(plan)['measurement'])
        with self.assertRaises(ValueError): validate_plan(dict(plan,measurement='true'))
        run={'authorization':{'contract':{'plan':dict(plan,measurement=False)}},'plan':plan,'limits':plan['limits']}
        with self.assertRaisesRegex(ValueError,'measurement'):authorization_run(run)


class MeasurementOutputTests(LocalCase):
    def test_zero_cost_measurement_uses_provider_default_and_reconciles_actual_tokens(self):
        task=self.fixture(paid=True);task['branch_run']={'id':'measurement-fixture','plan':{'measurement':True}}
        for cfg in task['providers'].values():cfg.update(input_rate=0,output_rate=0)
        provider=Mock();provider.complete.return_value=({'role':'assistant','content':'Done'}, {'prompt_tokens':10,'completion_tokens':9000,'cost':0})
        self.engine.provider_factory=lambda role,config:provider
        self.engine._request(Runtime(task),[{'role':'user','content':'Work'}],[],'worker',purpose='branch_planning')
        self.assertIsNone(provider.complete.call_args.args[2])
        self.assertEqual(task['usage']['worker']['tokens'],9010)
        self.assertEqual(task['request_metrics'][-1]['output_limit_basis'],'provider_default')
        self.engine._request(Runtime(task),[],[],'worker',purpose='probe')
        self.assertEqual(provider.complete.call_args.args[2],1024)
        task['branch_run']['plan']['measurement']=False
        task['branch_run']['plan']['uncapped_work']=True
        self.engine._request(Runtime(task),[],[],'worker',purpose='branch_planning')
        self.assertEqual(provider.complete.call_args.args[2],task['limits']['output_tokens'])

    def test_wire_request_omits_output_cap_only_when_none(self):
        provider=ChatProvider({'base_url':'http://127.0.0.1:1234/v1','model':'fixture','key_env':'TEST_UNUSED'})
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.return_value=json.dumps({'choices':[{'message':{'role':'assistant','content':'Hi'}}],'usage':{'prompt_tokens':1,'completion_tokens':2}}).encode()
        with patch('cheapos.providers.build_opener') as build:
            build.return_value.open.return_value=response
            provider.complete([],[],None)
            self.assertNotIn('max_tokens',json.loads(build.return_value.open.call_args.args[0].data))
            provider.complete([],[],256)
            self.assertEqual(json.loads(build.return_value.open.call_args.args[0].data)['max_tokens'],256)


class MeasurementExecutionTests(unittest.TestCase):
    setUp=execution.BranchExecutionTests.setUp
    run_job=execution.BranchExecutionTests.run_job
    def test_real_three_item_run_exceeds_small_nominal_limits(self):
        self.values['plan']['measurement']=True
        task=self.run_job({'working_seconds':1,'worker_turns':1,'requests':8,'reviewer_tokens':2048})
        run=task['branch_run']
        self.assertEqual(run['status'],'ready_for_merge',task.get('error'))
        self.assertEqual(len(run['completed_operations']),3)
        self.assertGreater(run['consumption']['working_seconds'],1)
        self.assertGreater(run['consumption']['worker_turns'],1)
        self.assertGreater(run['consumption']['requests'],8)
        self.assertGreater(run['consumption']['worker_tokens'],0)
        self.assertGreater(run['consumption']['check_seconds'],0)
