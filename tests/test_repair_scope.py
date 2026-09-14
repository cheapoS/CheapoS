"""Pure selection and amendment checks; no Git, engines, or model requests."""
import copy
import unittest
from cheapos import repair_scope, branch_completion as completion
from cheapos.branch_authorization import digest

class ScopeTests(unittest.TestCase):
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
