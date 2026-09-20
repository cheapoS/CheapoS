import copy
import json
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from cheapos.engine import Engine
from cheapos.workspace import git
from cheapos.branch_workspace import _tip
from test_engine import CONFIG


class BranchStartTests(unittest.TestCase):
    def setUp(self):
        carto = patch('cheapos.carto.Carto.available', return_value=False)
        carto.start()
        self.addCleanup(carto.stop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.source=self.root/'repo';self.source.mkdir()
        git(self.source,'init','-qb','main');git(self.source,'config','user.name','Fixture');git(self.source,'config','user.email','fixture@example.invalid')
        (self.source/'hello.py').write_text('value=1\n')
        # Python 3.13+ rejects discovery with zero tests. Give commit/recovery
        # fixtures real verification instead of relying on an empty suite.
        (self.source/'test_hello.py').write_text(
            'import unittest\nfrom hello import value\n'
            'class HelloTests(unittest.TestCase):\n'
            '    def test_value(self):\n'
            '        self.assertIsInstance(value, int)\n'
            '        self.assertGreater(value, 0)\n')
        git(self.source,'add','.');git(self.source,'commit','-qm','base')
        self.engine=Engine(self.root/'state',fixture_delay=0);self.addCleanup(self.engine.shutdown)
        self.engine.config={'worker':dict(CONFIG,model='worker',input_rate=0,output_rate=0),'reviewer':dict(CONFIG,model='reviewer',input_rate=0,output_rate=0)}
        self.launch=self.engine.branch.launch
        self.engine.branch.launch=lambda task_id:self.engine.store.get(task_id)
        self.engine.save_preferences({'execution':{'mode':'manual'}})
        command=shlex.join([sys.executable,'-m','unittest','discover'])
        self.values={'repository':str(self.source),'base_ref':'refs/heads/main','target_ref':'refs/heads/main','feature_ref':'refs/heads/feature/job',
                     'prompt':'Implement this job','plan':{'items':[{'id':'one','title':'One','instructions':'Implement one','acceptance_criteria':['Works'],'required_checks':[command]}],
                     'limits':{'dollars':0},'final_checks':[command]}}

    def test_prepare_start_once_and_source_unchanged(self):
        (self.source/'hello.py').write_text('dirty\n')
        before=git(self.source,'status','--porcelain'),git(self.source,'write-tree'),git(self.source,'rev-parse','HEAD')
        proposal=self.engine.branch.prepare(self.values)
        self.assertIsNone(_tip(self.source,'refs/heads/feature/job'))
        self.assertEqual(self.engine.runtimes,{})
        self.assertTrue(proposal['readiness']['ready'])
        with self.assertRaisesRegex(ValueError,'Full-suite'):
            self.engine.branch.authorize(proposal['task_id'],{'proposal_id':proposal['proposal_id'],'approved':True})
        self.assertIsNone(_tip(self.source,'refs/heads/feature/job'))
        decision={'proposal_id':proposal['proposal_id'],'approved':True,'full_suite_approved':True}
        with patch('cheapos.unattended_setup.environment.inspect', return_value={'status':'missing','evidence':'Dependency absent.','next_step':'Prepare environment.'}):
            with self.assertRaisesRegex(ValueError,'before Start'):
                self.engine.branch.authorize(proposal['task_id'],decision)
        self.assertIsNone(_tip(self.source,'refs/heads/feature/job'))
        with patch('cheapos.branch_controller.work.create', side_effect=OSError('Synthetic setup interruption')):
            with self.assertRaisesRegex(OSError, 'setup interruption'):
                self.engine.branch.authorize(proposal['task_id'],decision)
        saved=self.engine.store.get(proposal['task_id'])
        self.assertEqual(saved['branch_run']['status'],'awaiting_authorization')
        self.assertTrue(saved['branch_run']['authorization_ref'])
        consent=self.engine.branch.resume(proposal['task_id'],{})
        self.assertTrue(consent['needs_consent'])
        task=self.engine.branch.resume(proposal['task_id'],{'proposal_id':consent['proposal_id'],'approved':True})['task']
        self.assertEqual(task,self.engine.branch.authorize(task['id'],decision))
        self.assertEqual(_tip(self.source,'refs/heads/feature/job'),task['branch_run']['base_sha'])
        self.assertEqual(before,(git(self.source,'status','--porcelain'),git(self.source,'write-tree'),git(self.source,'rev-parse','HEAD')))
        self.assertTrue(self.engine.branch.scopes.authorize(task,task['check_command']))
        self.engine.branch.validate_authority(task,task['branch_run'])
        self.engine.branch.revoke(task['id'])
        with self.assertRaises(ValueError):self.engine.branch.validate_authority(self.engine.store.get(task['id']),self.engine.store.get(task['id'])['branch_run'])

    def test_tampering_forgery_and_changed_scope_do_not_create_branch(self):
        proposal=self.engine.branch.prepare(self.values);task_id=proposal['task_id']
        for values in ({'proposal_id':'forged','approved':True},{'proposal_id':proposal['proposal_id'],'approved':False}):
            with self.assertRaises(ValueError):self.engine.branch.authorize(task_id,values)
        task=self.engine.store.get(task_id);task['branch_run']['plan']['items'][0]['instructions']='Different work';self.engine.store.save(task)
        with self.assertRaises(ValueError):self.engine.branch.authorize(task_id,{'proposal_id':proposal['proposal_id'],'approved':True,'full_suite_approved':True})
        self.assertIsNone(_tip(self.source,'refs/heads/feature/job'))

    def test_restart_keeps_contract_but_expires_commands(self):
        proposal=self.engine.branch.prepare(self.values)
        task=self.engine.branch.authorize(proposal['task_id'],{'proposal_id':proposal['proposal_id'],'approved':True,'full_suite_approved':True})
        task['branch_run']['status']='paused';task['status']='paused';self.engine.store.save(task)
        self.engine.update_limits(task['id'],{'limits':{'uncapped_work':True}})
        restarted=Engine(self.root/'state',fixture_delay=0);self.addCleanup(restarted.shutdown)
        restarted.config=copy.deepcopy(self.engine.config)
        loaded=restarted.store.get(task['id'])
        self.assertTrue(loaded['branch_run']['plan']['uncapped_work'])
        restarted.branch.validate_authority(loaded,loaded['branch_run'])
        self.assertFalse(restarted.branch.scopes.authorize(loaded,loaded['check_command']))
        self.assertEqual(restarted.runtimes,{})

    def test_restart_unstarted_proposal_continues_without_replan(self):
        proposal = self.engine.branch.prepare(self.values)
        task_id = proposal['task_id']
        restarted = Engine(self.root / 'state', fixture_delay=0)
        self.addCleanup(restarted.shutdown)
        restarted.config = copy.deepcopy(self.engine.config)
        restarted.branch.launch = lambda tid: restarted.store.get(tid)
        with patch.object(restarted.branch, 'plan') as mock_plan:
            result = restarted.branch.message(task_id, {'message': 'plan approved, continue'})
            mock_plan.assert_not_called()
        self.assertTrue(result['branch_run']['authorization_ref'])
        self.assertEqual(result['branch_run']['status'], 'running')
        self.assertEqual(result['status'], 'running')
