import copy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cheapos.branch_authorization import ProposalRegistry, CheckScopes, contract_builder
from cheapos.branch_runs import new_run
from cheapos.project_permissions import ProjectTestGrants


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


if __name__ == '__main__': unittest.main()
