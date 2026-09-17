import copy
import unittest
from unittest.mock import patch
from cheapos.branch_workspace import _tip
import test_branch_start as fixtures


class BranchReprepareTests(unittest.TestCase):
    setUp=fixtures.BranchStartTests.setUp

    def test_same_task_preserves_planning_accounting_and_invalidates_old_token(self):
        proposal=self.engine.branch.prepare(self.values);task_id=proposal['task_id']
        task=self.engine.store.get(task_id)
        task['usage']['worker']['tokens']=123
        task['request_metrics']=[{'id':'planned-request'}]
        task['branch_run']['consumption'].update(requests=2,working_seconds=11)
        task['branch_run']['budget_ledger']={'version':1,'request_ids':['planned-request'],'observed':{'worker_turns':1}}
        self.engine.store.save(task)
        values=copy.deepcopy(self.values);values['plan']['items'][0]['instructions']='Implement the clarified original work'
        values['feature_ref']='refs/heads/feature/edited'
        edited=self.engine.branch.reprepare(task_id,values)
        saved=self.engine.store.get(task_id)
        self.assertEqual(edited['task_id'],task_id)
        self.assertEqual(len(self.engine.store.list()),1)
        self.assertEqual(saved['usage'],task['usage'])
        self.assertEqual(saved['request_metrics'],task['request_metrics'])
        self.assertEqual(saved['branch_run']['consumption'],task['branch_run']['consumption'])
        self.assertEqual(saved['branch_run']['budget_ledger'],task['branch_run']['budget_ledger'])
        self.assertEqual(saved['branch_run']['inputs'],task['branch_run']['inputs'])
        self.assertEqual(saved['branch_run']['plan_revision'],2)
        self.assertNotIn(proposal['proposal_id'],self.engine.branch.proposals.proposals)
        with self.assertRaises(ValueError):self.engine.branch.authorize(task_id,{'proposal_id':proposal['proposal_id'],'approved':True})
        self.assertIsNone(_tip(self.source,self.values['feature_ref']))
        self.assertIsNone(_tip(self.source,values['feature_ref']))
        saved['planning_policy']=copy.deepcopy(saved['branch_run']['model_policy'])
        for tips,message in (([None],'Integration target'),(['base','existing'],'Feature branch')):
            with patch('cheapos.branch_controller.work._tip',side_effect=tips),self.assertRaisesRegex(ValueError,message):
                self.engine.branch.prepare(values,planning_task=saved)
            self.assertEqual(self.engine.store.get(task_id)['usage'],saved['usage'])
        with patch('cheapos.branch_controller.work.prepare', side_effect=AssertionError('Existing snapshot must be reused')):
            replanned=self.engine.branch.prepare(values,planning_task=saved)
        after=self.engine.store.get(task_id)
        self.assertEqual(after['workspace'],saved['workspace'])
        self.assertEqual(after['usage'],saved['usage'])
        self.assertEqual(after['branch_run']['consumption'],saved['branch_run']['consumption'])
        self.assertTrue(replanned['readiness']['ready'])
        edited=replanned
        self.engine.branch.launch=lambda identity:self.engine.store.get(identity)
        started=self.engine.branch.authorize(task_id,{'proposal_id':edited['proposal_id'],'approved':True,'full_suite_approved':True})
        self.assertEqual(started['branch_run']['consumption']['requests'],2)
        self.assertEqual(_tip(self.source,values['feature_ref']),saved['branch_run']['base_sha'])

    def test_invalid_edit_does_not_discard_draft_or_renew_allowance(self):
        proposal=self.engine.branch.prepare(self.values);task_id=proposal['task_id']
        before=self.engine.store.get(task_id)
        for changes in ({'prompt':'Different input'},{'feature_ref':'refs/heads/main'},{'base_ref':'refs/heads/other'},{'inputs':{'document':'different'}}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.engine.branch.reprepare(task_id,{**self.values,**changes})
            self.assertEqual(before,self.engine.store.get(task_id))
        self.assertIn(proposal['proposal_id'],self.engine.branch.proposals.proposals)
        before['branch_run']['consumption']['requests']=8;self.engine.store.save(before)
        lower=copy.deepcopy(self.values);lower['plan']['limits']['requests']=4
        with self.assertRaisesRegex(ValueError,'already consumed'):self.engine.branch.reprepare(task_id,lower)
        self.assertEqual(self.engine.store.get(task_id)['branch_run']['consumption']['requests'],8)


if __name__=='__main__':unittest.main()
