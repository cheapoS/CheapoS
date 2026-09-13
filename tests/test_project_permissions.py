from cheapos.verification import evidence_identity
import shlex
from pathlib import Path
from unittest.mock import Mock
from cheapos.engine import Engine
from test_engine import LocalCase, call
import test_permissions as exact_permissions
from test_permissions import COMMAND, OTHER


class ProjectPermissionTests(LocalCase):
    task=exact_permissions.SessionPermissionTests.task
    replies=exact_permissions.SessionPermissionTests.replies
    waiting=exact_permissions.SessionPermissionTests.waiting

    def grant(self,task):
        self.replies([call('run_checks',{'command':COMMAND}),{'content':'Checked.'}])
        self.engine.start(task['id']);request=self.waiting(task)
        pending=self.engine.store.get(task['id'])['pending_approval']
        self.assertEqual(pending['profile']['runner'],'unittest')
        self.engine.approve_check(task['id'],True,approval_id=request,scope='project_tests_session')
        self.assertEqual(self.finish(task)['status'],'awaiting_reply')
        return self.engine.session_permissions(task['id'])['project_grants'][0]['id']

    def test_two_selectors_followup_and_same_project_copy_share_one_grant(self):
        task=self.task();self.grant(task)
        self.replies([call('run_checks',{'command':OTHER}),{'content':'Checked another selector.'}])
        self.engine.start(task['id'],{'message':'Check the other test.'})
        result=self.finish(task)
        self.assertEqual(len(result['checks']),2)
        self.assertEqual(sum(e['title']=='Permission needed to run the verification command' for e in result['events']),1)
        self.engine.configure({role:{'base_url':'http://127.0.0.1:1/v1','model':'fixture','input_rate':0,'output_rate':0} for role in ['worker','reviewer']})
        other=self.engine.create({'repository':task['source'],'prompt':'Check the same project','conversational':True})
        self.replies([call('run_checks',{'command':OTHER}),{'content':'Checked.'}])
        self.engine.start(other['id']);result=self.finish(other)
        self.assertEqual(len(result['checks']),1)
        self.assertFalse(any(e['title']=='Permission needed to run the verification command' for e in result['events']))

    def test_revoke_restart_and_configuration_changes_remove_matching_permission(self):
        task=self.task();grant_id=self.grant(task)
        registry=self.engine.project_test_grants
        current=self.engine.store.get(task['id']);argv=shlex.split(OTHER)
        self.assertTrue(registry.authorize(current,argv)[0])
        (Path(current['workspace'])/'test_added.py').write_text('# ordinary test edit\n')
        self.assertTrue(registry.authorize(current,argv)[0])
        (Path(current['workspace'])/'setup.cfg').write_text('[unittest]\n')
        self.assertIsNone(registry.authorize(current,argv)[0])
        (Path(current['workspace'])/'setup.cfg').unlink()
        self.engine.revoke_project_permission(task['id'],grant_id)
        self.assertIsNone(registry.authorize(current,argv)[0])
        self.engine.shutdown();self.engine=Engine(self.engine.store.root)
        self.assertEqual(self.engine.session_permissions(task['id'])['project_grants'],[])

    def test_replaced_copy_source_and_other_project_cannot_inherit(self):
        task=self.task();self.grant(task);registry=self.engine.project_test_grants
        current=self.engine.store.get(task['id']);argv=shlex.split(COMMAND)
        other=self.fixture();current['workspace']=other['workspace']
        self.assertIsNone(registry.authorize(current,argv)[0])
        self.assertIsNone(registry.proposal(current,argv))
        self.assertIsNone(registry.authorize(other,argv)[0])
        current=self.engine.store.get(task['id'])
        source=Path(current['source']);(source/'.git').rename(source/'.git-old')
        (source/'.git').mkdir()
        self.assertIsNone(registry.authorize(current,argv)[0])
        self.assertIsNone(registry.proposal(current,argv))

    def test_stale_profile_and_scope_cannot_be_approved(self):
        task=self.task();self.replies([call('run_checks',{'command':COMMAND})])
        self.engine.start(task['id']);request=self.waiting(task)
        with self.assertRaises(ValueError):self.engine.approve_check(task['id'],True,scope='project_tests_session')
        with self.assertRaises(ValueError):self.engine.approve_check(task['id'],True,approval_id=request,scope='anything')
        (Path(task['workspace'])/'setup.cfg').write_text('[changed]\n')
        with self.assertRaisesRegex(ValueError,'profile changed'):
            self.engine.approve_check(task['id'],True,approval_id=request,scope='project_tests_session')
        self.engine.approve_check(task['id'],False,approval_id=request,scope='once');self.finish(task)
        self.assertEqual(self.engine.session_permissions(task['id'])['project_grants'],[])

    def test_revoke_invalidates_older_unsubmitted_proposal(self):
        task=self.task();grant_id=self.grant(task);registry=self.engine.project_test_grants
        task=self.engine.store.get(task['id'])
        pending={'command':shlex.split(COMMAND),'directory':task['workspace'],'profile':registry.proposal(task,shlex.split(COMMAND))}
        self.engine.revoke_project_permission(task['id'],grant_id)
        with self.assertRaisesRegex(ValueError,'profile changed'):registry.approve(task,pending)


    def test_reconciliation_registers_new_copy_without_widening_grant(self):
        import hashlib
        from cheapos.workspace import Workspace, git
        task=self.task();grant_id=self.grant(task)
        task=self.engine.store.get(task['id'])
        Workspace(task['workspace']).write_file('saved.txt','Task edit\n')
        self.engine.refresh_changes(task)
        digest=hashlib.sha256(task['patch'].encode()).hexdigest()
        task.update(status='approved', checks=[{'passed':True,'digest':digest, 'verification_identity': evidence_identity(task)}],
                    checkpoints=[{'decision':'APPROVE','diff':task['patch'], 'verification_identity': evidence_identity(task)}])
        self.engine.store.save(task)
        source=Path(task['source']);(source/'other.txt').write_text('Concurrent edit\n')
        git(source,'add','other.txt')
        git(source,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Concurrent work')
        result=self.engine.reconcile_project(task['id'],{'patch_digest':digest})
        self.assertNotEqual(result['workspace'],task['workspace'])
        self.assertEqual(self.engine.project_test_grants.authorize(result,shlex.split(COMMAND))[0],grant_id)
