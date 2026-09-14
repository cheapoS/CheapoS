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

    def test_measurement_review_can_gather_more_than_eight_distinct_results(self):
        task=self.task(); task['branch_run']['plan']['measurement']=True
        attempts=[]
        def review(runtime,messages,tools,role):
            attempts.append(1)
            schema=tools[-1]['function']['parameters']['properties']['criteria_outcomes']
            self.assertEqual(schema['required'],['Both bounds work'])
            if len(attempts)<=9:
                return call('read_file',{'path':'math_utils.py','start_line':len(attempts),'end_line':len(attempts)})
            packet=json.loads(messages[1]['content'])
            return call('review_decision',{'decision':'APPROVE','feedback':'Inspected implementation','candidate_id':packet['candidate_id'],'criteria_outcomes':{'Both bounds work':{'passed':True,'evidence':'Read code and passing tests'}}})
        self.engine.request=Mock(side_effect=review)
        self.assertEqual(checkpoint(self.engine,Runtime(task),{})['decision'],'APPROVE')
        self.assertEqual(len(attempts),10)

    def test_measurement_repeated_invalid_review_stays_bounded_across_resume(self):
        task=self.task();task['branch_run']['plan']['measurement']=True
        def review(runtime,messages,tools,role):
            packet=json.loads(messages[1]['content'])
            return call('review_decision',{'decision':'APPROVE','feedback':'done','candidate_id':packet['candidate_id'],'criteria_outcomes':{'wrong key':{'passed':True,'evidence':'Tests'}}})
        self.engine.request=Mock(side_effect=review)
        with self.assertRaisesRegex(ProgressPause,'Unsupported|repeated'):checkpoint(self.engine,Runtime(task),{})
        self.assertEqual(self.engine.request.call_count,3)
        feedback=[e['detail']['error'] for e in task['events'] if e['kind']=='review_feedback']
        self.assertIn('Both bounds work',feedback[0]);self.assertIn('wrong key',feedback[0])
        with self.assertRaisesRegex(ProgressPause,'Unsupported|repeated'):checkpoint(self.engine,Runtime(task),{})
        self.assertEqual(self.engine.request.call_count,3)
        self.assertNotIn('ready_receipt',task['branch_run']['items'][0])

    def test_serialized_check_command_does_not_poison_saved_environment(self):
        task=self.task();previous=list(task['check_command'])
        with self.assertRaisesRegex(ValueError,'plain command string'):
            self.engine.checks(Runtime(task),json.dumps(previous))
        self.assertEqual(task['check_command'],previous)
        self.assertNotIn('environment_setup',task)
        runtime=Runtime(task)
        runtime.approval.wait=Mock()  # Decline immediately; never a real wait.
        from cheapos.workspace import Workspace
        from unittest.mock import patch
        with patch.object(Workspace,'run_checks') as execute:
            with self.assertRaisesRegex(InterruptedError,'declined'):
                self.engine.checks(runtime, 'python3 -c \"print(123)\"')
            execute.assert_not_called()
        self.assertTrue(any(e['kind']=='permission' for e in task['events']))
