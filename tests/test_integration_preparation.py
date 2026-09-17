"""In-memory continuation cases. No Git fixtures, providers, or real waits."""
import copy
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from cheapos import integration_preparation as prep


class IntegrationPreparationTests(unittest.TestCase):
    def fixture(self,branch=True):
        task={'id':'task','source':'source','workspace':'private','patch':'patch','workspace_generation':0,'status':'paused',
              'usage':{'tokens':23},'checks':[{'passed':True}]}
        if branch:task['branch_run']={'target_ref':'refs/heads/main','expected_feature_tip':'feature',
            'workspace_mapping':{'source':'source'},'items':[{'status':'committed'}],'status':'paused'}
        engine=SimpleNamespace(lock=threading.RLock(),store=Mock(),admission=Mock(),require_active_task=Mock(),
                               runtimes={},branch=Mock(),start=Mock(),reconcile_project=Mock(),route_restore_stop=threading.Event())
        engine.admission.operations={}
        engine.store.get.return_value=task
        engine.admission.snapshot.return_value={'interactive':{'allowed':True},'unattended':{'allowed':True}}
        return engine,task

    def accepted(self,engine,task):
        values={'approved':True,'target_tip':'target','candidate':prep.candidate(task),'operation_id':'op','target_ref':'refs/heads/main'}
        with patch.object(prep,'_launch'):prep.start(engine,'task',values)
        return values

    def test_acknowledges_before_git_and_duplicate_does_not_replace_receipt(self):
        engine,task=self.fixture();values=self.accepted(engine,task)
        original=copy.deepcopy(task['integration_preparation'])
        with patch.object(prep,'_launch'),patch.object(prep,'readiness') as read:
            prep.start(engine,'task',values)
            read.assert_not_called()
            with self.assertRaises(ValueError):prep.start(engine,'task',{**values,'target_tip':'other'})
        self.assertEqual(task['integration_preparation'],original)
        self.assertEqual(task['usage'],{'tokens':23})

    def test_conflict_assignment_continues_without_second_operator_action(self):
        engine,task=self.fixture();self.accepted(engine,task)
        state={'code':'target_advanced','target_tip':'target'}
        with patch.object(prep,'readiness',return_value=state),patch('cheapos.branch_completion.update_token',return_value='token'),patch('cheapos.branch_completion.update_branch',return_value={'needs_conflict_resolution':True}),patch('cheapos.branch_conflicts.start') as resolve:
            prep._drive(engine,'task')
        resolve.assert_called_once_with(engine.branch,'task',{'approved':True,'update_token':'token'})
        self.assertEqual(task['integration_preparation']['id'],'op')
        self.assertEqual(task['integration_preparation']['stage'],'resolving')
        self.assertEqual(task['checks'],[{'passed':True}])

    def test_restart_after_assignment_resumes_existing_item(self):
        engine,task=self.fixture();self.accepted(engine,task)
        task['branch_run']['conflict_resolution']={'preparation_id':'op','item_id':'resolve'}
        with patch('cheapos.branch_conflicts.start') as assign:
            prep._drive(engine,'task')
        assign.assert_not_called();engine.branch.resume.assert_called_once_with('task',{})

    def test_dirty_destination_waits_without_mutation(self):
        engine,task=self.fixture();self.accepted(engine,task)
        with patch.object(prep,'readiness',return_value={'code':'dirty_destination','files':['a.py']}),patch.object(prep.threading,'Timer') as timer:
            prep._drive(engine,'task')
        self.assertEqual(task['integration_preparation']['status'],'waiting')
        timer.assert_called_once();engine.branch.resume.assert_not_called()
        engine.reconcile_project.assert_not_called()

    def test_interactive_reconciliation_dispatch_is_server_owned(self):
        engine,task=self.fixture(False);self.accepted(engine,task)
        def reconcile(*args):task['workspace_generation']=1
        engine.reconcile_project.side_effect=reconcile
        with patch.object(prep,'readiness',return_value={'code':'text_conflicts','target_tip':'target'}):prep._drive(engine,'task')
        engine.reconcile_project.assert_called_once();engine.start.assert_called_once_with('task')
        # A process loss after reconciliation must not rebuild another task copy.
        task['integration_preparation'].pop('dispatched')
        engine.start.reset_mock();engine.reconcile_project.reset_mock()
        prep._drive(engine,'task')
        engine.reconcile_project.assert_not_called();engine.start.assert_called_once()

    def test_redundant_interactive_patch_still_runs_verification(self):
        engine,task=self.fixture(False);self.accepted(engine,task)
        engine.reconcile_project.side_effect=lambda *args:task.update(patch='',workspace_generation=1)
        with patch.object(prep,'readiness',return_value={'code':'text_conflicts','target_tip':'target'}):prep._drive(engine,'task')
        self.assertTrue(task['integration_preparation']['already_included'])
        self.assertNotEqual(task['integration_preparation']['status'],'ready')
        engine.start.assert_called_once()

    def test_readiness_dirty_is_not_branch_update(self):
        engine,task=self.fixture()
        def git(source,*args,**kwargs):
            if args[0]=='symbolic-ref':return 'refs/heads/main'
            if args[0]=='status':return ' M a.py'
            return ''
        with patch.object(prep.work,'_tip',return_value='target'),patch.object(prep.work,'source_git',side_effect=git):
            state=prep.readiness(engine,'task')
        self.assertEqual(state['code'],'dirty_destination');self.assertEqual(state['actions'],['inspect_local_changes'])
        self.assertEqual(state['files'],['a.py'])

    def test_changed_target_history_requires_specific_decision(self):
        engine,task=self.fixture();self.accepted(engine,task)
        with patch.object(prep,'readiness',return_value={'code':'target_advanced','target_tip':'replacement'}),patch.object(prep.work,'source_git',side_effect=ValueError('not ancestor')):
            prep._drive(engine,'task')
        self.assertEqual(task['integration_preparation']['reason']['code'],'target_replaced')
        engine.branch.resume.assert_not_called()

    def test_readiness_finish_requires_review_receipt_and_no_destination_write(self):
        engine,task=self.fixture();self.accepted(engine,task)
        task['branch_run'].update(status='ready_for_merge',readiness={'id':'fresh'})
        with patch.object(prep,'readiness',return_value={'code':'ready'}):prep.observe(engine,task)
        self.assertEqual(task['integration_preparation']['status'],'ready')
        engine.branch.merge.assert_not_called()

    def test_shutdown_suppresses_timer_dispatch(self):
        engine,task=self.fixture();self.accepted(engine,task)
        engine.route_restore_stop.set()
        with patch.object(prep.threading,'Thread') as thread:prep.resume(engine,'task')
        thread.assert_not_called()

    def test_already_included_dispatches_actual_engine_start_with_checkpoint(self):
        from tests.test_finish_review import FinishReviewTests
        from cheapos.engine import Engine
        fixture=FinishReviewTests();fixture.setUp()
        fixture.task.update(patch='',integration_preparation={'already_included':True,'authorized':True,'id':'op'})
        fixture.engine.start=lambda task_id:Engine.start(fixture.engine,task_id)
        with patch('cheapos.engine.Runtime'),patch('cheapos.engine.threading.Thread'):
            prep._resume_interactive(fixture.engine,fixture.task)
        self.assertEqual(fixture.task['status'],'running')
        self.assertTrue(fixture.task['finish_review'])
        self.assertIn('pending_checkpoint',fixture.task)
        self.assertIn('saved',fixture.engine.runtimes)

    def test_cancel_during_inspection_prevents_dispatch_and_stale_publish(self):
        engine,task=self.fixture();self.accepted(engine,task)
        def inspection(*args):
            prep.cancel(engine,'task')
            return {'code':'target_advanced','target_tip':'target'}
        with patch.object(prep,'readiness',side_effect=inspection),patch('cheapos.branch_completion.update_branch') as update:
            prep._drive(engine,'task')
        update.assert_not_called()
        self.assertEqual(task['integration_preparation']['status'],'cancelled')
        self.assertFalse(task['integration_preparation']['authorized'])
        self.assertFalse(prep.automatic(engine,task))

    def test_new_request_can_retry_failed_identity_but_not_duplicate_active_work(self):
        engine,task=self.fixture();values=self.accepted(engine,task)
        with patch.object(prep,'_launch'):
            prep.start(engine,'task',{**values,'operation_id':'duplicate'})
        self.assertEqual(task['integration_preparation']['id'],'op')
        task['integration_preparation'].update(status='failed',dispatched=True)
        with patch.object(prep,'_launch'):
            prep.start(engine,'task',{**values,'operation_id':'retry'})
        self.assertEqual(task['integration_preparation']['id'],'retry')
        self.assertTrue(task['integration_preparation']['dispatched'])
        self.assertEqual(task['integration_preparation_history'][0]['id'],'op')

    def test_explicit_new_id_reauthorizes_cancelled_preparation(self):
        engine,task=self.fixture();values=self.accepted(engine,task)
        prep.cancel(engine,'task')
        self.assertFalse(prep.automatic(engine,task))
        with patch.object(prep,'_launch'):
            prep.start(engine,'task',{**values,'operation_id':'new-consent'})
        self.assertTrue(task['integration_preparation']['authorized'])
        self.assertEqual(task['integration_preparation']['id'],'new-consent')
        self.assertEqual(task['integration_preparation_history'][0]['status'],'cancelled')

    def test_interactive_resolution_comparison_reads_only_captured_paths(self):
        import tempfile
        from pathlib import Path
        engine,task=self.fixture(False)
        with tempfile.TemporaryDirectory() as directory:
            previous=Path(directory)/'previous';current=Path(directory)/'current'
            previous.mkdir();current.mkdir()
            (previous/'a.py').write_text('before\n');(current/'a.py').write_text('combined\n')
            task.update(workspace=str(current),reconciliation={'previous_workspace':str(previous),
                'source_head':'target','files':['a.py'],'conflicts':['a.py']})
            with patch.object(prep.work,'source_git',return_value='old-baseline'):
                result=prep.resolution_changes(engine,'task')
            self.assertIn('-before',result['diff']);self.assertIn('+combined',result['diff'])
            self.assertEqual(result['target_tip'],'target');self.assertEqual(result['files'],['a.py'])
            task['reconciliation']['files']=['../outside']
            with self.assertRaises(ValueError):prep.resolution_changes(engine,'task')
