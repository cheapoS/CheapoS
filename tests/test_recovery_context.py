import hashlib
import unittest
from cheapos.recovery_context import packet

class RecoveryContextTests(unittest.TestCase):
    def test_preserves_direction_completed_fix_and_scoped_receipts(self):
        task={'prompt':'Original bug','patch':'fixed','workspace_generation':2,
              'branch_run':{'current_item_id':'repair','guidance':[{'item_id':'repair','message':'Verify the focused route test'}],
                            'items':[{'id':'fix','status':'committed','outcome_summary':'Route fixed'}]},
              'events':[{'kind':'assistant','item_id':'repair','detail':'Frontend and backend routes already match.'}]*5,
              'checks':[{'command':['python3','-m','unittest','tests.test_empty_trash'],'passed':True,
                         'digest':hashlib.sha256(b'fixed').hexdigest(),'verification_identity':'identity','generation':2}]}
        result=packet(task)
        self.assertEqual(result['latest_operator_direction'],'Verify the focused route test')
        self.assertEqual(len(result['prior_worker_statements_unverified']),1)
        self.assertEqual(result['completed_items'][0]['id'],'fix')
        self.assertIn('submit checkpoint',result['next_step'])
        self.assertIn('Do not broaden',result['validation_policy'])
        task['patch']='changed again'
        self.assertNotIn('A check passed for this patch',packet(task)['next_step'])
        task['patch']='fixed';task['workspace_generation']=3
        self.assertNotIn('A check passed for this patch',packet(task)['next_step'])
