"""Planning authorization isolation using dictionaries and an inert ledger."""
import copy
import threading
import unittest
from types import SimpleNamespace

from cheapos.branch_budget import Ledger, LimitExceeded
from cheapos.branch_controller import restore_planning_allowance, run_limits
from cheapos.engine import limits_from


class PlanningAllowanceTests(unittest.TestCase):
    def task(self):
        planning=run_limits({},3)
        original=limits_from({'dollars':planning['dollars'],'run_minutes':15,'reviewer_tokens':planning['reviewer_tokens'],'output_tokens':planning['output_tokens']})
        return {'planning_limits':planning,'planning_task_limits':original,'planning_request':{'measurement':False},
                'limits':limits_from({'dollars':10,'run_minutes':100}),
                'branch_run':{'limits':run_limits({'dollars':10,'requests':1000},3),'plan':{'measurement':True,'limits':{}},
                              'consumption':{'requests':4,'working_seconds':14,'dollars':0},
                              'budget_ledger':{'version':1,'request_ids':['old-request'],'observed':{}},
                              'inputs':{'prompt':'Original scope','hash':'captured'}},
                'usage':{'cost':0,'uncertain_requests':1,'estimated_requests':0,'worker':{'tokens':0,'cost':0},'reviewer':{'tokens':0,'cost':0},'planner':{'tokens':100,'cost':0}},
                'request_metrics':[{'id':'old-request','role':'planner'}],'worker_turns':0,'tool_actions':0,'checks':[],
                'providers':{'planner':{'model':'captured','base_url':'https://gateway.example/v1'}},'access_policy':{'connection_revision':'captured'}}

    def test_execution_edits_never_enlarge_captured_planning_allowance_or_reset_usage(self):
        task=self.task();before=copy.deepcopy(task)
        restore_planning_allowance(task)
        self.assertEqual(task['limits'],before['planning_task_limits'])
        self.assertEqual(task['branch_run']['limits'],before['planning_limits'])
        self.assertEqual(task['branch_run']['plan']['limits'],before['planning_limits'])
        self.assertFalse(task['branch_run']['plan'].get('measurement',False))
        for key in ('usage','request_metrics','providers','access_policy'):
            self.assertEqual(task[key],before[key])
        for key in ('consumption','budget_ledger','inputs'):
            self.assertEqual(task['branch_run'][key],before['branch_run'][key])
        restored=copy.deepcopy(task);restore_planning_allowance(task)
        self.assertEqual(task,restored)
        task['usage']['cost']=.01
        runtime=SimpleNamespace(task=task,stop=threading.Event())
        with self.assertRaises(LimitExceeded):Ledger(runtime,lambda:None).guard(next_request=True)

    def test_legacy_snapshot_derives_only_original_planning_settings_and_explicit_measurement(self):
        task=self.task();del task['planning_task_limits'];task['planning_request']['measurement']=True
        restore_planning_allowance(task)
        self.assertEqual(task['limits']['dollars'],0)
        self.assertEqual(task['limits']['output_tokens'],task['planning_limits']['output_tokens'])
        self.assertEqual(task['limits']['run_minutes'],15)
        self.assertTrue(task['branch_run']['plan']['measurement'])
        self.assertEqual(task['usage']['planner']['tokens'],100)

    def test_malformed_or_conflicting_saved_authorization_fails_before_mutating(self):
        for changes in ({'planning_task_limits':{}},{'planning_task_limits':{'dollars':10}},
                        {'planning_limits':{'dollars':0}}, {'planning_request':{'measurement':'true'}}):
            task=self.task();task.update(changes);before=copy.deepcopy(task)
            with self.subTest(changes=changes),self.assertRaises((ValueError,KeyError,TypeError)):
                restore_planning_allowance(task)
            self.assertEqual(task,before)
        task=self.task();task['planning_task_limits']['dollars']=10;before=copy.deepcopy(task)
        with self.assertRaises(ValueError):restore_planning_allowance(task)
        self.assertEqual(task,before)
