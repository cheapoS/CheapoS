"""In-memory continuation cases. No Git fixtures, providers, or real waits."""
import copy
import shlex
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from types import MethodType
from unittest.mock import Mock,patch
from cheapos import integration_preparation as prep


class IntegrationPreparationTests(unittest.TestCase):
    def authorized_fixture(self):
        """Real consent/Resume/launch with tiny directories, no Git or execution."""
        from tests.test_branch_authorization import CheckScopeTests
        from tests.test_branch_operator import BranchOperatorTests
        from cheapos.branch_controller import BranchController
        from cheapos.branch_authorization import contract_builder,ProposalRegistry
        permissions=CheckScopeTests();permissions.setUp();self.addCleanup(permissions.doCleanups)
        fixture=BranchOperatorTests();fixture.setUp()
        task=fixture.saved;run=task['branch_run'];engine=fixture.engine;controller=fixture.controller
        task.update({k:permissions.task[k] for k in ('source','workspace','snapshot')})
        # Register this task ID without restoring any expired session grant.
        permissions.grants.workspaces['task']=permissions.grants.workspaces['t']
        run['workspace_mapping'].update(source=task['source'],workspace=task['workspace'],stage='ready')
        run['items'][0]['status']='committed'
        run['check_scope']=[permissions.scopes.prepare(task,permissions.argv)]
        command=shlex.join(permissions.argv)
        run['plan']['items'][0]['required_checks']=[command]
        run['plan']['final_checks']=[command]
        run['items'][0]['required_checks']=[command]
        controller.scopes=permissions.scopes;controller.resume_proposals=ProposalRegistry()
        controller.validate_authority=lambda task,run:controller.proposals.validate(run['authorization'],contract_builder(run,{},run['model_policy'],run['check_scope']))
        proposal=controller.proposals.prepare('task',contract_builder(run,{},run['model_policy'],run['check_scope']))
        auth=controller.proposals.authorize('task',proposal['proposal_id'],True,proposal['contract'])
        run.update(authorization=auth,authorization_ref=auth['id'])
        engine.branch=controller;engine.runtimes={};engine.gateway.pool=Mock()
        engine.admission=Mock();engine.admission.snapshot.return_value={'unattended':{'allowed':True}}
        engine.route_restore_stop=threading.Event()
        for name in ('resume','launch','_launch'):setattr(controller,name,MethodType(getattr(BranchController,name),controller))
        controller.execute=Mock()
        return fixture,permissions

    def test_update_click_renews_exact_checks_and_starts_conflict_worker(self):
        from cheapos import branch_conflicts
        from tests.test_branch_conflicts import ConflictTests
        fixture,permissions=self.authorized_fixture();engine=fixture.engine
        before=copy.deepcopy(fixture.saved)
        self.assertIsNone(permissions.scopes.authorize(fixture.saved,permissions.argv))
        self.accepted(engine,fixture.saved)
        self.assertTrue(permissions.scopes.authorize(fixture.saved,permissions.argv))
        self.assertEqual(permissions.grants.grants,{})  # No project-wide grant.
        with ExitStack() as stack:
            stack.enter_context(patch.object(prep,'readiness',return_value={'code':'target_advanced','target_tip':'target'}))
            stack.enter_context(patch('cheapos.branch_completion.update_token',return_value='token'))
            stack.enter_context(patch('cheapos.branch_completion.update_branch',return_value={'needs_conflict_resolution':True}))
            stack.enter_context(patch.object(branch_conflicts,'capture',return_value=ConflictTests().context()))
            stack.enter_context(patch.object(branch_conflicts.work,'source_git',return_value=''))
            stack.enter_context(patch.object(branch_conflicts.work,'validate_owned'))
            stack.enter_context(patch('cheapos.model_pool.observe_completions'))
            thread=stack.enter_context(patch('threading.Thread'))
            prep._drive(engine,'task')
        self.assertEqual(fixture.saved['status'],'running')
        self.assertEqual(fixture.saved['branch_run']['items'][-1]['id'],'resolve-conflicts-1')
        thread.return_value.start.assert_called_once()
        self.assertEqual(thread.call_args.kwargs['target'],fixture.controller.execute)
        self.assertEqual(fixture.saved['usage'],before['usage'])
        self.assertEqual(fixture.saved['branch_run']['limits'],before['branch_run']['limits'])
        self.assertEqual(fixture.saved['branch_run']['model_policy'],before['branch_run']['model_policy'])
        self.assertEqual(fixture.saved['branch_run']['final_evidence'],{})

    def test_changed_environment_requires_permission_in_same_update_then_continues(self):
        fixture,permissions=self.authorized_fixture();engine=fixture.engine
        (Path(fixture.saved['workspace'])/'setup.cfg').write_text('[test]\nchanged = true\n')
        self.accepted(engine,fixture.saved)
        self.assertIsNone(permissions.scopes.authorize(fixture.saved,permissions.argv))
        fixture.saved['integration_preparation']['dispatched']=True
        with patch('cheapos.branch_workspace.validate_owned'),patch('cheapos.model_pool.observe_completions'):
            prep._drive(engine,'task')
        op=fixture.saved['integration_preparation']
        self.assertEqual(op['status'],'decision')
        self.assertEqual(op['reason']['code'],'command_permission_required')
        self.assertEqual(op['reason']['commands'],[permissions.argv])
        self.assertEqual(engine.runtimes,{})
        # A fresh permission proposal can continue that same assignment in Changes.
        with patch('cheapos.branch_workspace.validate_owned'),patch('cheapos.model_pool.observe_completions'),patch('threading.Thread') as thread:
            proposal=fixture.controller.resume('task',{})
            result=fixture.controller.resume('task',{'approved':True,'proposal_id':proposal['proposal_id']})
        self.assertFalse(result['needs_consent'])
        self.assertEqual(fixture.saved['status'],'running')
        self.assertEqual(fixture.saved['integration_preparation']['id'],op['id'])
        self.assertEqual(fixture.saved['integration_preparation']['status'],'running')
        self.assertNotIn('reason',fixture.saved['integration_preparation'])
        thread.return_value.start.assert_called_once()

    def test_background_preparation_never_renews_expired_checks(self):
        fixture,permissions=self.authorized_fixture();engine=fixture.engine
        values={'approved':True,'target_tip':'target','candidate':prep.candidate(fixture.saved)}
        with patch.object(prep,'_launch'):prep.start(engine,'task',values,renew_checks=False)
        self.assertIsNone(permissions.scopes.authorize(fixture.saved,permissions.argv))
        fixture.saved['integration_preparation']['dispatched']=True
        with patch('cheapos.branch_workspace.validate_owned'),patch('cheapos.model_pool.observe_completions'):
            prep._drive(engine,'task')
        self.assertEqual(fixture.saved['integration_preparation']['reason']['code'],'command_permission_required')
        self.assertIsNone(permissions.scopes.authorize(fixture.saved,permissions.argv))
        with patch.object(prep,'_launch') as launch:prep.start(engine,'task',values)
        self.assertTrue(permissions.scopes.authorize(fixture.saved,permissions.argv))
        launch.assert_called_once_with(engine,'task')

    def test_each_background_handoff_retains_required_permission(self):
        consent={'needs_consent':True,'scopes':[{'command':['python3','test.py']}]}
        for path in ('conflict','clean_update','pending_update','review'):
            with self.subTest(path=path):
                engine,task=self.fixture();self.accepted(engine,task)
                if path=='pending_update':task['branch_run']['target_update']={'stage':'prepared'}
                state={'code':'review_required' if path=='review' else 'target_advanced','target_tip':'target'}
                engine.branch.resume.return_value=consent
                with patch.object(prep,'readiness',return_value=state),patch('cheapos.branch_completion.update_token',return_value='token'),patch('cheapos.branch_completion.update_branch',return_value={'needs_conflict_resolution':True} if path=='conflict' else consent),patch('cheapos.branch_conflicts.start',return_value=consent):
                    prep._drive(engine,'task')
                self.assertEqual(task['integration_preparation']['reason']['code'],'command_permission_required')
                self.assertEqual(task['integration_preparation']['status'],'decision')

    def test_cancelled_or_running_task_ignores_late_permission_result(self):
        for state in ('cancelled','running','replaced'):
            with self.subTest(state=state):
                engine,task=self.fixture();self.accepted(engine,task)
                if state=='cancelled':prep.cancel(engine,'task')
                elif state=='replaced':task['integration_preparation']['id']='new-operation'
                else:engine.runtimes['task']=SimpleNamespace(thread=Mock())
                before=copy.deepcopy(task)
                prep._continued(engine,'task',{'needs_consent':True,'scopes':[]},'op')
                self.assertEqual(task,before)

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
        task['branch_run']['readiness']={'id':'reviewed'}
        def git(source,*args,**kwargs):
            if args[0]=='merge-base':
                self.assertEqual(source,'source')
                return ''
            self.assertEqual(source,'linked-target')
            if args[0]=='symbolic-ref':return 'refs/heads/main'
            if args[0]=='status':return ' M a.py'
            if args[0]=='diff-tree':return b'a.py\0'
            if args[0]=='ls-files':return b''
            return ''
        with patch.object(prep.work,'_tip',return_value='target'),patch.object(prep.work,'source_git',side_effect=git), \
                patch.object(prep.branch_merge,'_destination',return_value='linked-target'), \
                patch.object(prep.branch_merge,'destination_identity'),patch.object(prep.work,'validate_owned'):
            state=prep.readiness(engine,'task')
        self.assertEqual(state['code'],'dirty_destination');self.assertEqual(state['actions'],['inspect_local_changes'])
        self.assertEqual(state['files'],['a.py'])
        self.assertEqual(state['destination'],'linked-target')

    def test_dirty_destination_keeps_update_action_and_dispatches_isolated_preparation(self):
        engine,task=self.fixture();task['branch_run']['readiness']={'id':'reviewed'}
        self.accepted(engine,task)
        advanced=True
        def git(source,*args,**kwargs):
            if args[0]=='merge-base':
                self.assertEqual(source,'source')
                if advanced:raise ValueError('target is not an ancestor')
                return ''
            self.assertEqual(source,'linked-target')
            if args[0]=='symbolic-ref':return 'refs/heads/main'
            if args[0]=='status':return '?? notes.md\0?? protocol.md\0'
            if args[0]=='diff-tree':return b'app.py\0'
            if args[0]=='ls-files':return b''
            self.assertEqual(args[0],'rev-parse')
            return ''
        with patch.object(prep.work,'_tip',return_value='target'),patch.object(prep.work,'source_git',side_effect=git), \
                patch.object(prep.branch_merge,'_destination',return_value='linked-target'), \
                patch.object(prep.branch_merge,'destination_identity'),patch.object(prep.work,'validate_owned'), \
                patch('cheapos.branch_completion.update_token',return_value='token'), \
                patch('cheapos.branch_completion.update_branch',return_value={'needs_conflict_resolution':True}) as update, \
                patch('cheapos.branch_conflicts.start',return_value={}) as resolve:
            state=prep.readiness(engine,'task')
            self.assertEqual(state['code'],'target_advanced')
            self.assertIn('update_resolve',state['actions'])
            self.assertIn('inspect_local_changes',state['actions'])
            self.assertEqual(state['local_changes'],['notes.md','protocol.md'])
            prep._drive(engine,'task')
            update.assert_called_once_with(engine.branch,'task',{'approved':True,'update_token':'token'})
            resolve.assert_called_once_with(engine.branch,'task',{'approved':True,'update_token':'token'})
            self.assertEqual(task['integration_preparation']['stage'],'resolving')
            # Once committed changes are included, unrelated drafts require no
            # operator cleanup, extra agent work, or repeated verification.
            advanced=False
            state=prep.readiness(engine,'task')
            self.assertEqual(state['code'],'ready')
            self.assertEqual(state['local_changes'],['notes.md','protocol.md'])
            self.assertNotIn('update_resolve',state['actions'])
            self.assertIn('preserved',state['message'])
        engine.reconcile_project.assert_not_called()
        self.assertEqual(task['usage'],{'tokens':23})
        self.assertEqual(task['checks'],[{'passed':True}])

    def test_interactive_local_changes_still_require_existing_commit_safeguards(self):
        engine,task=self.fixture(branch=False)
        def git(source,*args,**kwargs):
            return 'refs/heads/main' if args[0]=='symbolic-ref' else b'?? notes.md\0' if args[0]=='status' else ''
        with patch.object(prep.work,'_tip',return_value='target'),patch.object(prep.work,'source_git',side_effect=git):
            state=prep.readiness(engine,'task')
        self.assertEqual(state['code'],'dirty_destination')
        self.assertEqual(state['files'],['notes.md'])

    def test_dirty_destination_does_not_bypass_authority_or_owned_workspace(self):
        for failure in ('authority_changed','ownership_changed','work_remaining'):
            with self.subTest(failure=failure):
                engine,task=self.fixture()
                if failure=='authority_changed':engine.branch.validate_authority.side_effect=ValueError('authority changed')
                if failure=='work_remaining':task['branch_run']['items'][0]['status']='working'
                def git(source,*args,**kwargs):
                    self.assertNotEqual(args[0],'merge-base')
                    return 'refs/heads/main' if args[0]=='symbolic-ref' else '?? notes.md\0' if args[0]=='status' else ''
                with patch.object(prep.work,'_tip',return_value='target'),patch.object(prep.work,'source_git',side_effect=git), \
                        patch.object(prep.branch_merge,'_destination',return_value='linked-target'), \
                        patch.object(prep.branch_merge,'destination_identity'), \
                        patch.object(prep.work,'validate_owned',side_effect=ValueError('ownership changed') if failure=='ownership_changed' else None):
                    state=prep.readiness(engine,'task')
                self.assertEqual(state['code'],failure)
                self.assertNotIn('update_resolve',state['actions'])

    def test_unchecked_out_branch_readiness_ignores_unrelated_checkout(self):
        engine,task=self.fixture()
        task['branch_run']['readiness']={'id':'reviewed'}
        with patch.object(prep.work,'_tip',return_value='target'), \
                patch.object(prep.work,'source_git') as git,patch.object(prep.work,'validate_owned'), \
                patch.object(prep.branch_merge,'_destination',return_value=None):
            state=prep.readiness(engine,'task')
        self.assertEqual(state['code'],'ready')
        self.assertIsNone(state['destination'])
        git.assert_called_once_with('source','merge-base','--is-ancestor','target','feature')

    def test_inspect_local_changes_reads_only_the_actual_destination(self):
        engine,task=self.fixture()
        with patch.object(prep,'readiness',return_value={'destination':'linked-target','files':[],'local_changes':['a.py']}), \
                patch.object(prep.work,'source_git',return_value='target edits') as git:
            result=prep.local_changes(engine,'task')
        git.assert_called_once_with('linked-target','diff','HEAD','--no-ext-diff','--no-renames')
        self.assertEqual(result['diff'],'target edits')
        self.assertEqual(result['files'],['a.py'])
        with patch.object(prep,'readiness',return_value={'destination':None,'files':[]}), \
                patch.object(prep.work,'source_git') as git:
            self.assertEqual(prep.local_changes(engine,'task')['diff'],'')
        git.assert_not_called()
        with patch.object(prep,'readiness',return_value={'message':'Destination changed'}), \
                patch.object(prep.work,'source_git') as git:
            with self.assertRaisesRegex(ValueError,'Destination changed'):prep.local_changes(engine,'task')
        git.assert_not_called()

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

    def test_retry_does_not_inherit_dispatch_from_a_different_assignment(self):
        for changed in ('candidate','target_tip','target_ref','workspace','workspace_generation'):
            with self.subTest(changed=changed):
                engine,task=self.fixture();values=self.accepted(engine,task)
                task['integration_preparation'].update(status='cancelled',dispatched=True)
                values={**values,'operation_id':'new-update'}
                if changed=='candidate':
                    task['branch_run']['expected_feature_tip']='new-feature';values[changed]='new-feature'
                elif changed=='target_tip':values[changed]='new-target'
                elif changed=='target_ref':
                    task['branch_run']['target_ref']='refs/heads/release';values[changed]='refs/heads/release'
                elif changed=='workspace':task[changed]='new-private'
                else:task[changed]=1
                with patch.object(prep,'_launch'):prep.start(engine,'task',values)
                self.assertFalse(task['integration_preparation'].get('dispatched'))
                self.assertTrue(task['integration_preparation_history'][-1]['dispatched'])

    def test_saved_stale_dispatch_assigns_new_conflicts_instead_of_repeating_review(self):
        engine,task=self.fixture();self.accepted(engine,task)
        task['integration_preparation']['dispatched']=True
        task['branch_run'].update(status='paused',pause_reason='branch_drift',readiness={'id':'old-review'},
            conflict_resolution={'status':'integrated','preparation_id':'previous-update','item_id':'resolve-1'})
        before=copy.deepcopy({key:task[key] for key in ('checks','usage')})
        state={'code':'target_advanced','target_tip':'target'}
        with patch.object(prep,'readiness',return_value=state), \
             patch('cheapos.branch_completion.update_token',return_value='token'), \
             patch('cheapos.branch_completion.update_branch',return_value={'needs_conflict_resolution':True}) as update, \
             patch('cheapos.branch_conflicts.start',return_value={}) as resolve:
            prep._drive(engine,'task')
        update.assert_called_once_with(engine.branch,'task',{'approved':True,'update_token':'token'})
        resolve.assert_called_once_with(engine.branch,'task',{'approved':True,'update_token':'token'})
        engine.branch.resume.assert_not_called()
        self.assertEqual(task['integration_preparation']['stage'],'resolving')
        for key,value in before.items():self.assertEqual(task[key],value)

    def test_target_drift_never_replaces_an_unfinished_resolution(self):
        engine,task=self.fixture();self.accepted(engine,task)
        task['integration_preparation']['dispatched']=True
        task['branch_run'].update(status='paused',pause_reason='branch_drift',readiness={'id':'old-review'},
            conflict_resolution={'status':'working','preparation_id':'op','item_id':'resolve'})
        task['branch_run']['items'].append({'id':'resolve','status':'working'})
        with patch.object(prep,'readiness') as inspect,patch('cheapos.branch_conflicts.start') as assign:
            prep._drive(engine,'task')
        inspect.assert_not_called();assign.assert_not_called()
        engine.branch.resume.assert_called_once_with('task',{})

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
