"""Network-free planning recovery regression cases."""
import copy
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from cheapos import branch_planner as planner
from cheapos.branch_operator import capabilities, recover


class PlanningRecoveryTests(unittest.TestCase):
    def test_unapproved_recovery_does_not_inspect_missing_worker_or_reviewer(self):
        task={'id':'t','planning_request':{'prompt':'keep this'},'branch_run':{'inputs':{'prompt':'keep this'}},'providers':{'worker':None,'reviewer':None},'gateway_connections':[], 'usage':{'cost':0.1}}
        saved=copy.deepcopy(task)
        engine=SimpleNamespace(lock=threading.RLock(),runtimes={},require_active_task=Mock(),store=SimpleNamespace(get=lambda _:copy.deepcopy(saved),save=Mock()),connections=SimpleNamespace())
        controller=SimpleNamespace(engine=engine,plan=Mock(),proposals=SimpleNamespace(lock=threading.RLock(),proposals={'old':{'task_id':'t'}}))
        from cheapos.server import LocalHandler
        engine.branch=controller
        handler=object.__new__(LocalHandler)
        handler.path='/api/tasks/t/operator-recovery'
        handler.server=SimpleNamespace(engine=engine)
        handler.trusted=Mock(return_value=True);handler.reply=Mock()
        handler.do_GET()
        self.assertTrue(handler.reply.call_args.args[0]['planning'])
        cap=capabilities(controller,'t')
        self.assertTrue(cap['can_retry']);self.assertTrue(cap['planning']);self.assertEqual(cap['planners'],[])
        recover(controller,'t',{'action':'retry'})
        self.assertEqual(controller.plan.call_args.kwargs['planning_task']['usage'],task['usage'])
        self.assertEqual(controller.plan.call_args.kwargs['planning_task']['branch_run'],task['branch_run'])
        self.assertEqual(controller.proposals.proposals,{})

    def test_malformed_planner_handoff_retains_context_and_usage(self):
        inputs={'source':'/fixture','prompt':'original request'};inputs['hash']=planner._digest(inputs)
        task={'planning_limits':{'dollars':0},'execution':{'mode':'remote'},'route':{'base_url':'fixture'},'providers':{'planner':{'model':'bad'}},'usage':{'cost':0}}
        runtime=SimpleNamespace(task=task,stop=threading.Event(),guard=Mock(),failed_models=set())
        requests=[]
        def request(runtime,messages,*args,**kwargs):
            requests.append(copy.deepcopy(messages));task['usage']['cost']+=1
            return {'content':'bad'} if len(requests)<4 else {'ok':True}
        engine=SimpleNamespace(request=request,event=Mock())
        def parse(response,*args):
            if response.get('ok'):return {'items':['valid']}
            raise planner.PlanningResponseError('bad format')
        def select(*args):task['providers']['planner']={'model':'good'}
        with patch.object(planner,'project_context',return_value='context'),patch.object(planner,'_parse',side_effect=parse),patch('cheapos.routing._select_connections',side_effect=select) as selected:
            self.assertEqual(planner.plan(engine,runtime,inputs),{'items':['valid']})
        self.assertEqual(selected.call_count,1);self.assertEqual(task['usage']['cost'],4)
        self.assertEqual(requests[0][:2],requests[-1][:2]);self.assertNotIn('routing_ready',str(requests[-1]))
        self.assertIn('bad',runtime.failed_models)
