import json
import unittest
from cheapos.working_state import project, update

class WorkingStateTests(unittest.TestCase):
    def test_restart_corrections_and_claims(self):
        task={'prompt':'Add restart','requests':['Add restart'],'status':'running','events':[{'kind':'steer','detail':'Wait for readiness'}]}
        update(task,{'steps':[{'id':'endpoint','text':'Endpoint','status':'done'},{'id':'ready','text':'Check readiness','status':'working'}], 'next_action':'Wire readiness check', 'references':[0]})
        restored=json.loads(json.dumps(task));value=project(restored)
        self.assertEqual(value['next_action'],'Wire readiness check')
        self.assertEqual(value['corrections'][0]['text'],'Wait for readiness')
        self.assertEqual(restored['status'],'running');self.assertNotIn('checks',restored)
        restored['patch']='new';self.assertTrue(project(restored)['references'][0]['historical'])
    def test_reject_authority_and_isolate_items(self):
        task={'prompt':'Job','branch_run':{'current_item_id':'a'}}
        update(task,{'next_action':'Implement a'})
        before=json.dumps(task,sort_keys=True)
        for args in ({'approved':True},{'steps':[{'id':'x','text':'x','status':'approved'}]},{'references':[-1]}):
            with self.assertRaises(ValueError):update(task,args)
            self.assertEqual(json.dumps(task,sort_keys=True),before)
        task['branch_run']['current_item_id']='b';self.assertNotIn('next_action',project(task))
