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
        engine.store.get.return_value=task;engine.admission.integration.return_value=nullcontext()
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
