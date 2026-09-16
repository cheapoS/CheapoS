"""Retest/resume state transitions without Git, subprocesses, waits or inference."""
import copy
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_review, branch_runs, progress, verification
from cheapos.branch_controller import BranchController
from cheapos.engine import Engine
from cheapos.providers import ProviderError


def call(name, args):
    return {'role':'assistant','tool_calls':[{'id':'read-1','function':{'name':name,'arguments':json.dumps(args)}}]}


class RetestRecoveryTests(unittest.TestCase):
    def test_compact_context_keeps_file_directory_bounded_without_losing_requirements(self):
        task={'source':'unused','workspace':'unused','changes':[],'events':[],'compact_edits':True,
              'prompt':'Implement restart','requests':['Implement restart','Preserve exact arguments'],
              'checks':[],'checkpoints':[],'check_command':['python3','-m','unittest']}
        names=['tests/module_%04d.py'%i for i in range(500)]
        with patch('cheapos.engine.Workspace') as workspace, \
             patch('cheapos.engine.project_context.brief',return_value={}), \
             patch('cheapos.engine.project_context.continuation',return_value={'active_requirements':task['requests']}):
            workspace.return_value.list_files.return_value=names
            engine=SimpleNamespace(carto=SimpleNamespace(context=Mock(return_value={'status':'disabled'})))
            messages=Engine.action_messages(engine,task)
        packet=json.loads(messages[1]['content'])
        self.assertEqual(packet['available_files'],names[:60])
        self.assertEqual(packet['file_listing']['total'],500)
        self.assertTrue(packet['file_listing']['partial'])
        self.assertEqual(packet['continuation_record']['active_requirements'],task['requests'])

    def record(self):
        return {'command':['python3','-m','unittest','tests.test_http'], 'passed':True,
                'exit_code':0,'outcome':'passed','input_identity':'inputs',
                'verification_identity':'inputs','digest':'patch','output':'Ran 34 tests in 20.1s\nOK'}

    def test_passed_timing_output_is_not_progress_but_changed_inputs_and_failure_are(self):
        task={'patch':'patch','checks':[self.record()]}
        progress.state(task)
        for elapsed in ('21.5','0.5','24.89'):
            task['checks'][-1]['output']=f'Ran 34 tests in {elapsed}s\nOK'
            self.assertFalse(progress.observe(task))
        task['checks'][-1]['verification_identity']='changed environment'
        self.assertTrue(progress.observe(task))
        task['checks'][-1].update(passed=False,outcome='test_failure',output='FAILED assertion')
        self.assertTrue(progress.observe(task))
        restored=json.loads(json.dumps(task))
        self.assertFalse(progress.observe(restored))

    def test_reuse_requires_complete_success_and_current_exact_input_identity(self):
        record=self.record();task={'checks':[record]};argv=record['command']
        with patch.object(verification,'evidence_identity',return_value='inputs') as identity:
            self.assertIs(verification.reusable_check(task,argv),record)
            for changes in ({'passed':False},{'exit_code':1},{'reason':'cancelled'},
                            {'truncated':True},{'outcome':'inputs_changed'},
                            {'input_identity':'old'},{'verification_identity':None}):
                with self.subTest(changes=changes):
                    self.assertIsNone(verification.reusable_check({'checks':[{**record,**changes}]},argv))
            self.assertIsNone(verification.reusable_check(task,[*argv,'-v']))
            self.assertIsNone(verification.reusable_check({'checks':[record,{**record,'passed':False}]},argv))
            for current in ('changed-files','changed-runner','changed-config',None):
                identity.return_value=current
                self.assertIsNone(verification.reusable_check(task,argv))

    def test_engine_reuse_does_not_run_subprocess_or_request_execution_permission(self):
        record=self.record();task={'id':'task','checks':[record],'tool_actions':2,'check_command':record['command'],'branch_run':{'status':'running'}}
        engine=SimpleNamespace(verification_argv=Mock(return_value=record['command']),event=Mock())
        with patch('cheapos.engine.reconciliation.ensure_resolved'), \
             patch('cheapos.engine.environment.inspect',return_value={'status':'ready'}), \
             patch.object(verification,'evidence_identity',return_value='inputs'), \
             patch('cheapos.engine.Workspace') as workspace:
            result=Engine.checks(engine,SimpleNamespace(task=task,guard=lambda:None))
        workspace.assert_not_called()
        self.assertTrue(result['reused']);self.assertEqual(task['tool_actions'],3)
        self.assertEqual(task['checks'],[record]);self.assertNotIn('reused',record)
        self.assertEqual(result['verification_identity'],'inputs')

    def test_repeat_test_advances_to_review_without_assuming_approval(self):
        engine=SimpleNamespace(checks=Mock(return_value={'reused':True}),event=Mock(),
                               checkpoint_feedback=Mock(return_value={'decision':'REQUEST_CHANGES'}))
        runtime=SimpleNamespace(task={'branch_run':{'status':'running'}})
        result=Engine.worker_checks(engine,runtime,{})
        self.assertEqual(result['decision'],'REQUEST_CHANGES')
        self.assertEqual(engine.checkpoint_feedback.call_count,1)
        Engine.worker_checks(engine,runtime,{},last_call=False)
        runtime.task['branch_run'].update(current_item_id='one',items=[{'id':'one','review_repair':{'defects':['Needs a disposition']}}])
        Engine.worker_checks(engine,runtime,{})
        engine.checks.return_value={'passed':False}
        Engine.worker_checks(engine,runtime,{})
        runtime.task={};engine.checks.return_value={'reused':True}
        Engine.worker_checks(engine,runtime,{})
        self.assertEqual(engine.checkpoint_feedback.call_count,1)

    def test_resume_review_skips_worker_and_only_request_changes_returns_to_worker(self):
        engine=SimpleNamespace(event=Mock(),initial_messages=Mock(return_value=[]),_run_with_wait=Mock())
        controller=SimpleNamespace(engine=engine)
        runtime=SimpleNamespace(task={'pending_review':{'worker_summary':'Original work','repair_dispositions':[{'finding_id':'one','evidence':'Retained correction'}]}})
        item={'id':'one','status':'reviewing'}
        with patch.object(branch_review,'checkpoint',return_value={'decision':'APPROVE'}) as review:
            BranchController.continue_item(controller,runtime,item)
            engine._run_with_wait.assert_not_called()
            self.assertEqual(review.call_args.args[2]['summary'],'Original work')
            self.assertEqual(review.call_args.args[2]['repair_dispositions'],runtime.task['pending_review']['repair_dispositions'])
            review.return_value={'decision':'REQUEST_CHANGES'}
            BranchController.continue_item(controller,runtime,item)
            engine._run_with_wait.assert_called_once()

    def test_unittest_paths_do_not_corrupt_executable_discovery_or_filters(self):
        for name in ('tests/test_http.py','tests/test_http','tests.test_http.py','./tests/test_http.py'):
            self.assertEqual(verification.normalize_unittest(['.venv/bin/python','-m','unittest','-v',name]),
                             ['.venv/bin/python','-m','unittest','-v','tests.test_http'])
        for argv in (['.venv/bin/python','-m','unittest','discover','-s','tests/unit','-p','test_*.py'],
                     ['python3','-m','unittest','-k','some/filter.py','tests.test_http'],
                     ['python3','script.py'],['python3','-m','other','file.py'],
                     ['python3','-m','unittest','/tmp/tests/test_http.py']):
            self.assertEqual(verification.normalize_unittest(argv),argv)

    def test_review_transcript_survives_failure_and_reuses_checks_without_replaying_reads(self):
        run=branch_runs.new_run({'items':[{'id':'one','title':'Fix','instructions':'Fix',
              'acceptance_criteria':['Works'],'required_checks':['python3 -m unittest']}],
              'limits':{'working_seconds':600}})
        run.update(status='running',expected_feature_tip='tip',current_item_id='one')
        run['items'][0]['status']='working'
        task={'branch_run':run,'active_role':'worker','checks':[],'review_count':0,'checkpoints':[],
              'providers':{'worker':'worker','reviewer':'reviewer'}}
        runtime=SimpleNamespace(task=task,guard=lambda:None,stop=threading.Event())
        engine=SimpleNamespace(store=SimpleNamespace(save=Mock()),event=Mock(),checks=Mock(),
               file_tool=Mock(return_value={'content':'The already inspected function'}),
               parse_call=lambda c:(c['function']['name'],json.loads(c['function']['arguments'])),request=Mock())
        def interrupted(rt,messages,tools,role):
            task['pending_review']['review_requests']+=1
            if engine.request.call_count==1:return call('read_file',{'path':'code.py'})
            raise ProviderError('connection interrupted')
        engine.request.side_effect=interrupted
        current={'id':'candidate','checks':[],'patch':'diff'}
        with patch.object(branch_review.evidence,'candidate',return_value=current), \
             patch.object(branch_review.evidence,'current_checks',return_value=[]), \
             patch.object(branch_review.evidence,'review_packet',return_value={}), \
             patch.object(branch_review.evidence,'ready_receipt',return_value='receipt'), \
             patch.object(branch_review.evidence,'revalidate'):
            with self.assertRaises(ProviderError):branch_review.checkpoint(engine,runtime,{'summary':'Done'})
            runtime.task=json.loads(json.dumps(task));restored=runtime.task
            self.assertEqual(restored['pending_review']['review_requests'],2)
            def finish(rt,messages,tools,role):
                self.assertEqual(role,'reviewer')
                self.assertIn('The already inspected function',json.dumps(messages))
                self.assertEqual(rt.task['pending_review']['review_requests'],2)
                return call('review_decision',{'decision':'APPROVE','candidate_id':'candidate',
                     'feedback':'Inspected code and check evidence','criteria_outcomes':{'Works':{'passed':True,'evidence':'Read code'}}})
            engine.request.side_effect=finish
            result=branch_review.checkpoint(engine,runtime,{})
        self.assertEqual(result['decision'],'APPROVE')
        engine.checks.assert_not_called();engine.file_tool.assert_called_once()
        self.assertEqual(restored['branch_run']['items'][0]['ready_receipt'],'receipt')

    def test_history_bounds_keep_complete_exchanges(self):
        pending={};base=[{'role':'system'},{'role':'user'}]
        unfinished=call('read_file',{'path':'do_not_replay.py'})
        branch_review.save_history(pending,base+[unfinished])
        self.assertEqual(pending['messages'],[])
        huge=call('read_file',{'path':'huge.py'})
        branch_review.save_history(pending,base+[huge,{'role':'tool','tool_call_id':'read-1','content':'x'*60001}])
        self.assertEqual(pending['messages'],[]);self.assertTrue(pending['history_partial'])


if __name__=='__main__':unittest.main()
