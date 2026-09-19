import json
import os
import sys
from pathlib import Path

from cheapos import environment
from cheapos.workspace import Workspace,git
from test_engine import LocalCase,call


class EnvironmentTests(LocalCase):
    def test_missing_executable_environment_and_guidance_are_read_only(self):
        task=self.fixture();root=Path(task['workspace'])
        (root/'README.md').write_text('Prepare this task copy:\n```sh\npython3 -m venv .venv\n.venv/bin/python -m pip install -r requirements.txt\n```\n')
        (root/'requirements.txt').write_text('pytest\n')
        missing=environment.inspect(task,['fixture-command-that-does-not-exist'])
        self.assertEqual(missing['missing'],'executable')
        missing=environment.inspect(task,['.venv/bin/python','-m','pytest'])
        self.assertEqual(missing['missing'],'selected_environment')
        self.assertEqual(missing['setup_commands'],['python3 -m venv .venv','.venv/bin/python -m pip install -r requirements.txt'])
        self.assertFalse((root/'.venv').exists())

    def test_declared_pytest_absence_is_conservative_about_custom_paths(self):
        task=self.fixture();root=Path(task['workspace']);prefix=root/'.venv';(prefix/'bin').mkdir(parents=True)
        runner=prefix/'bin/python';runner.write_text('#!/bin/sh\nexit 99\n');runner.chmod(0o700)
        (prefix/'pyvenv.cfg').write_text('include-system-site-packages = false\n')
        (root/'requirements.txt').write_text('pytest==8.0\n')
        argv=['.venv/bin/python','-m','pytest'];self.assertEqual(environment.inspect(task,argv)['missing'],'declared_pytest')
        site=prefix/'lib/python3.9/site-packages';site.mkdir(parents=True);(site/'custom.pth').write_text('import must_never_execute\n')
        self.assertEqual(environment.inspect(task,argv)['status'],'ready')
        (site/'custom.pth').unlink();(site/'pytest').mkdir()
        self.assertEqual(environment.inspect(task,argv)['status'],'ready')

    def test_setup_resume_rechecks_without_restarting_implementation(self):
        task=self.fixture(paid=True);root=Path(task['workspace']);source=Path(task['source']);head=git(source,'rev-parse','HEAD')
        self.engine.file_tool(task,'replace_text',{'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'})
        task['check_command']=['.venv/bin/python','-m','unittest','discover','-v'];self.engine.store.save(task)
        replies=iter([call('run_checks'),call('checkpoint',{'summary':'Fixed bounds','uncertainties':''}),call('review_decision',{'decision':'APPROVE','feedback':'Actual tests passed.'})]);requests=[]
        class Provider:
            def complete(self,messages,tools,maximum):
                requests.append(messages);return next(replies),{'prompt_tokens':5,'completion_tokens':5,'cost':0}
        self.engine.provider_factory=lambda *args:Provider();self.engine.start(task['id']);paused=self.finish(task)
        self.assertEqual(paused['error_code'],'environment_setup');self.assertEqual(paused['checks'],[])
        with self.assertRaisesRegex(ValueError,'(?i)re-check'):self.engine.start(task['id'])
        self.assertEqual(len(requests),1)
        runner=root/'.venv/bin/python';runner.parent.mkdir(parents=True);runner.symlink_to(sys.executable)
        ready=self.engine.recheck_environment(task['id']);self.assertEqual(ready['environment_setup']['status'],'ready')
        self.assertEqual(ready['workspace_generation'],1);self.assertEqual(ready['patch'],paused['patch'])
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'approved',result['error']);self.assertEqual(len(result['checks']),1)
        self.assertEqual(len(requests),3);self.assertEqual(git(source,'rev-parse','HEAD'),head)

    def test_project_import_error_remains_actual_test_failure(self):
        task=self.fixture();root=Path(task['workspace'])
        (root/'test_broken.py').write_text('from math_utils import nonexistent_project_function\n')
        self.assertEqual(environment.inspect(task,task['check_command'])['status'],'ready')
        import threading
        result=Workspace(root).run_checks(task['check_command'],threading.Event(),timeout=10)
        self.assertFalse(result['passed']);self.assertIn('ImportError',result['output']);self.assertIn('nonexistent_project_function',result['output'])
