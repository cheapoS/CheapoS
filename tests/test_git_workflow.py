"""Deterministic publication/CI contracts; no network, models, Git or waits."""
import copy
import threading
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import git_workflow as flow, github


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
        self.create = patch.object(github, 'api', return_value={'number': 7, 'head': {'sha': 'a'*40}, 'base': {'ref': 'production'}}).start()
        self.addCleanup(patch.stopall)

    def approve(self, preview):
        return flow.publish(self.engine, 'task', {'approved': True, 'id': preview['id']})

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


class GitHubStatusTests(unittest.TestCase):
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
