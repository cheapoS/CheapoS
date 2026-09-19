"""Tiny approval dispatch regressions; no workers, Git, or commands run."""
import threading
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from cheapos.engine import Engine
from cheapos.branch_authorization import CheckScopes


class BranchCommandPermissions(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        workspace=str(Path(temp.name).resolve())
        scope={'command':['runner','test'],'directory':workspace,'profile':None,'fingerprint':'current'}
        task={'id':'t','workspace':workspace,'branch_run':{},'pending_approval':{'id':'p',**scope,'branch_scope':scope.copy()}}
        runtime=SimpleNamespace(task=task,approval=threading.Event(),stop=threading.Event())
        engine=SimpleNamespace(lock=threading.RLock(),require_active_task=Mock(),runtimes={'t':runtime},branch=SimpleNamespace(validate_authority=Mock(),scopes=Mock()),project_test_grants=Mock(),command_permissions={},event=Mock())
        engine.branch.scopes.prepare.return_value=scope
        return engine,runtime,scope

    def test_remember_uses_bound_branch_grant(self):
        engine,runtime,scope=self.fixture()
        Engine.approve_check(engine,'t',True,remember=True,approval_id='p')
        engine.branch.validate_authority.assert_called_once()
        engine.branch.scopes.consent.assert_called_once_with(runtime.task,scope,exact=True)
        self.assertEqual(engine.command_permissions,{})
        self.assertTrue(runtime.approval.is_set())

    def test_stale_scope_and_authority_cannot_grant(self):
        for stale in ('scope','authority','id'):
            engine,runtime,scope=self.fixture()
            if stale=='scope':scope['fingerprint']='changed'
            if stale=='authority':engine.branch.validate_authority.side_effect=ValueError('revoked')
            with self.assertRaises(ValueError):
                Engine.approve_check(engine,'t',True,remember=True,approval_id='old' if stale=='id' else 'p')
            engine.branch.scopes.consent.assert_not_called()
            self.assertFalse(runtime.approval.is_set())

    def test_decline_does_not_grant(self):
        engine,runtime,_=self.fixture()
        Engine.approve_check(engine,'t',False,approval_id='p')
        engine.branch.scopes.consent.assert_not_called()
        engine.project_test_grants.approve.assert_not_called()
        self.assertFalse(runtime.approved)

    def test_exact_consent_does_not_expand_to_profile(self):
        grants=Mock();grants.authorize.return_value=(None,None)
        scopes=CheckScopes(grants)
        value={'command':['runner','test'],'profile':{'runner':'unittest'}}
        scopes.prepare=Mock(return_value=value)
        key=scopes.consent({},value,exact=True)
        self.assertIn(key,scopes.exact_grants)
        grants.approve.assert_not_called()
