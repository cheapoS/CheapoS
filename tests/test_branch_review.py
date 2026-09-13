import json
import shlex
from unittest.mock import Mock
from cheapos import branch_runs
from cheapos.engine import Runtime, ProgressPause
from cheapos.branch_review import checkpoint
from test_engine import LocalCase, call


class BranchReviewTests(LocalCase):
    def task(self):
        task = self.fixture(paid=True)
        task['conversational'] = True
        task['providers']['reviewer']['model']='fixture-reviewer'
        task['branch_run'] = branch_runs.new_run({'items':[{'id':'fix','title':'Fix clamp','instructions':'Fix clamp','acceptance_criteria':['Both bounds work'], 'required_checks':[shlex.join(task['check_command'])]}], 'limits':{'working_seconds':600}})
        run = task['branch_run']; run['authorization_ref']='fixture'; run['status']='running';run['expected_feature_tip']='fixture-base'
        branch_runs.transition_item(run,'fix','working')
        self.engine.file_tool(task,'replace_text',{'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'})
        scope = self.engine.branch.scopes.prepare(task, task['check_command'])
        self.engine.branch.scopes.consent(task, scope)
        self.assertTrue(self.engine.branch.scopes.authorize(task, task['check_command']))
        return task

    def test_real_checks_independent_review_receipt_and_reuse(self):
        task=self.task();runtime=Runtime(task)
        def review(runtime,messages,tools,role):
            packet=json.loads(messages[1]['content'])
            return call('review_decision',{'decision':'APPROVE','feedback':'Inspected both bounds','candidate_id':packet['candidate_id'], 'criteria_outcomes':{'Both bounds work':{'passed':True,'evidence':'Tests and code cover lower and upper bounds'}}})
        self.engine.request=Mock(side_effect=review)
        result=checkpoint(self.engine,runtime,{})
        self.assertEqual(result['decision'],'APPROVE')
        item=task['branch_run']['items'][0]
        self.assertEqual(json.loads(item['ready_receipt'])['outcome'],'ready')
        self.assertEqual(len(task['checks']),1)
        item['status']='working';task['status']='running'
        checkpoint(self.engine,runtime,{})
        self.assertEqual(len(task['checks']),1)

    def test_partial_completion_and_same_model_cannot_get_receipt(self):
        task=self.task(); task['providers']['reviewer']=dict(task['providers']['worker'])
        def review(runtime,messages,tools,role):
            packet=json.loads(messages[1]['content'])
            return call('review_decision',{'decision':'APPROVE','feedback':'done','candidate_id':packet['candidate_id'],'criteria_outcomes':{}})
        self.engine.request=Mock(side_effect=review)
        with self.assertRaises(ProgressPause): checkpoint(self.engine,Runtime(task),{})
        self.assertNotIn('ready_receipt',task['branch_run']['items'][0])
