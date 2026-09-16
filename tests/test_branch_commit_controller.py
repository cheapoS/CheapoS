import json
import unittest
from pathlib import Path
from unittest.mock import Mock
from cheapos import branch_runs
from cheapos.engine import Runtime
from cheapos.workspace import Workspace, git
from test_engine import call
import test_branch_start as fixture


class BranchCommitControllerTests(unittest.TestCase):
    setUp=fixture.BranchStartTests.setUp

    def reviewed(self):
        proposal=self.engine.branch.prepare(self.values)
        task=self.engine.branch.authorize(proposal['task_id'],{'proposal_id':proposal['proposal_id'],'approved':True,'full_suite_approved':True})
        run=task['branch_run'];run['status']='running'
        branch_runs.transition_item(run,'one','working')
        (Path(task['workspace'])/'hello.py').write_text('value=2\n')
        task['status']='running';runtime=Runtime(task)
        def review(rt,messages,tools,role):
            packet=json.loads(messages[1]['content'])
            return call('review_decision',{'decision':'APPROVE','feedback':'Read value=2','candidate_id':packet['candidate_id'],'criteria_outcomes':{'Works':{'passed':True,'evidence':'Read hello.py value=2'}}})
        self.engine.request=Mock(side_effect=review)
        self.engine.checkpoint(runtime,{})
        return runtime,run['items'][0]

    def test_controller_commits_and_updates_mapping_without_human_acceptance(self):
        runtime,item=self.reviewed();task=runtime.task
        self.engine.branch.commit_item(runtime,item)
        saved=self.engine.store.get(task['id']);run=saved['branch_run']
        self.assertEqual(run['items'][0]['status'],'committed')
        self.assertEqual(run['pending_operations'],[])
        self.assertEqual(saved.get('commits',[]),[])
        self.assertEqual(saved['patch'],'')
        self.assertEqual(git(self.source,'show','feature/job:hello.py').strip(),'value=2')
        self.assertEqual((self.source/'hello.py').read_text(),'value=1\n')
        self.assertEqual(len([e for e in run['events'] if e['kind']=='item_completed']),1)

    def test_final_save_failure_recovers_exact_commit_and_one_milestone(self):
        runtime,item=self.reviewed();task=runtime.task
        original=self.engine.store.save
        def fail_final(record):
            if record['branch_run']['items'][0]['status']=='committed':raise OSError('Final write failed')
            original(record)
        self.engine.store.save=fail_final
        with self.assertRaises(OSError):self.engine.branch.commit_item(runtime,item)
        tip=git(self.source,'rev-parse','feature/job')
        self.engine.store.save=original
        saved=self.engine.store.get(task['id']);new_runtime=Runtime(saved)
        self.engine.branch.commit_item(new_runtime,saved['branch_run']['items'][0])
        self.assertEqual(git(self.source,'rev-parse','feature/job'),tip)
        self.assertEqual(len([e for e in saved['branch_run']['events'] if e['kind']=='item_completed']),1)
