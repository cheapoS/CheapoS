import copy
import unittest
from cheapos.engine import limits_from
from cheapos.work_budgets import guard, effective
from cheapos.request_budget import resolve
from cheapos.providers import BudgetError

class WorkBudgetTests(unittest.TestCase):
    def test_independent_caps_override_legacy_uncapped_and_survive_reload(self):
        task={'limits':limits_from({'uncapped_work':True,'work_policy_version':2,'work_requests':2,'work_tools':None}),
              'session_actions':{'coverage':'complete','counts':{'worker':2,'tools':50}}, 'usage':{}}
        with self.assertRaises(BudgetError):guard(task,additions={'work_requests':1})
        changed=copy.deepcopy(task);changed['limits']['work_requests']=3
        guard(changed,additions={'work_requests':1})
        self.assertEqual(changed['session_actions'],task['session_actions'])
        self.assertIsNone(effective(task)['work_tools'])
        task['limits']['work_requests']=0
        with self.assertRaises(BudgetError):guard(task)
        for value in (-1, True, 1.5, float('inf')):
            with self.assertRaises(ValueError):limits_from({'work_requests':value})

    def test_output_capacity_is_explicit_and_unknown_remains_unknown(self):
        task={'limits':limits_from({'response_tokens':'automatic'})}
        self.assertEqual(resolve(task,{}, {'max_output_tokens':8192})['tokens'],8192)
        unknown=resolve(task,{}, {'max_output_tokens':8192,'metadata_evidence':{'stale':True}})
        self.assertIsNone(unknown['capacity_tokens'])
        task['limits']['response_tokens']=1000
        self.assertEqual(resolve(task,{}, {'max_output_tokens':8192})['tokens'],1000)
