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
        controller._finish_start=Mock(side_effect=ValueError('Private snapshot contents changed'))
        branch_startup.complete(controller,runtime)
        run=runtime.task['branch_run']
        self.assertEqual(run['startup']['status'],'failed')
        self.assertEqual(run['status'],'awaiting_authorization')
        self.assertEqual(run['limits'],before)
        self.assertTrue(run['startup']['error'])
        controller.engine.event.assert_called_once()

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
