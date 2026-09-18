import copy
import json
import shlex
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace, MethodType
from unittest.mock import Mock, patch

from cheapos.branch_authorization import ProposalRegistry, CheckScopes, contract_builder
from cheapos.branch_runs import new_run
from cheapos.project_permissions import ProjectTestGrants
from cheapos.branch_controller import BranchController
from cheapos.access_policy import snapshot


class SavedPolicyTests(unittest.TestCase):
    """Saved-run authorization with no Git, models, network or real-time waits."""
    def fixture(self):
        settings={'base_url':'http://127.0.0.1:20128/v1','connection_revision':'saved',
                  'included_models':[]}
        policy={'execution':{'mode':'delegate','local_model':'gemma','local_reviewer':''},
                'providers':{'worker':None,'reviewer':None},'gateway_access':snapshot(settings)}
        run=new_run({'items':[{'id':'one','title':'One','instructions':'Implement it',
                              'acceptance_criteria':['Works']}],'limits':{'dollars':0}})
        run.update(model_policy=copy.deepcopy(policy),authorization_workspace={},check_scope=[],
                   workspace_mapping={'stage':'ready'},expected_feature_tip='saved',
                   status='paused',current_item_id=None,pending_operations=[])
        registry=ProposalRegistry()
        contract=contract_builder(run,{},policy,[])
        proposal=registry.prepare('task',contract)
        auth=registry.authorize('task',proposal['proposal_id'],True,contract)
        run.update(authorization=auth,authorization_ref=auth['id'])
        task={'id':'task','branch_run':run,'status':'paused','prompt':'Implement it',
              'providers':{'worker':{'model':'saved-worker'},'reviewer':{'model':'saved-reviewer'}},
              'usage':{'cost':0,'tokens':123},'checks':[{'passed':True,'candidate_id':'saved'}]}
        engine=SimpleNamespace(lock=threading.RLock(),runtimes={},
            require_active_task=Mock(),admission=SimpleNamespace(require=Mock()),
            store=SimpleNamespace(get=lambda _:task,save=Mock()),gateway=SimpleNamespace(settings=settings,pool=Mock()))
        controller=SimpleNamespace(engine=engine,proposals=registry,
            model_policy=Mock(return_value=copy.deepcopy(policy)),launch=Mock(return_value=task))
        controller.contract=MethodType(BranchController.contract,controller)
        controller.validate_authority=MethodType(BranchController.validate_authority,controller)
        controller.scopes=SimpleNamespace(prepare=Mock(),authorize=Mock())
        return task,controller,settings

    def test_resume_keeps_approved_policy_after_global_defaults_change_and_restart(self):
        task,controller,settings=self.fixture();before=copy.deepcopy(task)
        # Match the incident, and cover additional unrelated role/default edits.
        for execution in ({'local_reviewer':'gemma'}, {'mode':'manual'}, {'coordinator_assistance':False}):
            current=copy.deepcopy(task['branch_run']['model_policy'])
            current['execution'].update(execution)
            current['providers']['reviewer']={'model':'new-default'}
            controller.model_policy.return_value=current
            controller.proposals=ProposalRegistry()  # No ephemeral proposal state survives restart.
            restored=json.loads(json.dumps(task));task.clear();task.update(restored)
            with patch('cheapos.branch_workspace.validate_owned'), \
                 patch('cheapos.model_pool.observe_completions'):
                result=BranchController.resume(controller,'task',{})
            self.assertIs(result['task'],task)
            self.assertEqual(task['branch_run']['authorization'],before['branch_run']['authorization'])
            for key in ('providers','usage','checks'):self.assertEqual(task[key],before[key])
        self.assertEqual(controller.launch.call_count,3)
        controller.model_policy.assert_not_called()

    def test_unapproved_proposal_still_detects_changed_defaults(self):
        task,controller,_=self.fixture();run=task['branch_run']
        auth=run.pop('authorization');run.pop('authorization_ref')
        controller.model_policy.return_value['execution']['local_reviewer']='changed'
        with self.assertRaisesRegex(ValueError,'Run scope changed'):
            controller.proposals.validate(auth,controller.contract(task))
        controller.model_policy.assert_called_once()

    def test_captured_draft_defaults_are_bound_without_rereading_live_defaults(self):
        from cheapos.branch_authorization import digest
        task,controller,_=self.fixture();run=task['branch_run']
        run.pop('authorization');run.pop('authorization_ref')
        task['settings_snapshot']={'revision':'captured','values':{'execution':{'mode':'delegate'}}}
        run['settings_snapshot_digest']=digest(task['settings_snapshot'])
        controller.model_policy.return_value={'execution':{'mode':'remote'},'providers':{}}
        result=controller.contract(task)
        self.assertEqual(result['model_policy'],run['model_policy'])
        self.assertEqual(result['settings_snapshot_digest'],run['settings_snapshot_digest'])
        controller.model_policy.assert_not_called()
        task['settings_snapshot']['revision']='different'
        with self.assertRaisesRegex(ValueError,'Captured chat setup changed'):controller.contract(task)

    def test_planning_limits_use_captured_settings_with_explicit_request_overrides(self):
        from cheapos.branch_controller import planning_limits_from_settings
        snapshot={'values':{'limits':{'dollars':0,'run_minutes':12,'worker_turns':45,'iterations':8}}}
        self.assertEqual(planning_limits_from_settings(snapshot,{'worker_turns':60}),
                         {'dollars':0,'working_seconds':720,'worker_turns':60})
        self.assertEqual(snapshot['values']['limits']['worker_turns'],45)

    def test_current_connection_still_validated_and_new_access_is_not_adopted(self):
        task,controller,settings=self.fixture();before=copy.deepcopy(task['branch_run']['authorization'])
        settings['included_models']=['provider/new-model']
        controller.validate_authority(task,task['branch_run'])
        self.assertEqual(controller.contract(task)['model_policy']['gateway_access']['included_models'],[])
        for field,value in (('base_url','http://127.0.0.1:9999/v1'),('connection_revision','replaced')):
            old=settings[field];settings[field]=value
            with self.assertRaisesRegex(ValueError,'Connection access changed'):
                controller.validate_authority(task,task['branch_run'])
            settings[field]=old
        self.assertEqual(task['branch_run']['authorization'],before)

    def test_saved_scope_mutation_or_revocation_still_blocks(self):
        task,controller,_=self.fixture();original=copy.deepcopy(task)
        for kind in ('policy','checks','plan','revoked','reference'):
            task.clear();task.update(copy.deepcopy(original));run=task['branch_run']
            if kind=='policy':run['model_policy']['execution']['mode']='manual'
            if kind=='checks':run['check_scope']=[{'command':['unapproved']}]
            if kind=='plan':run['plan']['items'][0]['instructions']='Different work'
            if kind=='revoked':run['authorization']['status']='revoked'
            if kind=='reference':run['authorization_ref']='different'
            with self.subTest(kind=kind),self.assertRaises(ValueError):controller.validate_authority(task,run)


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.stamp = 1
        self.registry = ProposalRegistry(clock=lambda: self.stamp, ttl=10)
        run = new_run({'items': [{'id': 'one', 'title': 'One', 'instructions': 'Do it', 'acceptance_criteria': ['Works']}], 'limits': {'cost': 1}})
        self.contract = contract_builder(run, {'base_sha': 'base', 'feature_ref': 'refs/heads/feature'}, {'worker': 'a', 'reviewer': 'b'}, [])
        self.proposal = self.registry.prepare('task', self.contract)

    def authorize(self, **kwargs):
        return self.registry.authorize(kwargs.get('task_id', 'task'), kwargs.get('proposal_id', self.proposal['proposal_id']), kwargs.get('approved', True), kwargs.get('current_contract', self.contract))

    def test_exact_idempotent_and_separate_from_token(self):
        first = self.authorize()
        self.assertEqual(first, self.authorize())
        self.assertNotIn(self.proposal['proposal_id'], str(first))
        self.assertTrue(self.registry.validate(first, self.contract))
        first['contract']['limits']['cost'] = 5
        self.assertEqual(self.authorize()['contract']['limits']['cost'], 1)

    def test_expired_missing_cross_task_forged_and_nonboolean(self):
        for kwargs in ({'task_id': 'other'}, {'proposal_id': 'forged'}, {'proposal_id': None}, {'approved': 1}, {'approved': False}, {'approved': 'true'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): self.authorize(**kwargs)
        self.stamp = 11
        with self.assertRaises(ValueError): self.authorize()

    def test_all_scope_changes_rejected(self):
        for field in self.contract:
            changed = copy.deepcopy(self.contract); changed[field] = 'changed'
            with self.subTest(field=field), self.assertRaises(ValueError): self.authorize(current_contract=changed)

    def test_revocation_cannot_be_replayed(self):
        auth = self.authorize()
        self.registry.revoke(auth['id'])
        with self.assertRaises(ValueError): self.authorize()
        with self.assertRaises(ValueError): self.registry.validate(auth, self.contract)

    def test_restart_loses_proposals_but_durable_contract_can_be_revalidated(self):
        auth = self.authorize()
        fresh = ProposalRegistry()
        with self.assertRaises(ValueError): fresh.authorize('task', self.proposal['proposal_id'], True, self.contract)
        self.assertTrue(fresh.validate(auth, self.contract))


class CheckScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        source = root / 'source'; source.mkdir(); (source / '.git').mkdir()
        workspace = root / 'tasks' / 't' / 'workspace'; workspace.mkdir(parents=True); (workspace / '.git').mkdir()
        self.task = {'id': 't', 'source': str(source), 'workspace': str(workspace), 'snapshot': {'source': str(source)}}
        self.store = SimpleNamespace(root=root, list=lambda: [self.task])
        self.grants = ProjectTestGrants(self.store)
        self.scopes = CheckScopes(self.grants)
        self.argv = [sys.executable, '-B', '-m', 'unittest', 'discover']

    def test_profile_reused_for_ordinary_tests_but_not_config_changes(self):
        scope = self.scopes.prepare(self.task, self.argv)
        grant = self.scopes.consent(self.task, scope)
        self.assertEqual(grant, self.scopes.consent(self.task, scope))
        (Path(self.task['workspace']) / 'test_new.py').write_text('# ordinary edit')
        self.assertEqual(grant, self.scopes.authorize(self.task, self.argv))
        (Path(self.task['workspace']) / 'setup.cfg').write_text('[test]')
        self.assertIsNone(self.scopes.authorize(self.task, self.argv))
        with self.assertRaises(ValueError): self.scopes.consent(self.task, scope)

    def test_exact_command_not_prefix_grant_and_restart_expires(self):
        argv = [sys.executable, 'verify.py']
        scope = self.scopes.prepare(self.task, argv)
        self.assertIsNone(scope['profile'])
        self.scopes.consent(self.task, scope)
        self.assertTrue(self.scopes.authorize(self.task, argv))
        self.assertIsNone(self.scopes.authorize(self.task, argv + ['--other']))
        restarted = CheckScopes(ProjectTestGrants(self.store))
        self.assertIsNone(restarted.authorize(self.task, argv))

    def test_revoke_and_cross_workspace(self):
        argv = [sys.executable, 'verify.py']
        grant = self.scopes.consent(self.task, self.scopes.prepare(self.task, argv))
        self.scopes.revoke(grant)
        self.assertIsNone(self.scopes.authorize(self.task, argv))
        other = dict(self.task, workspace=self.task['source'])
        with self.assertRaises(ValueError): self.scopes.prepare(other, argv)

    def approved_file_check(self):
        command = [sys.executable, '-B', '-m', 'unittest', 'examples/penny-pinner/test_pinner.py', '-v']
        scope = self.scopes.prepare(self.task, command)
        self.assertIsNone(scope['profile'])
        self.task['branch_run'] = {'status': 'running', 'check_scope': [scope]}
        grant = self.scopes.consent(self.task, scope)
        return command, grant

    def test_file_check_variants_use_original_argv_without_new_grants(self):
        command, _ = self.approved_file_check()
        before = copy.deepcopy(self.task)
        for args in (['examples/penny-pinner/test_pinner.py'], ['-q', 'examples/penny-pinner/test_pinner.py'],
                     ['examples/penny-pinner/test_pinner.py', '--verbose']):
            variant = [sys.executable, '-m', 'unittest', *args]
            with self.subTest(args=args):
                self.assertEqual(self.scopes.approved_command(self.task, variant), command)
                self.assertIsNone(self.scopes.authorize(self.task, variant))
        self.assertEqual(self.task, before)
        self.assertEqual(len(self.scopes.exact_grants), 1)
        self.assertEqual(self.grants.grants, {})

    def test_file_check_variants_preserve_selection_interpreter_and_execution_flags(self):
        command, _ = self.approved_file_check()
        selector = command[-2]
        variants = [[sys.executable, '-m', 'unittest', *args] for args in (
            ['examples/penny-pinner/test_other.py'], [selector, 'other.test'],
            [selector, '-f'], [selector, '-b'], [selector, '-k', 'one'],
            [selector, '--unknown'], ['discover'], [], ['-v'])]
        variants.extend(([sys.executable, '-I', *command[2:]],
                         ['/another/python', *command[2:]],
                         [sys.executable, '-m', 'pytest', selector]))
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertEqual(self.scopes.approved_command(self.task, variant), variant)

    def test_file_check_variants_require_current_unrevoked_authority(self):
        command, grant = self.approved_file_check()
        variant = [sys.executable, '-m', 'unittest', command[-2]]
        fresh = CheckScopes(ProjectTestGrants(self.store))
        self.assertEqual(fresh.approved_command(self.task, variant), variant)
        other = dict(self.task, workspace=self.task['source'])
        self.assertEqual(self.scopes.approved_command(other, variant), variant)
        config = Path(self.task['workspace']) / 'setup.cfg'
        config.write_text('[test]')
        self.assertEqual(self.scopes.approved_command(self.task, variant), variant)
        config.unlink()
        self.scopes.revoke(grant)
        self.assertEqual(self.scopes.approved_command(self.task, variant), variant)

    def check_engine(self):
        """Actual dispatch/permissions with tiny directories; no Git or subprocess."""
        from cheapos.engine import Engine
        command, _ = self.approved_file_check()
        self.task.update(conversational=True, check_command=command, checks=[],
                         patch='saved patch', tool_actions=0, status='running',
                         limits={'check_seconds': 90, 'run_minutes': 15})
        engine = Engine.__new__(Engine)
        engine.lock = threading.RLock()
        engine.branch = SimpleNamespace(scopes=self.scopes)
        engine.project_test_grants = self.grants
        engine.command_permissions = {}
        engine.store = SimpleNamespace(root=self.store.root, publish=Mock())
        engine.admission = SimpleNamespace(resource=lambda *args: nullcontext())
        engine.event = Mock()
        engine.refresh_changes = Mock()
        engine.worker_check_feedback = lambda runtime, result: result
        engine.checkpoint_feedback = Mock(return_value={'decision': 'APPROVE'})
        runtime = SimpleNamespace(task=self.task, started=time.monotonic(),
                                  stop=threading.Event(), guard=Mock(),
                                  approval=Mock())
        runtime.approval.wait.side_effect = AssertionError('Operator permission requested')
        return engine, runtime, command

    def test_approved_variant_runs_once_and_reaches_independent_review_without_operator(self):
        engine, runtime, command = self.check_engine()
        variant = [sys.executable, '-m', 'unittest', command[-2]]
        with patch('cheapos.engine.reconciliation.ensure_resolved'), \
             patch('cheapos.engine.environment.inspect', return_value={'status': 'ready'}), \
             patch('cheapos.engine.evidence_identity', return_value='same-inputs'), \
             patch('cheapos.verification.evidence_identity', return_value='same-inputs'), \
             patch('cheapos.engine.Workspace') as workspace:
            workspace.return_value.patch.return_value = self.task['patch']
            workspace.return_value.run_checks.side_effect = lambda argv, *a, **kw: {
                'command': list(argv), 'passed': True, 'exit_code': 0, 'output': 'OK'}
            result = engine.worker_checks(runtime, {'command': shlex.join(variant)})
            self.assertTrue(result['passed'])
            self.assertEqual(result['command'], command)
            self.assertEqual(self.task['checks'][0]['command'], command)
            self.assertEqual(workspace.return_value.run_checks.call_args.args[0], command)
            engine.checkpoint_feedback.assert_not_called()
            # Another request for the variant reuses the exact approved receipt
            # and goes to the independent reviewer instead of a retest loop.
            self.assertEqual(engine.worker_checks(runtime, {'command': shlex.join(variant)}), {'decision': 'APPROVE'})
            workspace.return_value.run_checks.assert_called_once()
        engine.checkpoint_feedback.assert_called_once()
        runtime.approval.wait.assert_not_called()
        self.assertNotIn('pending_approval', self.task)
        self.assertEqual(len(self.task['checks']), 1)
        rewrites = [call.args[3] for call in engine.event.call_args_list if call.args[1] == 'check_command']
        self.assertEqual(rewrites[0], {'requested_command': variant, 'command': command})

    def test_stale_check_grant_still_requests_permission_without_running(self):
        engine, runtime, command = self.check_engine()
        (Path(self.task['workspace']) / 'setup.cfg').write_text('[changed]')
        variant = [sys.executable, '-m', 'unittest', command[-2]]
        with patch('cheapos.engine.reconciliation.ensure_resolved'), \
             patch('cheapos.engine.environment.inspect', return_value={'status': 'ready'}), \
             patch('cheapos.engine.Workspace') as workspace:
            with self.assertRaisesRegex(AssertionError, 'Operator permission requested'):
                engine.checks(runtime, shlex.join(variant))
        workspace.assert_not_called()
        self.assertEqual(self.task['status'], 'waiting_approval')
        self.assertEqual(self.task['pending_approval']['command'], variant)
    def test_authorized_branch_run_auto_consents_profile_and_check_scope(self):
        verify_argv = [sys.executable, 'verify.py']
        scope = self.scopes.prepare(self.task, verify_argv)
        branch_task = dict(self.task, branch_run={'authorization_ref': 'auth-123', 'check_scope': [scope]})
        self.assertTrue(self.scopes.authorize(branch_task, verify_argv))
        self.assertTrue(self.scopes.authorize(branch_task, self.argv))


if __name__ == '__main__': unittest.main()
