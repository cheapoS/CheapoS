"""Pinned deterministic controller fixtures, not a live-model quality benchmark."""
import hashlib
import json
import shlex
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from .engine import Engine
from .workspace import git
from . import metrics


def call(name,**arguments):
    return {'tool_calls':[{'id':'fixture-call','type':'function','function':{'name':name,'arguments':json.dumps(arguments)}}]}


def fixtures():
    base={'math_utils.py':'def clamp(value, lower, upper):\n    return min(value, upper)\n',
          'test_math_utils.py':'import unittest\nfrom math_utils import clamp\nclass Tests(unittest.TestCase):\n    def test_bounds(self):\n        self.assertEqual(clamp(-1,0,10),0)\n        self.assertEqual(clamp(20,0,10),10)\n'}
    edit=call('replace_text',path='math_utils.py',old_text='return min(value, upper)',new_text='return max(lower, min(value, upper))')
    checkpoint=call('checkpoint',summary='Complete the fixed fixture requirement.',uncertainties='')
    approve=call('review_decision',decision='APPROVE',feedback='The actual patch and checks satisfy the fixed requirement.')
    return [
        ('f01','readme',{'README.md':'# Fixture\n','test_readme.py':'import unittest\nfrom pathlib import Path\nclass Tests(unittest.TestCase):\n    def test_usage(self):\n        self.assertIn("Run the tests",Path("README.md").read_text())\n'},'Add the sentence Run the tests to README.',[call('replace_text',path='README.md',old_text='# Fixture',new_text='# Fixture\n\nRun the tests'),checkpoint,approve]),
        ('f02','utility',{'test_utility.py':'import unittest\nfrom utility import square\nclass Tests(unittest.TestCase):\n    def test_square(self):\n        self.assertEqual(square(-3),9)\n        self.assertEqual(square(0),0)\n'},'Create utility.square returning the square of its argument.',[call('write_file',path='utility.py',content='def square(value):\n    return value * value\n'),checkpoint,approve]),
        ('f03','bug_fix',base,'Fix both clamp bounds.',[edit,checkpoint,approve]),
        ('f04','public_link',{'README.md':'# Link question fixture\n'},'Explain https://example.org/fixture without edits.',[call('read_url',url='https://example.org/fixture'),{'content':'The fixture says the verification code is cobalt. Source: https://example.org/fixture'}]),
        ('f05','failed_check_repair',base,'Fix both clamp bounds after observing failing checks.',[call('run_checks'),edit,checkpoint,approve]),
        ('f06','reviewer_revision',base,'Fix bounds and reject inverted ranges.',[edit,checkpoint,call('review_decision',decision='REQUEST_CHANGES',feedback='Also reject inverted ranges and add a regression test.'),call('replace_text',path='math_utils.py',old_text='return max(lower, min(value, upper))',new_text='if lower > upper: raise ValueError("inverted bounds")\n    return max(lower, min(value, upper))'),call('replace_text',path='test_math_utils.py',old_text='class Tests(unittest.TestCase):',new_text='class Tests(unittest.TestCase):\n    def test_inverted(self):\n        with self.assertRaises(ValueError): clamp(1,10,0)'),checkpoint,approve]),
        ('f07','commit_conflict',base,'Fix both clamp bounds.',[edit,checkpoint,approve]),
    ]


def run():
    outcomes=[]
    for fixture_id,kind,files,prompt,responses in fixtures():
        baseline=hashlib.sha256(json.dumps({'files':files,'request':prompt},sort_keys=True).encode()).hexdigest()
        with tempfile.TemporaryDirectory(prefix='cheapos-benchmark-') as directory:
            root=Path(directory);source=root/'source';source.mkdir()
            for name,content in files.items():(source/name).write_text(content)
            git(source,'init','-q');git(source,'config','user.name','Fixture Operator');git(source,'config','user.email','fixture@invalid.local')
            git(source,'add','.');git(source,'commit','-qm','Pinned fixture baseline');head=git(source,'rev-parse','HEAD')
            engine=Engine(root/'state',fixture_delay=0)
            engine.config={role:{'base_url':'http://127.0.0.1:11434/v1','model':'fixture-'+role,'key_env':'CHEAPOS_BENCHMARK_FIXTURE_KEY','input_rate':0,'output_rate':0} for role in ('worker','reviewer')}
            queue=iter(responses)
            class Provider:
                def complete(self,messages,tools,maximum):
                    return next(queue),{'prompt_tokens':10,'completion_tokens':5,'cost':0,'prompt_tokens_details':{'cached_tokens':2},'completion_tokens_details':{'reasoning_tokens':1}}
            engine.provider_factory=lambda *args:Provider()
            try:
                task=engine.create({'repository':str(source),'prompt':prompt,'conversational':True,'check_command':shlex.join([sys.executable,'-m','unittest','discover','-v']),'auto_approve_checks':True})
                with patch('cheapos.web.fetch',return_value=('https://example.org/fixture','text/plain',b'The verification code is cobalt.')):
                    engine.start(task['id']);engine.runtimes[task['id']].thread.join(30)
                assert not engine.runtimes[task['id']].thread.is_alive(),'Fixture exceeded its bounded run'
                task=engine.store.get(task['id']);assert git(source,'rev-parse','HEAD')==head and git(source,'status','--porcelain')==''
                if kind=='public_link':
                    assert task['status']=='awaiting_reply' and not task['changes'] and not task['checks']
                    assert any(e['kind']=='tool' and e['title']=='read url' and 'cobalt' in e['detail']['result']['content'] for e in task['events'])
                    assert any(e['kind']=='assistant' and 'cobalt' in str(e['detail']) and 'https://example.org/fixture' in str(e['detail']) for e in task['events'])
                else:
                    assert task['status']=='approved',task.get('error')
                    assert task['changes'] and task['checks'][-1]['passed'] and task['checkpoints'][-1]['decision']=='APPROVE'
                    engine.reviewed_patch(task)
                    if kind=='failed_check_repair':assert not task['checks'][0]['passed'] and len(task['checks'])==2
                    if kind=='reviewer_revision':assert [c['decision'] for c in task['checkpoints']]==['REQUEST_CHANGES','APPROVE']
                    if kind=='readme':
                        preview=engine.prepare_commit(task['id'])
                        engine.apply_commit(task['id'],{'approved':True,'approval_id':preview['approval_id'],'message':preview['message']})
                        task=engine.store.get(task['id']);assert task['commits'] and not task['patch']
                    if kind=='commit_conflict':
                        (source/'math_utils.py').write_text('# Separate operator change\n')
                        git(source,'add','.');git(source,'commit','-qm','Conflicting fixture change');conflict_head=git(source,'rev-parse','HEAD')
                        try:engine.prepare_commit(task['id'])
                        except ValueError:pass
                        else:raise AssertionError('Conflicting source change was not blocked')
                        assert git(source,'rev-parse','HEAD')==conflict_head
                        task=engine.store.get(task['id']);assert task.get('commit_conflict_observed')
                outcomes.append({'fixture_id':fixture_id,'kind':kind,'baseline_sha256':baseline,'verified_outcome':True,**metrics.aggregate(task)})
            finally:engine.shutdown()
    return {'schema_version':1,'mode':'deterministic_scripted_providers','fixtures':outcomes,'passed':all(item['verified_outcome'] for item in outcomes),
            'limitations':'Pinned source and assertions test controller behavior. No live model quality, speed, savings, or billing claims. Human commit action is simulated only in the disposable fixture.'}
