import copy
import threading
import unittest
from types import SimpleNamespace

from cheapos import branch_completion as completion
from cheapos.branch_authorization import ProposalRegistry
from cheapos.model_pool import FreeModelPool
from cheapos.workspace import git
import test_branch_final as fixtures


class BranchCompletionTests(unittest.TestCase):
    authorize = fixtures.BranchFinalTests.authorize
    receipt = fixtures.BranchFinalTests.receipt
    save = fixtures.BranchFinalTests.save
    checks = fixtures.BranchFinalTests.checks
    request = fixtures.BranchFinalTests.request

    def setUp(self):
        fixtures.BranchFinalTests.setUp(self)
        self.run.update(status='finalizing', limits={'dollars':0}, amendments=[], original_request='Implement', inputs={})
        self.run['plan']['limits']={'dollars':0}
        import shlex
        self.run['plan']['final_checks']=[shlex.join(c) if isinstance(c,list) else c for c in self.run['plan']['final_checks']]
        self.run['authorization']={'id':'original','status':'active','contract':{'plan':copy.deepcopy(self.run['plan']),'plan_revision':self.run['plan_revision']}}
        self.run['authorization_ref']='original'
        self.task.update(id='task', status='running', events=[])
        self.saved_task=copy.deepcopy(self.task)
        def save_task(task): self.saved_task=copy.deepcopy(task)
        self.engine.store=SimpleNamespace(save=save_task,get=lambda _:copy.deepcopy(self.saved_task))
        self.engine.lock=threading.RLock();self.engine.runtimes={}
        self.engine.gateway=SimpleNamespace(pool=FreeModelPool(self.root/'state'))
        self.engine.require_active_task=lambda _:None
        self.engine.event=lambda task,kind,title,detail:task['events'].append({'kind':kind,'title':title,'detail':detail})
        self.controller=SimpleNamespace(engine=self.engine,final_proposals=ProposalRegistry(),
            validate_authority=lambda task,run:completion.authorization_run(run),launch=lambda _:copy.deepcopy(self.saved_task))
        self.controller.resume=lambda task_id,values:{'needs_consent':False,'task':self.controller.launch(task_id)}
        self.engine.branch=self.controller
        self.run.update(events=[],event_sequence=0)
        self.engine.store.save(self.task)

    def finalize(self):
        self.assertTrue(completion.finalize(self.engine,self.runtime))
        return self.saved_task

    def test_final_preview_is_read_only_and_merge_is_explicit_idempotent(self):
        self.finalize()
        calls=len(self.requests); checks=len(self.task['checks']); before=git(self.source,'rev-parse','HEAD')
        preview=completion.preview(self.controller,'task')
        self.assertTrue(preview['merge_available'])
        self.assertIn('+two',preview['diff'])
        page=completion.diff(self.controller,'task',{'preview_id':preview['preview_id'],'cursor':0})
        self.assertEqual(page['diff'],preview['diff'])
        self.assertEqual((len(self.requests),len(self.task['checks'])),(calls,checks))
        self.assertEqual(git(self.source,'rev-parse','HEAD'),before)
        with self.assertRaises(ValueError):completion.merge(self.controller,'task',{'preview_id':preview['preview_id'],'approved':False})
        decision={'preview_id':preview['preview_id'],'approved':True}
        result=completion.merge(self.controller,'task',decision)
        self.assertEqual(result['branch_run']['status'],'merged')
        self.assertEqual(git(self.source,'rev-parse','HEAD').strip(),self.run['expected_feature_tip'])
        self.assertEqual(completion.merge(self.controller,'task',decision),result)

    def test_left_branch_keeps_read_only_diff_without_restoring_authority(self):
        self.finalize()
        self.saved_task['branch_run']['status']='left_on_branch'
        self.saved_task['branch_run']['authorization']['status']='revoked'
        def revoked(task,run):raise ValueError('Run authorization was revoked')
        self.controller.validate_authority=revoked
        preview=completion.preview(self.controller,'task')
        self.assertFalse(preview['merge_available'])
        self.assertIsNone(preview['preview_id'])
        self.assertIn('revoked',preview['blocker'])
        self.assertIn('+two',preview['diff'])
        self.assertIn('+two',completion.diff(self.controller,'task',{'cursor':0})['diff'])
        self.assertEqual(self.saved_task['branch_run']['authorization']['status'],'revoked')
        self.assertEqual(self.controller.final_proposals.proposals,{})

    def test_saved_merge_recovers_after_target_moved_without_second_merge(self):
        from unittest.mock import patch
        from cheapos import branch_merge
        self.finalize();preview=completion.preview(self.controller,'task')
        save=branch_merge._save
        def interrupt(operation,stage,persist):
            save(operation,stage,persist)
            if stage=='target_integrated':raise OSError('Interrupted after target integration')
        with patch.object(branch_merge,'_save',side_effect=interrupt):
            with self.assertRaises(OSError):completion.merge(self.controller,'task',{'preview_id':preview['preview_id'],'approved':True})
        self.assertEqual(self.saved_task['status'],'paused')
        self.assertEqual(self.saved_task['branch_run']['status'],'paused')
        self.assertIn('explicit recovery',self.saved_task['error'])
        self.assertIn('merge_operation',self.saved_task['branch_run'])
        tip=git(self.source,'rev-parse','HEAD')
        result=completion.merge(self.controller,'task',{'approved':True,'recover':True})
        self.assertEqual(result['branch_run']['status'],'merged')
        self.assertEqual(tip,git(self.source,'rev-parse','HEAD'))
        self.assertNotIn('merge_operation',result['branch_run'])

    def test_revision_proposal_retains_history_and_requires_confirmation(self):
        self.finalize()
        result=completion.revise(self.controller,'task',{'message':'Correct the original acceptance failure'})
        proposal=result['revision_proposal']
        self.assertEqual(len(self.saved_task['branch_run']['items']),1)
        self.assertIn('readiness',self.saved_task['branch_run'])
        completion.revise(self.controller,'task',{'proposal_id':proposal['proposal_id'],'approved':True})
        run=self.saved_task['branch_run']
        self.assertEqual(len(run['items']),2)
        self.assertEqual(run['items'][0]['status'],'committed')
        self.assertNotIn('readiness',run)
        self.assertEqual(completion.authorization_run(run)['plan'],run['authorization']['contract']['plan'])
        tampered=copy.deepcopy(run);tampered['plan']['final_checks']=['new command']
        with self.assertRaises(ValueError):completion.authorization_run(tampered)
        run['plan']['items'][-1]['instructions']='Changed unauthorized work'
        with self.assertRaises(ValueError):completion.authorization_run(run)

    def test_automatic_final_revision_has_original_criteria_and_bounded_authority(self):
        self.request_changes=True
        self.assertFalse(completion.finalize(self.engine,self.runtime))
        run=self.saved_task['branch_run']
        self.assertEqual(run['amendments'][0]['origin'],'final_review')
        self.assertEqual(run['items'][-1]['acceptance_criteria'],run['items'][0]['acceptance_criteria'])
        completion.authorization_run(run)
        run['amendments']*=4
        with self.assertRaises(ValueError):completion.authorization_run(run)

    def test_stale_or_cross_task_preview_cannot_merge(self):
        self.finalize();preview=completion.preview(self.controller,'task')
        with self.assertRaises(ValueError):completion.merge(self.controller,'other',{'preview_id':preview['preview_id'],'approved':True})
        self.controller.final_proposals.proposals[preview['preview_id']]['expires']=0
        with self.assertRaises(ValueError):completion.merge(self.controller,'task',{'preview_id':preview['preview_id'],'approved':True})
        self.assertEqual(git(self.source,'rev-parse','HEAD').strip(),self.run['base_sha'])
        (self.source/'code').write_text('uncommitted operator work')
        blocked=completion.preview(self.controller,'task')
        self.assertFalse(blocked['merge_available'])
        self.assertTrue(blocked['blocker'])
        self.assertIn('+two',blocked['diff'])
        self.assertIn('+two',completion.diff(self.controller,'task',{'cursor':0})['diff'])


if __name__=='__main__':unittest.main()
