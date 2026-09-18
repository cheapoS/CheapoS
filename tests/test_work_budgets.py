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

    def test_review_reservation_names_the_selected_budget_and_paid_cap_still_binds(self):
        from cheapos.providers import reserve
        config={'model':'m','input_rate':0,'output_rate':0}
        task={'limits':limits_from({'work_policy_version':2,'work_review_tokens':0,'response_tokens':'automatic'}),'usage':{'cost':0,'uncertain_requests':0,'worker':{'tokens':0,'cost':0},'reviewer':{'tokens':0,'cost':0}}}
        with self.assertRaises(BudgetError) as caught:reserve(task,config,[{'role':'user','content':'Review'}],[],'reviewer')
        self.assertEqual(caught.exception.limit_hit['key'],'work_review_tokens')
        task['limits'].update(work_review_tokens=None,dollars=0)
        with self.assertRaises(BudgetError):reserve(task,{**config,'input_rate':1},[],[],'worker')

    def test_adaptive_check_deadline_uses_exact_command_and_explicit_cap_is_binding(self):
        from cheapos.request_budget import verification
        task={'limits':limits_from({'verification_seconds':'automatic'}), 'checks':[{'command':['test'], 'outcome':'process_timeout','allowed_seconds':360}]}
        self.assertEqual(verification(task,['test']),720)
        self.assertEqual(verification(task,['other']),task['limits']['check_seconds'])
        task['limits']['verification_seconds']=5
        self.assertEqual(verification(task,['test']),5)

    def test_output_context_reservation_agree_when_money_reduces_allowance(self):
        from cheapos.providers import reserve
        from cheapos.context_budget import decision
        task={'limits':limits_from({'dollars':.001,'response_tokens':'automatic'}),'usage':{'cost':0,'uncertain_requests':0,'worker':{'tokens':0,'cost':0}}}
        config={'model':'paid','input_rate':0,'output_rate':10}
        model={'context_length':32000,'max_output_tokens':8192}
        messages=[{'role':'user','content':'task'}]
        chosen=resolve(task,config,model,messages=messages,tools=[],role='worker')
        self.assertEqual(chosen['tokens'],100)
        self.assertEqual(decision(task,messages,[],config,model)['output_reserve_tokens'],100)
        reservation=reserve(task,{**config,'_effective_output_tokens':chosen['tokens']},messages,[],'worker')
        self.assertEqual(reservation['completion_tokens'],100)
        self.assertLessEqual(task['usage']['cost'],task['limits']['dollars'])
