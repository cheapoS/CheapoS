"""Deterministic publication/CI contracts; no network, models, Git or waits."""
import copy
import threading
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import git_workflow as flow, github, git_sync


class GitWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.task = {'id': 'task', 'source': '/project', 'title': 'Fix parsing',
                     'settings_snapshot': {'values': {'git': {'workflow': 'pull_request', 'remote': 'origin'}}}}
        self.saved = copy.deepcopy(self.task)
        def save(task): self.saved = copy.deepcopy(task)
        self.engine = SimpleNamespace(lock=threading.RLock(), store=SimpleNamespace(get=lambda _: copy.deepcopy(self.saved), save=save),
            admission=SimpleNamespace(require_idle=Mock(), integration=lambda *_: nullcontext()), require_active_task=Mock(), event=Mock())
        self.candidate = {'source': '/project', 'base': 'production', 'head': 'a'*40, 'tree': 'b'*40,
                          'evidence': 'review', 'patch': 'reviewed patch', 'files': ['a.py']}
        self.destination = patch.object(github, 'destination', return_value=('org/repo', 'https://github.com/org/repo.git')).start()
        self.candidate_mock = patch.object(flow, '_candidate', return_value=self.candidate).start()
        self.git = patch.object(flow.work, 'source_git', return_value='').start()
        self.find = patch.object(github, 'find_pull', return_value=None).start()
        self.missing_base = patch.object(flow, 'missing_remote_base', return_value=False).start()
        self.create = patch.object(github, 'api', return_value={'number': 7, 'head': {'sha': 'a'*40}, 'base': {'ref': 'production'}}).start()
        self.sync = patch.object(git_sync, 'synchronize', return_value={'state':'updated', 'retryable':False, 'message':'Updated local production.'}).start()
        self.addCleanup(patch.stopall)

    def approve(self, preview):
        return flow.publish(self.engine, 'task', {'approved': True, 'id': preview['id']})

    def test_failure_before_publication_intent_uses_candidate_readiness(self):
        from cheapos import integration_preparation as prep
        with patch.object(prep,'readiness',return_value={'code':'target_advanced'}) as readiness:
            self.assertEqual(flow.publication_recovery(self.engine,'task'),{'code':'target_advanced'})
        readiness.assert_called_once_with(self.engine,'task')
        self.find.assert_not_called()

    def test_missing_base_preserves_intent_and_does_not_push_or_create(self):
        preview = flow.preview(self.engine, 'task')
        self.missing_base.return_value = True
        with self.assertRaisesRegex(ValueError, 'destination no longer exists'):
            self.approve(preview)
        self.assertEqual(self.saved['pull_request']['state'], 'publishing')
        self.assertFalse(any(call.args[1] == 'push' for call in self.git.call_args_list))
        self.create.assert_not_called()

    def test_deleted_destination_recovery_preserves_candidate_and_requires_new_publication(self):
        from cheapos import integration_preparation as prep
        preview = flow.preview(self.engine, 'task')
        self.missing_base.return_value = True
        with self.assertRaises(ValueError):self.approve(preview)
        original = copy.deepcopy(self.saved['pull_request'])
        self.saved.update(workspace='/copy',patch='reviewed patch',checks=[{'passed':True}],usage={'tokens':42})
        self.saved['integration_preparation'] = {'id':'old-update','status':'ready','target_ref':'refs/heads/production'}
        self.engine.reviewed_patch = Mock()
        self.engine.runtimes = {}
        self.engine.route_restore_stop = threading.Event()
        self.missing_base.side_effect = lambda p: p['base'] == 'production'
        state = {'source':'/project','branch':'refs/heads/main','head':'new-target'}
        with patch.object(flow.commits,'source_state',return_value=state):
            offer = flow.publication_recovery(self.engine, 'task')
            self.assertEqual(offer['previous_base'],'production')
            values = {'approved':True,'operation_id':'replacement',**{k:offer[k] for k in ('publication_id','candidate','target_ref','target_tip')}}
            before = copy.deepcopy(self.saved)
            with patch.object(prep,'_launch') as launch:
                with self.assertRaisesRegex(ValueError,'changed'):
                    prep.start(self.engine,'task',{**values,'publication_id':'stale'})
                self.assertEqual(self.saved,before)
                accepted = prep.start(self.engine,'task',values)
                prep.start(self.engine,'task',values)  # Lost acknowledgement reuses the operation.
            self.assertNotIn('pull_request',accepted)
            self.assertEqual(accepted['pull_request_history'][0]['head'],original['head'])
            self.assertEqual(accepted['pull_request_history'][0]['state'],'superseded')
            self.assertEqual(accepted['usage'],{'tokens':42})
            self.assertEqual(accepted['checks'],before['checks'])
            self.assertEqual(accepted['publication_generation'],1)
            self.assertNotIn('task',self.engine.pull_request_previews)
        # Saved preparation dispatches reconciliation and continuation, retaining authority.
        self.engine.admission.snapshot = Mock(return_value={'interactive':{'allowed':True}})
        self.engine.admission.operations = {}
        self.engine.reconcile_project = Mock()
        self.engine.start = Mock()
        with patch.object(prep,'readiness',return_value={'code':'target_advanced','target_tip':'new-target'}):
            prep._drive(self.engine,'task')
        self.engine.reconcile_project.assert_called_once_with('task',{'patch_digest':offer['candidate']})
        self.engine.start.assert_called_once_with('task')
        # Controller completion uses new review evidence; old publication approval is rejected.
        self.candidate_mock.return_value = {**self.candidate,'base':'main','evidence':'new review','head':'d'*40}
        next_preview = flow.preview(self.engine,'task')
        self.assertNotEqual(next_preview['branch'],original['branch'])
        self.assertEqual(next_preview['base'],'main')
        with self.assertRaises(ValueError):self.approve(preview)
        self.create.return_value = {'number':8,'head':{'sha':'d'*40},'base':{'ref':'main'}}
        self.git.return_value = ''
        self.assertEqual(self.approve(next_preview)['number'],8)

    def test_recovery_does_not_replace_existing_pr_or_available_base(self):
        preview = flow.preview(self.engine,'task')
        self.missing_base.return_value=True
        with self.assertRaises(ValueError):self.approve(preview)
        before=copy.deepcopy(self.saved)
        self.find.return_value={'number':7}
        self.assertIsNone(flow.publication_recovery(self.engine,'task'))
        self.find.return_value=None
        self.missing_base.return_value=False
        self.assertIsNone(flow.publication_recovery(self.engine,'task'))
        self.find.side_effect=ValueError('GitHub unavailable')
        with self.assertRaises(ValueError):flow.publication_recovery(self.engine,'task')
        self.assertEqual(self.saved,before)

    def test_local_is_default_and_rejects_unknown_policy(self):
        self.assertEqual(flow.policy({}), {'workflow': 'local', 'remote': 'origin'})
        for value in ({'workflow':'auto_merge'}, {'remote':'--mirror'}, {'remote':'origin:refs/heads/main'}):
            with self.assertRaises(ValueError):flow.validate_settings(value)

    def test_preview_is_read_only_publication_preserves_base_and_is_idempotent(self):
        preview = flow.preview(self.engine, 'task')
        self.git.assert_not_called();self.create.assert_not_called()
        result = self.approve(preview)
        self.assertEqual(result['url'], 'https://github.com/org/repo/pull/7')
        push = next(c.args for c in self.git.call_args_list if c.args[1] == 'push')
        self.assertEqual(push[-1], 'a'*40 + ':refs/heads/' + preview['branch'])
        self.assertIn('--force-with-lease=refs/heads/' + preview['branch'] + ':', push)
        self.assertNotIn('refs/heads/production', ' '.join(push))
        self.assertEqual(self.create.call_args.args[2]['base'], 'production')
        count = len(self.git.call_args_list)
        self.assertEqual(self.approve(preview), result)
        self.assertEqual(len(self.git.call_args_list), count)
        self.create.assert_called_once()

    def test_missing_approval_changed_candidate_and_changed_destination_do_not_push(self):
        preview = flow.preview(self.engine, 'task')
        with self.assertRaises(ValueError):flow.publish(self.engine, 'task', {'id': preview['id'], 'approved': False})
        self.candidate_mock.return_value = {**self.candidate, 'evidence': 'changed'}
        with self.assertRaisesRegex(ValueError, 'reviewed work changed'):self.approve(preview)
        self.candidate_mock.return_value = self.candidate
        self.destination.return_value = ('different/repo','https://github.com/different/repo.git')
        with self.assertRaisesRegex(ValueError, 'remote changed'):self.approve(preview)
        self.git.assert_not_called();self.create.assert_not_called()

    def test_lost_create_response_recovers_same_pr_without_repeating_push(self):
        preview = flow.preview(self.engine, 'task')
        self.create.side_effect = ValueError('response lost')
        with self.assertRaisesRegex(ValueError, 'response lost'):self.approve(preview)
        self.assertEqual(self.saved['pull_request']['state'], 'publishing')
        self.engine.pull_request_previews = {}  # A restart loses volatile previews.
        self.find.return_value = {'number':7, 'head':{'sha':'a'*40}, 'base':{'ref':'production'}}
        self.git.reset_mock();self.git.return_value = 'a'*40 + '\trefs/heads/' + preview['branch']
        result = self.approve(preview)
        self.assertEqual(result['number'],7)
        self.assertFalse(any(c.args[1]=='push' for c in self.git.call_args_list))
        self.create.assert_called_once()

    def test_external_remote_branch_is_never_overwritten(self):
        preview = flow.preview(self.engine, 'task')
        self.git.return_value = 'c'*40 + '\trefs/heads/other'
        with self.assertRaisesRegex(ValueError, 'will not be overwritten'):self.approve(preview)
        self.assertFalse(any(c.args[1]=='push' for c in self.git.call_args_list))
        self.create.assert_not_called()

    def test_operator_text_is_saved_before_publication_and_retries_keep_it(self):
        self.saved['checkpoints'] = [{'decision': 'APPROVE', 'pull_request': {'title': 'Agent title', 'description': 'Reviewed behavior.'}}]
        preview = flow.preview(self.engine, 'task')
        self.assertEqual(preview['title'], 'Agent title')
        values = {'approved': True, 'id': preview['id'], 'title': 'Operator title', 'description': 'Adjusted description.'}
        self.create.side_effect = ValueError('response lost')
        with self.assertRaisesRegex(ValueError, 'response lost'):
            flow.publish(self.engine, 'task', values)
        self.assertEqual(self.saved['pull_request']['description'], values['description'])
        self.assertEqual(self.create.call_args.args[2]['title'], values['title'])
        self.assertIn(values['description'], self.create.call_args.args[2]['body'])
        with self.assertRaisesRegex(ValueError, 'already started'):
            flow.publish(self.engine, 'task', {**values, 'title': 'Changed after push'})
        self.find.return_value = {'number':7, 'head':{'sha':'a'*40}, 'base':{'ref':'production'}}
        self.git.return_value = 'a'*40 + '\tref'
        self.assertEqual(self.approve(self.saved['pull_request'])['title'], 'Operator title')

    def test_invalid_operator_text_does_not_create_publication_intent(self):
        preview = flow.preview(self.engine, 'task')
        for edited in ({'title': ''}, {'title': 'a\nb', 'description': ''}, {'title':'x', 'description': 2}):
            with self.assertRaises(ValueError):
                flow.publish(self.engine, 'task', {'approved':True, 'id':preview['id'], **edited})
        self.git.assert_not_called(); self.create.assert_not_called()
        self.assertNotIn('pull_request', self.saved)

    def test_reviewed_update_advances_same_pr_with_expected_head_lease(self):
        first = self.approve(flow.preview(self.engine, 'task'))
        self.candidate_mock.return_value = {**self.candidate, 'head':'d'*40, 'tree':'e'*40, 'evidence':'new review'}
        preview = flow.preview(self.engine, 'task')
        self.assertTrue(preview['update'])
        self.find.return_value = {'number':7, 'head':{'sha':first['head']}, 'base':{'ref':'production'}}
        self.create.return_value = {'number':7, 'head':{'sha':'d'*40}, 'base':{'ref':'production'}}
        self.git.reset_mock()
        self.git.side_effect = lambda _, command, *args, **kwargs: first['head']+'\tref' if command == 'ls-remote' else ''
        updated = self.approve(preview)
        self.assertEqual(updated['number'], first['number'])
        self.assertEqual(updated['head'], 'd'*40)
        commands = [c.args for c in self.git.call_args_list]
        self.assertIn(('/project','merge-base','--is-ancestor',first['head'],'d'*40),commands)
        push = next(c for c in commands if c[1]=='push')
        self.assertIn('--force-with-lease=refs/heads/'+first['branch']+':'+first['head'], push)
        self.assertEqual(len(self.saved['pull_request_history']),1)
        self.assertEqual(self.create.call_args.args[1], 'pulls/7')
        self.assertEqual(self.create.call_args.kwargs['method'], 'PATCH')
        self.assertIn('Recorded validation', self.create.call_args.args[2]['body'])

    def test_status_preserves_work_and_only_completes_the_current_merged_candidate(self):
        operation = self.approve(flow.preview(self.engine, 'task'))
        self.saved.update(status='approved', patch='saved edits', usage={'tokens':42})
        for result, expected in [('pending','approved'),('failed','approved'),('changed','approved'),('merged','completed')]:
            with patch.object(github,'checks',return_value={'state':result,'merged_commit':'merge'}):
                flow.status(self.engine,'task')
            self.assertEqual(self.saved['status'],expected)
            self.assertEqual(self.saved['patch'],'saved edits')
            self.assertEqual(self.saved['usage'],{'tokens':42})
        self.saved['status']='approved'
        self.candidate_mock.return_value = {**self.candidate,'evidence':'new work'}
        with patch.object(github,'checks',return_value={'state':'merged','merged_commit':'merge'}):
            flow.status(self.engine,'task')
        self.assertEqual(self.saved['status'],'approved')
        self.assertEqual(self.saved['pull_request']['head'],operation['head'])

    def test_remote_merge_completion_survives_deferred_sync_and_restart(self):
        operation = self.approve(flow.preview(self.engine, 'task'))
        self.saved.update(status='approved', patch='saved edits')
        self.sync.return_value = {'state':'deferred', 'retryable':True, 'message':'Draft preserved.'}
        with patch.object(github,'checks',return_value={'state':'merged','merged_commit':'merge'}):
            result = flow.status(self.engine,'task')
            self.assertEqual(self.saved['status'],'completed')
            self.assertEqual(result['local_sync']['state'],'deferred')
            self.assertEqual(self.saved['pull_request']['merged_head'],operation['head'])
            # Source advance makes the old interactive candidate unavailable;
            # the persisted merge receipt still allows idempotent sync recovery.
            self.candidate_mock.side_effect = ValueError('source advanced')
            self.sync.return_value = {'state':'current', 'retryable':False, 'message':'Already current.'}
            result = flow.status(self.engine,'task')
        self.assertEqual(result['local_sync']['state'],'current')
        self.assertEqual(self.saved['patch'],'saved edits')
        self.sync.assert_called_with('/project','origin','refs/heads/production',
            expected_destination=('org/repo','https://github.com/org/repo.git'), merged_commit='merge')

    def test_busy_repository_persists_sync_retry_and_resumes_without_operator_repair(self):
        self.approve(flow.preview(self.engine, 'task'))
        self.saved.update(status='approved', patch='saved edits')
        self.engine.admission.integration = Mock(side_effect=ValueError('repository operation'))
        with patch.object(github, 'checks', return_value={'state':'merged', 'merged_commit':'merge'}):
            result = flow.status(self.engine, 'task')
            self.assertEqual(self.saved['status'], 'completed')
            self.assertEqual(self.saved['pull_request']['local_sync'], result['local_sync'])
            self.assertTrue(result['local_sync']['retryable'])
            self.sync.assert_not_called()
            self.engine.admission.integration = lambda *_: nullcontext()
            result = flow.status(self.engine, 'task')
        self.assertEqual(result['local_sync']['state'], 'updated')
        self.assertEqual(self.saved['pull_request']['local_sync'], result['local_sync'])
        self.assertEqual(self.saved['patch'], 'saved edits')

    def test_status_does_not_erase_a_receipt_saved_during_github_read(self):
        self.approve(flow.preview(self.engine, 'task'))
        receipt = {'state':'current', 'retryable':False, 'message':'Already current.'}
        def checks(*_):
            self.saved['pull_request']['local_sync'] = receipt.copy()
            self.saved['pull_request']['merged_head'] = 'a'*40
            return {'state':'merged', 'merged_commit':'merge'}
        self.engine.runtimes = {'task':SimpleNamespace(task=copy.deepcopy(self.saved),thread=SimpleNamespace(is_alive=lambda:True))}
        with patch.object(github, 'checks', side_effect=checks):
            result = flow.status(self.engine, 'task')
        self.assertEqual(self.saved['pull_request']['local_sync'], receipt)
        self.assertEqual(result['merged_head'], 'a'*40)
        self.sync.assert_not_called()

    def test_open_changed_and_busy_tasks_do_not_sync(self):
        self.approve(flow.preview(self.engine, 'task'))
        for state in ('open','changed','failed'):
            with patch.object(github,'checks',return_value={'state':state}):flow.status(self.engine,'task')
        self.engine.runtimes = {'task':SimpleNamespace(task=copy.deepcopy(self.saved),thread=SimpleNamespace(is_alive=lambda:True))}
        with patch.object(github,'checks',return_value={'state':'merged','merged_commit':'merge'}):flow.status(self.engine,'task')
        self.assertEqual(self.engine.runtimes['task'].task['pull_request']['ci']['state'], 'merged')
        self.sync.assert_not_called()


class GitHubStatusTests(unittest.TestCase):
    def test_recovery_lookup_finds_a_pr_even_if_its_base_changed(self):
        from urllib.parse import parse_qs, urlsplit
        pull={'number':7,'base':{'ref':'new-main'},'head':{'ref':'task','repo':{'full_name':'org/repo'}}}
        with patch.object(github,'api',return_value=[pull]) as api:
            self.assertEqual(github.find_pull('org/repo','task'),pull)
            self.assertNotIn('base',parse_qs(urlsplit(api.call_args.args[1]).query))
            self.assertIsNone(github.find_pull('org/repo','task','old-base'))

    def test_only_supported_remote_destinations_are_accepted(self):
        for url in ('git@github.com:org/repo.git', 'https://github.com/org/repo.git', 'ssh://git@github.com/org/repo'):
            with patch.object(github, 'source_git', return_value=url):self.assertEqual(github.repository('/x','origin'),'org/repo')
        for url in ('https://token@github.com/org/repo.git', 'file:///tmp/x', 'git@other.test:org/repo', 'ext::command', 'https://github.com/org/repo\nhttps://github.com/org/other'):
            with patch.object(github, 'source_git', return_value=url), self.assertRaises(ValueError):github.repository('/x','origin')

    def test_ci_is_bound_to_exact_head_and_missing_results_never_pass(self):
        with patch.object(github, 'api', return_value={'head': {'sha':'other'}}) as api:
            self.assertEqual(github.checks('org/repo',1,'expected')['state'],'changed')
            api.assert_called_once()
        pull={'head':{'sha':'expected'},'base':{'ref':'production'},'state':'open'}
        for runs, statuses, state in [([],[],'pending'),([{'name':'unit','status':'completed','conclusion':'failure'}],[],'failed'),
                ([{'name':'unit','status':'completed','conclusion':'success'}],[],'passed'),
                ([{'name':'unit','status':'in_progress'}],[],'pending'),
                ([],[{'context':'external','state':'pending'}],'pending')]:
            with self.subTest(state=state), patch.object(github,'api',side_effect=[pull,{'protected':True},{'check_runs':runs},{'statuses':statuses}]):
                result=github.checks('org/repo',1,'expected')
                self.assertEqual(result['state'],state);self.assertTrue(result['protected'])

    def test_merged_and_closed_are_distinct_and_incomplete_checks_remain_pending(self):
        for extra,state in [({'merged':True},'merged'),({'state':'closed'},'closed'),({},'pending')]:
            pull={'head':{'sha':'expected'},'base':{'ref':'master'},'state':'open',**extra}
            with patch.object(github,'api',side_effect=[pull,{'protected':False},{'check_runs':[{'name':'ok','conclusion':'success'}],'total_count':101},{'statuses':[]}]):
                self.assertEqual(github.checks('org/repo',1,'expected')['state'],state)


class NewTaskSyncTests(unittest.TestCase):
    def test_interactive_sync_precedes_snapshot_capture(self):
        from cheapos.engine import Engine
        class Captured(Exception): pass
        snapshot = {'values': {'git': {'workflow':'pull_request'}, 'limits': {'dollars':0}}}
        engine = SimpleNamespace(settings_capture=Mock(return_value=snapshot),
            settings_policy=Mock(return_value={'execution':{'mode':'remote'},'providers':{}}),
            store=SimpleNamespace(root=Path('/fixture')))
        with patch.object(git_sync,'before_task',return_value={'state':'current'}) as sync:
            def capture(*args):
                sync.assert_called_once_with('/project',snapshot)
                raise Captured()
            with patch('cheapos.engine.Workspace.snapshot',side_effect=capture), self.assertRaises(Captured):
                Engine.create(engine,{'repository':'/project','prompt':'Implement a parser','conversational':True})

    def test_unattended_sync_precedes_document_capture(self):
        from cheapos.branch_controller import BranchController
        class Captured(Exception): pass
        snapshot = {'values': {'git': {'workflow':'pull_request'}}}
        engine = SimpleNamespace(lock=threading.RLock(),settings_capture=Mock(return_value=snapshot),
            admission=SimpleNamespace(require=Mock(),pending={}))
        controller = object.__new__(BranchController); controller.engine=engine; controller.planning={}
        with patch.object(git_sync,'before_task',return_value={'state':'current'}) as sync:
            def capture(*args):
                sync.assert_called_once_with('/project',snapshot,'refs/heads/master')
                raise Captured()
            with patch('cheapos.branch_planner.capture_inputs',side_effect=capture), self.assertRaises(Captured):
                controller.plan({'repository':'/project','base_ref':'refs/heads/master','planning_id':'test','prompt':'Implement a parser'})
        self.assertEqual(controller.planning,{})
        self.assertEqual(engine.admission.pending,{})
