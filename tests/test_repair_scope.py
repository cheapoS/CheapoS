"""Pure selection and amendment checks; no Git, engines, or model requests."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from cheapos import repair_scope, branch_completion as completion
from cheapos.branch_authorization import digest

class ScopeTests(unittest.TestCase):
    def test_controller_repairs_outlive_proposal_size_without_expanding_authority(self):
        from cheapos import branch_runs
        items=[{'id':str(i),'title':'Check','instructions':'Keep original behavior',
                'acceptance_criteria':['correct behavior'],'required_checks':[]} for i in range(50)]
        plan=branch_runs.validate_plan({'items':items,'final_checks':[],
                                       'limits':{'working_seconds':600,'dollars':0}})
        run=branch_runs.new_run(plan)
        run['authorization']={'contract':{'plan':copy.deepcopy(plan),'plan_revision':1}}
        task={'branch_run':run};engine=SimpleNamespace(store=SimpleNamespace(save=Mock()))
        for index in range(4):
            item=completion._repair_item(run,'Verify original criterion',['49:1'])
            completion._append_repair(engine,task,item,'operator','confirmed',{},['49:1'])
        self.assertEqual(len(run['plan']['items']),54)
        self.assertEqual(completion.authorization_run(run)['plan'],plan)
        self.assertEqual(run['limits'],plan['limits'])
        with self.assertRaisesRegex(ValueError,'1–50'):
            branch_runs.validate_plan(run['plan'])  # HTTP proposals remain bounded.
        duplicate=copy.deepcopy(item)
        with self.assertRaisesRegex(ValueError,'new item ID'):
            completion._append_repair(engine,task,duplicate,'operator','confirmed',{},['49:1'])
        tampered=copy.deepcopy(run);tampered['amendments'][0]['item']['instructions']='Different scope'
        with self.assertRaisesRegex(ValueError,'repair item changed'):
            completion.authorization_run(tampered)

    def test_late_and_duplicate_text_keep_original_identity(self):
        items=[{'id':str(i),'acceptance_criteria':['same',*[f'criterion {i}-{j}' for j in range(3)]], 'required_checks':['check']} for i in range(5)]
        plan={'items':items,'final_checks':['check'],'limits':{}}
        run={'id':'run','authorization':{'contract':{'plan':plan,'plan_revision':1}},'plan':copy.deepcopy(plan),'plan_revision':1,'limits':{},'items':items}
        refs=repair_scope.select(run,['4:4','0:1','1:1'])
        self.assertEqual([r['id'] for r in refs],['4:4','0:1','1:1'])
        item=completion._repair_item(run,'Repair the final criterion',['4:4'])
        self.assertEqual(item['acceptance_criteria'],['criterion 4-2'])
        self.assertEqual(item['revision_of'],'4')
        with self.assertRaises(ValueError):completion._repair_item(run,'Ambiguous repair')
        with self.assertRaises(ValueError):repair_scope.select(run,['unknown:1'])
        observation={'candidate_id':'candidate','manifest_id':'manifest'}
        refs=repair_scope.select(run,['4:4'])
        amendment={'run_id':'run','item':item,'item_digest':digest(item),'origin':'final_review','authorization_id':digest(observation),'requirement_refs':refs,'observation':observation,'scope_digest':digest({'refs':refs,'observation':observation})}
        run.update(amendments=[amendment],plan_revision=2)
        run['plan']['items'].append(item)
        self.assertEqual(completion.authorization_run(run)['plan'],plan)
        amendment['requirement_refs'][0]['criterion']='changed'
        with self.assertRaises(ValueError):completion.authorization_run(run)
