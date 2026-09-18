"""Small controller regressions; real Git recovery is covered by a disposable smoke run."""
import copy
import threading
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch
from cheapos import branch_completion as completion


class UpdateControllerTests(unittest.TestCase):
    def fixture(self):
        run={'status':'paused','items':[{'status':'committed','evidence':{'passed':True}}],
             'workspace_mapping':{'source':'source'},'expected_feature_tip':'old','target_ref':'refs/heads/main',
             'readiness':{'id':'review'},'final_evidence':{'approved':True}}
        task={'branch_run':run,'checks':[{'passed':True}], 'pending_review':{'old':True}}
        engine=SimpleNamespace(store=Mock(),lock=threading.RLock(),admission=Mock(),event=Mock())
        engine.store.get.return_value=task;engine.admission.integration.side_effect=lambda *a:nullcontext();engine.admission.repository.side_effect=lambda *a:nullcontext()
        controller=SimpleNamespace(engine=engine,validate_authority=Mock(),resume=Mock(return_value={'task':task}))
        return controller,task

    def test_update_invalidates_approval_preserves_work_and_rechecks(self):
        controller,task=self.fixture();before=copy.deepcopy(task)
        finished={'new_tip':'new','private_new':'private','target_tip':'target'}
        with patch.object(completion,'_task',return_value=task),patch.object(completion,'update_token',return_value='token'),patch('cheapos.branch_update.prepare',return_value=finished),patch('cheapos.branch_update.finish',return_value=finished):
            completion.update_branch(controller,'task',{'approved':True,'update_token':'token'})
        run=task['branch_run']
        self.assertEqual(run['items'],before['branch_run']['items']);self.assertEqual(task['checks'],before['checks'])
        self.assertNotIn('readiness',run);self.assertEqual(run['final_evidence'],{})
        self.assertEqual(run['expected_feature_tip'],'new');self.assertEqual(run['previous_readiness'],[{'id':'review'}])
        controller.resume.assert_called_once_with('task',{})

    def test_stale_or_unapproved_update_does_not_touch_git(self):
        controller,task=self.fixture()
        with patch.object(completion,'_task',return_value=task),patch.object(completion,'update_token',return_value='new'),patch('cheapos.branch_update.prepare') as prepare:
            for values in ({'approved':False,'update_token':'new'},{'approved':True,'update_token':'old'}):
                with self.assertRaises(ValueError):completion.update_branch(controller,'task',values)
            prepare.assert_not_called();controller.resume.assert_not_called()

    def test_incomplete_work_cannot_be_updated(self):
        controller,task=self.fixture();task['branch_run']['items'][0]['status']='working'
        with patch.object(completion,'_task',return_value=task),patch('cheapos.branch_update.prepare') as prepare:
            with self.assertRaises(ValueError):completion.update_branch(controller,'task',{'approved':True,'update_token':'token'})
            prepare.assert_not_called()

    def test_unapproved_update_receipt_cannot_extend_item_ancestry(self):
        from cheapos.branch_update import advance_receipts, receipt_digest
        run={'workspace_mapping':{'source':'source','workspace':'private'},'feature_ref':'feature','target_ref':'main'}
        op={'stage':'completed','old_tip':'old','new_tip':'new','approved':False}
        op['digest']=receipt_digest(op)
        with self.assertRaisesRegex(ValueError,'approval'):
            advance_receipts(run,'old','private',[op])
        op['approved']=True
        with self.assertRaisesRegex(ValueError,'approval'):
            advance_receipts(run,'old','private',[op])

    def test_current_update_reuses_valid_review_and_duplicate_receipt(self):
        controller,task=self.fixture()
        task['branch_run']['workspace_mapping']['workspace_head']='private'
        before=copy.deepcopy(task['branch_run']['final_evidence'])
        current={'state':'already_current','updated':False,'target_tip':'target','private_old':'private'}
        with patch.object(completion,'_task',return_value=task), patch.object(completion,'update_token',return_value='token'), patch('cheapos.branch_update.prepare',return_value=current) as prepare, patch.object(completion.final,'validate',return_value=True), patch.object(completion.work,'validate_owned'), patch.object(completion.work,'_tip',return_value='target'):
            first=completion.update_branch(controller,'task',{'approved':True,'update_token':'token'})
            second=completion.update_branch(controller,'task',{'approved':True,'update_token':'token'})
        self.assertFalse(first['updated']);self.assertEqual(second['operation_id'],first['operation_id'])
        self.assertEqual(first['state'],'already_current');prepare.assert_called_once()
        controller.resume.assert_not_called()
        self.assertEqual(task['branch_run']['final_evidence'],before)
        self.assertNotIn('target_update_history',task['branch_run'])
        self.assertEqual(task['branch_run']['status'],'ready_for_merge')

    def test_current_update_continues_missing_review_and_rejects_target_movement(self):
        controller,task=self.fixture()
        task['branch_run']['workspace_mapping']['workspace_head']='private'
        current={'state':'already_current','updated':False,'target_tip':'target','private_old':'private'}
        with patch.object(completion,'_task',return_value=task), patch.object(completion,'update_token',return_value='token'), patch('cheapos.branch_update.prepare',return_value=current), patch.object(completion.final,'validate',side_effect=ValueError('stale')), patch.object(completion.work,'validate_owned'), patch.object(completion.work,'_tip',return_value='moved'):
            result=completion.update_branch(controller,'task',{'approved':True,'update_token':'token'})
            self.assertFalse(result['updated']);controller.resume.assert_called_once()
            with self.assertRaisesRegex(ValueError,'Branches changed'):
                completion.update_branch(controller,'task',{'approved':True,'update_token':'token'})
        self.assertEqual(task['branch_run']['update_result']['phase'],'rechecking')
