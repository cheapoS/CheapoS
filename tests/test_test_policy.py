import unittest
from types import SimpleNamespace
from cheapos import test_policy as policy

class TestPolicyTests(unittest.TestCase):
    def task(self):
        return {'source':'/repo','branch_run':{'test_policy_version':1,'plan':{
            'items':[{'required_checks':['python3 -m unittest discover -v tests']}],
            'final_checks':['python3 -m unittest discover -v tests']}}}

    def test_recognizes_broad_commands_without_blocking_targeted_checks(self):
        for command in ('python3 -m unittest discover -v tests','python3 -m unittest -v',
                        'pytest tests','python3 -m pytest','python3 scripts/check.py --full',
                        'python3 scripts/dev_tests.py --suite full'):
            self.assertTrue(policy.full_suite(command),command)
        for command in ('python3 -m unittest tests.test_http -v','python3 -m unittest discover -p test_http.py',
                        'pytest tests/test_http.py','python3 scripts/check.py --files dist/app.js',
                        'python3 scripts/dev_tests.py --pattern test_http.py'):
            self.assertFalse(policy.full_suite(command),command)

    def test_approval_is_explicit_exact_and_required_at_dispatch(self):
        task=self.task();command=task['branch_run']['plan']['final_checks'][0]
        for value in (None,False,'true',1):
            with self.assertRaises(ValueError):policy.approve(task,value)
        with self.assertRaises(ValueError):policy.guard(task,command)
        task['execution']={'development_mode':True}
        with self.assertRaises(ValueError):policy.guard(task,command)
        policy.approve(task,True);policy.guard(task,command)
        with self.assertRaises(ValueError):policy.guard(task,'pytest tests')
        self.assertEqual(len(task['full_suite_approval']),1)

    def test_existing_approved_run_keeps_only_captured_commands(self):
        task=self.task();task['branch_run'].pop('test_policy_version');task['branch_run']['authorization_ref']='old'
        policy.guard(task,'python3 -m unittest discover -v tests')
        with self.assertRaises(ValueError):policy.guard(task,'pytest tests')

    def test_disclosure_uses_same_project_measured_duration(self):
        task=self.task();engine=SimpleNamespace(store=SimpleNamespace(tasks={'saved':{
            'source':'/repo','checks':[{'command':['python3','-m','unittest','discover','-v','tests'],'duration':874.3,'time':'2026-09-15'}]}}))
        self.assertEqual(policy.disclosure(engine,task)['full_suite_last_seconds'],874.3)
        task['source']='/different';self.assertIsNone(policy.disclosure(engine,task)['full_suite_last_seconds'])

    def test_engine_dispatch_does_not_treat_takeover_as_full_suite_consent(self):
        from cheapos.engine import Engine, CheckCommandError
        task=self.task();task.update(conversational=True,check_command=['python3','-m','unittest','discover'],execution={'development_mode':True})
        engine=Engine.__new__(Engine)
        with self.assertRaises(CheckCommandError):engine.verification_argv(task)
        self.assertEqual(engine.verification_argv(task,'python3 -m unittest tests.test_http'),['python3','-m','unittest','tests.test_http'])

    def test_plan_only_is_not_verification_even_when_previously_validated(self):
        from cheapos.engine import Engine, CheckCommandError
        command=['python3','-B','scripts/check.py','--plan']
        task=dict(conversational=True, check_command=command, validated_check_command=command, limits={'uncapped_work':True})
        with self.assertRaisesRegex(CheckCommandError, 'lists checks but runs none'):
            Engine.__new__(Engine).verification_argv(task)
        self.assertEqual(task['check_command'], command)
        policy.require_verification('python3 -B scripts/check.py --files dist/app.js')

    def test_historical_plan_record_cannot_be_bound_as_evidence(self):
        from cheapos.branch_evidence import bind_check
        command=['python3','scripts/check.py','--plan']
        current={'checks':[{'command':command,'verification_identity':'same'}]}
        record=dict(command=command,passed=True,exit_code=0,verification_identity='same',input_identity='same')
        with self.assertRaisesRegex(ValueError, 'lists checks'):
            bind_check(current, command, record)
