"""Startup receipts/recovery and batch parsing without Git workflows or waits."""
import copy
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from cheapos import branch_runs, branch_startup, branch_workspace
from cheapos.branch_controller import BranchController
from cheapos.engine import Runtime


class StartupTests(unittest.TestCase):
    def fixture(self):
        run=branch_runs.new_run({'items':[{'id':'one','title':'One','instructions':'Implement one',
            'acceptance_criteria':['Works'],'required_checks':['python3 -m unittest test_one']}], 'limits':{'requests':10}})
        run.update(status='awaiting_authorization',authorization_ref='saved-approval',
                   workspace_mapping={'stage':'prepared'},check_scope=[],
                   startup={'status':'running','stage':'accepted','label':'Approval saved','started_at':'now'})
        task={'id':'task','events':[],'status':'running','branch_run':run}
        engine=SimpleNamespace(lock=threading.RLock(),event=Mock(),store=Mock())
        controller=object.__new__(BranchController)
        controller.engine=engine
        controller.validate_authority=Mock()
        return controller,Runtime(task)

    def test_pause_before_setup_cannot_create_branch_or_grant_commands(self):
        controller,runtime=self.fixture()
        runtime.stop.set()
        with patch('cheapos.branch_controller.work.create') as create:
            branch_startup.complete(controller,runtime)
        create.assert_not_called()
        run=runtime.task['branch_run']
        self.assertEqual(run['authorization_ref'],'saved-approval')
        self.assertEqual(run['startup']['status'],'paused')
        self.assertEqual(run['status'],'awaiting_authorization')
        self.assertEqual(run['pause_detail']['cause'],'operator')

    def test_setup_failure_is_retained_and_does_not_renew_or_launch_work(self):
        controller,runtime=self.fixture()
        before=copy.deepcopy(runtime.task['branch_run']['limits'])
        runtime.task.update(active_role='planner',error_code='http_429',
                            request_metrics=[{'id':'old-request','role':'planner','model':'old/planner'}])
        controller._finish_start=Mock(side_effect=branch_workspace.WorkspaceChanged('Private snapshot contents changed'))
        with self.assertLogs('cheapos.branch_startup',level='ERROR'):
            branch_startup.complete(controller,runtime)
        run=runtime.task['branch_run']
        self.assertEqual(run['startup']['status'],'failed')
        self.assertEqual(run['status'],'awaiting_authorization')
        self.assertEqual(run['limits'],before)
        self.assertEqual(run['startup']['error'],'Private snapshot contents changed')
        self.assertEqual(run['pause_detail']['cause'],'branch_drift')
        self.assertEqual(run['pause_detail']['stage'],'startup')
        self.assertNotIn('model',run['pause_detail'])
        self.assertNotIn('role',run['pause_detail'])
        self.assertNotEqual(run['pause_detail']['diagnostic_id'],'old-request')
        controller.engine.event.assert_called_once()

    def test_unexpected_startup_failure_keeps_traceback_out_of_public_diagnostic(self):
        controller,runtime=self.fixture()
        controller._finish_start=Mock(side_effect=RuntimeError('private raw error'))
        with self.assertLogs('cheapos.branch_startup',level='ERROR') as logs:
            branch_startup.complete(controller,runtime)
        run=runtime.task['branch_run']
        self.assertEqual(run['pause_detail']['cause'],'controller_error')
        self.assertIn(run['startup']['diagnostic_id'],' '.join(logs.output))
        self.assertIn('private raw error',' '.join(logs.output))
        self.assertNotIn('private raw error',str(run))

    def test_saved_startup_continues_on_pinned_snapshot_after_base_advances(self):
        controller,runtime=self.fixture()
        run=runtime.task['branch_run']
        mapping={'stage':'prepared','source':'/fixture','source_identity':['source'],
                 'common_identity':['git'],'base_ref':'refs/heads/main','base_sha':'approved',
                 'feature_ref':'refs/heads/feature/one','target_ref':'refs/heads/main',
                 'protected_refs':[],'workspace_identity':['private'],'workspace_head':'snapshot'}
        run.update(workspace_mapping=copy.deepcopy(mapping),authorization_workspace=copy.deepcopy(mapping),
                   model_policy={'mode':'free'},consumption={'requests':7},check_scope=[{'command':['check']}])
        saved={k:copy.deepcopy(run[k]) for k in ('authorization_ref','authorization_workspace','model_policy','consumption','limits','check_scope')}
        controller.scopes=SimpleNamespace(prepare=Mock(return_value=run['check_scope'][0]),consent=Mock())
        controller._launch=Mock()
        def create(prepared,persist,**kwargs):
            self.assertEqual(prepared,mapping)
            ready=dict(prepared,stage='ready',feature_tip='approved')
            persist(ready)
            return ready
        with patch.object(branch_workspace,'inspect_source',return_value={k:mapping[k] for k in ('source','source_identity','common_identity')}), \
             patch.object(branch_workspace,'_available'), \
             patch.object(branch_workspace,'_tip',side_effect=lambda source,ref:'newer' if ref==mapping['base_ref'] else None), \
             patch.object(branch_workspace,'source_git',return_value='approved'), \
             patch.object(branch_workspace,'create',side_effect=create), \
             patch('cheapos.unattended_setup.require_ready'):
            branch_startup.complete(controller,runtime)
        self.assertEqual(run['status'],'running')
        self.assertEqual(run['expected_feature_tip'],'approved')
        self.assertEqual({k:run[k] for k in saved},saved)
        controller.scopes.consent.assert_called_once_with(runtime.task,saved['check_scope'][0])
        controller._launch.assert_called_once_with('task',runtime=runtime)
        self.assertIn('Continuing from the approved snapshot',[call.args[2] for call in controller.engine.event.call_args_list])

    def test_progress_requires_current_authority_and_restart_retains_approval(self):
        controller,runtime=self.fixture()
        branch_startup.progress(controller,runtime,'verifying_snapshot')
        self.assertEqual(runtime.task['branch_run']['startup']['label'],'Verifying task copy')
        controller.validate_authority.side_effect=ValueError('Authorization was revoked')
        with self.assertRaises(ValueError): branch_startup.progress(controller,runtime,'preparing_branch')
        self.assertEqual(runtime.task['branch_run']['startup']['stage'],'verifying_snapshot')
        saved=copy.deepcopy(runtime.task['branch_run'])
        branch_runs.recover_restart(saved)
        self.assertEqual(saved['startup']['status'],'paused')
        self.assertEqual(saved['authorization_ref'],'saved-approval')
        self.assertEqual(saved['status'],'awaiting_authorization')


class SnapshotBatchTests(unittest.TestCase):
    def test_base_rewrites_deletion_and_missing_snapshot_still_block(self):
        plan={'source':'/fixture','base_ref':'refs/heads/main','base_sha':'approved',
              'workspace_identity':['private'],'workspace_head':'snapshot'}
        for current,ancestor,private in [('rewritten','unrelated',True),(None,'',True),('newer','approved',False)]:
            with self.subTest(current=current,private=private), \
                 patch.object(branch_workspace,'_tip',return_value=current), \
                 patch.object(branch_workspace,'source_git',return_value=ancestor):
                candidate=copy.deepcopy(plan)
                if not private:candidate.pop('workspace_identity')
                with self.assertRaises(branch_workspace.WorkspaceChanged):branch_workspace.validate_base(candidate)

    def test_one_process_preserves_binary_duplicate_and_empty_blobs(self):
        content=b'\x00binary\n\xff'
        oid='a'*40
        empty='b'*40
        entries=[{'oid':oid,'size':len(content)},{'oid':empty,'size':0},{'oid':oid,'size':len(content)}]
        response=(f'{oid} blob {len(content)}\n'.encode()+content+b'\n'+
                  f'{empty} blob 0\n\n'.encode()+f'{oid} blob {len(content)}\n'.encode()+content+b'\n')
        with patch.object(branch_workspace,'source_git',return_value=response) as git:
            blobs=branch_workspace._snapshot_blobs({'source':'/fixture','entries':entries})
        self.assertEqual([bytes(b) for b in blobs],[content,b'',content])
        git.assert_called_once_with('/fixture','cat-file','--batch',input=oid+'\n'+empty+'\n'+oid+'\n',binary=True)

    def test_missing_mismatched_truncated_and_trailing_objects_fail_closed(self):
        oid='a'*40
        plan={'source':'/fixture','entries':[{'oid':oid,'size':3}]}
        for response in (b'',f'{oid} missing\n'.encode(),f'{oid} tree 3\nabc\n'.encode(),
                         f'{"b"*40} blob 3\nabc\n'.encode(),f'{oid} blob 3\nab'.encode(),
                         f'{oid} blob 4\nabcd\n'.encode(),f'{oid} blob 3\nabc\nextra'.encode()):
            with self.subTest(response=response),patch.object(branch_workspace,'source_git',return_value=response):
                with self.assertRaises(ValueError):branch_workspace._snapshot_blobs(plan)
        with patch.object(branch_workspace,'source_git') as git:
            with self.assertRaises(ValueError):
                branch_workspace._snapshot_blobs({'source':'/fixture','entries':[{'oid':'HEAD\nother','size':3}]})
            git.assert_not_called()
