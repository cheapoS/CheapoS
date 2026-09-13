import json
from pathlib import Path
from unittest.mock import patch

from cheapos.providers import ProviderError
from cheapos.startup import local_candidates
from cheapos.workspace import git
from test_engine import LocalCase, call


class SampleTests(LocalCase):
    def sample(self, failure=None):
        self.engine.save_preferences({'execution':{'mode':'local','local_model':'fixture-local'}})
        task=self.engine.create_sample()
        requests=[]
        responses=iter([call('read_file',{'path':'math_utils.py'}),
            call('replace_text',{'path':'math_utils.py','old_text':'def clamp(value, lower, upper):\n    return min(value, upper)\n','new_text':'def clamp(value, lower, upper):\n    if lower > upper: raise ValueError("bounds")\n    return max(lower, min(value, upper))\n' if failure!='check' else 'def clamp(value, lower, upper):\n    return value\n'}),
            call('run_checks'),call('checkpoint',{'summary':'Fixed bounds','uncertainties':''})])
        class Provider:
            def __init__(self,role,config): self.role,self.config=role,config
            def complete(self,messages,tools,maximum):
                assert self.config['base_url']=='http://127.0.0.1:11434/v1'
                requests.append(self.role)
                if self.role=='reviewer':
                    if failure=='review':raise ProviderError('Fixture reviewer unavailable')
                    response=call('review_decision',{'decision':'APPROVE','feedback':'Actual four tests pass and bounds are correct.'})
                else: response=next(responses,{'content':'Unable to finish the sample.'})
                return response,{'prompt_tokens':10,'completion_tokens':5,'cost':0}
        self.engine.provider_factory=lambda role,config:Provider(role,config)
        return task,requests

    def test_real_sample_runs_tools_checks_and_separate_local_review(self):
        task,requests=self.sample();source=Path(task['source']);head=git(source,'rev-parse','HEAD');original=(source/'math_utils.py').read_text()
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'approved',result['error'])
        self.assertTrue(result['sample']);self.assertFalse(result['demo'])
        self.assertTrue(result['checks'][-1]['passed']);self.assertEqual(result['checkpoints'][-1]['decision'],'APPROVE')
        self.assertIn('reviewer',requests);self.assertTrue(result['changes'])
        self.assertEqual(git(source,'rev-parse','HEAD'),head);self.assertEqual((source/'math_utils.py').read_text(),original)
        self.assertEqual(result['limits']['dollars'],0);self.assertEqual(result['limits']['run_minutes'],5)
        self.assertEqual(len(self.engine.session_permissions(task['id'])['commands']),1)
        self.assertEqual(self.engine.project_test_grants.visible(task),[])

    def test_failures_never_report_full_loop_success(self):
        for failure in ('check','review'):
            with self.subTest(failure=failure):
                task,requests=self.sample(failure);self.engine.start(task['id']);result=self.finish(task)
                self.assertNotEqual(result['status'],'approved')
                if failure=='check': self.assertFalse(result['checks'][-1]['passed'])
                else:self.assertIn('reviewer',requests)

    def test_cloud_forwarding_alias_is_not_offered_as_local(self):
        def metadata(url,body=None):
            if url.endswith('/api/tags'):return {'models':[{'name':'fixture:cloud'},{'name':'forwarded'},{'name':'installed'}]}
            if url.endswith('/api/ps'):return {'models':[]}
            return {'capabilities':['completion','tools'],**({'remote_host':'fixture.invalid'} if body['model']=='forwarded' else {})}
        with patch('cheapos.startup.local_json',side_effect=metadata):
            self.assertEqual([c['config']['model'] for c in local_candidates()],['installed'])
