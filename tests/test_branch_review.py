import json
import shlex
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))

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
        component=Path(task['workspace'])/'component';component.mkdir()
        (component/'check.py').write_text("from pathlib import Path\nassert Path.cwd().name == 'component'\nprint('component verified')\n")
        command=[sys.executable,'-B','check.py']
        spec={'command':command,'directory':'component'}
        run=task['branch_run'];run['items'][0]['required_checks']=[spec];run['plan']['items'][0]['required_checks']=[spec]
        run['current_item_id']='fix'
        scope=self.engine.branch.scopes.prepare(task,command,directory='component')
        self.engine.branch.scopes.consent(task,scope);run['check_scope']=[scope]
        def review(runtime,messages,tools,role):
            packet=json.loads(messages[1]['content'])
            self.assertEqual(packet['checks'][0]['directory'], 'component')
            self.assertEqual(packet['checks'][0]['record']['directory'], 'component')
            return call('review_decision',{'decision':'APPROVE','feedback':'Inspected both bounds','candidate_id':packet['candidate_id'], 'criteria_outcomes':{'Both bounds work':{'passed':True,'evidence':'Tests and code cover lower and upper bounds'}}})
        self.engine.request=Mock(side_effect=review)
        result=checkpoint(self.engine,runtime,{})
        self.assertEqual(result['decision'],'APPROVE')
        item=task['branch_run']['items'][0]
        self.assertEqual(json.loads(item['ready_receipt'])['outcome'],'ready')
        self.assertEqual(len(task['checks']),1)
        item['status']='working';task['status']='running'
        result=self.engine.worker_checks(runtime,{'command':shlex.join(task['check_command'])})
        self.assertEqual(result['decision'],'APPROVE')
        self.assertEqual(len(task['checks']),1)
        self.assertEqual(self.engine.request.call_count,2)
        self.assertTrue(any(e['title']=='Taking verified changes to independent review' for e in task['events']))

    def test_checkpoint_filters_spurious_plan_preview_when_real_checks_exist(self):
        task = self.task()
        task['branch_run']['items'][0]['required_checks'].append('python3 -B scripts/check.py --plan')
        runtime = Runtime(task)
        def review(runtime, messages, tools, role):
            packet = json.loads(messages[1]['content'])
            return call('review_decision', {'decision': 'APPROVE', 'feedback': 'Inspected both bounds', 'candidate_id': packet['candidate_id'], 'criteria_outcomes': {'Both bounds work': {'passed': True, 'evidence': 'Tests pass'}}})
        self.engine.request = Mock(side_effect=review)
        result = checkpoint(self.engine, runtime, {})
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertNotIn('python3 -B scripts/check.py --plan', task['branch_run']['items'][0]['required_checks'])

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

    def test_branch_review_packet_paging_thresholds_and_plan_trimming(self):
        task = self.task()
        run = task['branch_run']
        cmd_str = shlex.join(task['check_command'])
        run['plan']['items'] = [
            {'id': 'fix', 'title': 'Fix clamp', 'instructions': 'Fix clamp instructions', 'acceptance_criteria': ['Both bounds work'], 'required_checks': [cmd_str], 'status': 'working'},
            {'id': 'm2', 'title': 'Second milestone', 'instructions': 'Bulky instructions ' * 20, 'acceptance_criteria': ['Criterion 2'], 'status': 'pending'}
        ]
        inspected_packet = {}
        def review(runtime, messages, tools, role):
            nonlocal inspected_packet
            inspected_packet = json.loads(messages[1]['content'])
            return call('review_decision', {
                'decision': 'APPROVE',
                'feedback': 'ok',
                'candidate_id': inspected_packet['candidate_id'],
                'criteria_outcomes': {'Both bounds work': {'passed': True, 'evidence': 'Passed'}}
            })
        self.engine.request = Mock(side_effect=review)
        result = checkpoint(self.engine, Runtime(task), {})
        self.assertEqual(result['decision'], 'APPROVE')

        # Verify plan trimming: non-current item 'm2' has only id, title, status
        items = inspected_packet['plan']['items']
        m2 = next(it for it in items if it['id'] == 'm2')
        self.assertEqual(m2, {'id': 'm2', 'title': 'Second milestone', 'status': 'pending'})
        self.assertNotIn('instructions', m2)
        self.assertNotIn('acceptance_criteria', m2)

        # Current item retains instructions
        fix = next(it for it in items if it['id'] == 'fix')
        self.assertIn('instructions', fix)

        # Small packets remain direct; large packets use exhaustive paging.
        from cheapos import branch_evidence
        orig_review_packet = branch_evidence.review_packet
        try:
            # 1. 50,000 characters passes (exceeds old 30,000 limit)
            run['items'][0]['status'] = 'working'
            run['items'][0].pop('ready_receipt', None)
            task['status'] = 'running'
            def large_packet(*args, **kwargs):
                pkt = orig_review_packet(*args, **kwargs)
                pkt['uncertainties'] = 'x' * (50000 - len(json.dumps(pkt)))
                return pkt

            branch_evidence.review_packet = large_packet
            result = checkpoint(self.engine, Runtime(task), {})
            self.assertEqual(result['decision'], 'APPROVE')

            # 2. 65,000 characters delegates to the paged-review path.
            run['items'][0]['status'] = 'working'
            run['items'][0].pop('ready_receipt', None)
            task['status'] = 'running'
            def over_limit_packet(*args, **kwargs):
                pkt = orig_review_packet(*args, **kwargs)
                pkt['uncertainties'] = 'x' * 65000
                return pkt

            branch_evidence.review_packet = over_limit_packet
            with patch('cheapos.branch_review_pages.prepare', side_effect=lambda e, rt, cur, pkt:
                       ({**pkt, 'uncertainties': 'Reviewed in retained pages'}, None, None)) as pages:
                self.assertEqual(checkpoint(self.engine, Runtime(task), {})['decision'], 'APPROVE')
                pages.assert_called_once()
                self.assertEqual(len(pages.call_args.args[3]['uncertainties']), 65000)

            # 3. 70,000 characters with review_repair passes (under 80,000 limit)
            run['items'][0]['status'] = 'working'
            run['items'][0].pop('ready_receipt', None)
            task['status'] = 'running'
            run['items'][0]['review_repair'] = {'source_patch': '', 'defects': [], 'candidate_id': inspected_packet['candidate_id']}
            def repair_packet(*args, **kwargs):
                pkt = orig_review_packet(*args, **kwargs)
                pkt['uncertainties'] = 'x' * (70000 - len(json.dumps(pkt)))
                return pkt

            branch_evidence.review_packet = repair_packet
            result = checkpoint(self.engine, Runtime(task), {})
            self.assertEqual(result['decision'], 'APPROVE')

            # 4. Repair packets also page instead of stopping at 80,000.
            run['items'][0]['status'] = 'working'
            run['items'][0].pop('ready_receipt', None)
            task['status'] = 'running'
            def over_repair_packet(*args, **kwargs):
                pkt = orig_review_packet(*args, **kwargs)
                pkt['uncertainties'] = 'x' * 85000
                return pkt

            branch_evidence.review_packet = over_repair_packet
            with patch('cheapos.branch_review_pages.prepare', side_effect=lambda e, rt, cur, pkt:
                       ({**pkt, 'uncertainties': 'Reviewed in retained pages'}, None, None)) as pages:
                self.assertEqual(checkpoint(self.engine, Runtime(task), {})['decision'], 'APPROVE')
                pages.assert_called_once()
                self.assertEqual(len(pages.call_args.args[3]['uncertainties']), 85000)
        finally:
            branch_evidence.review_packet = orig_review_packet

    def test_final_review_repair_packet_uses_item_patch_and_omits_duplicate_checks(self):
        task = self.task()
        run = task['branch_run']
        cmd_str = shlex.join(task['check_command'])
        item = run['items'][0]
        item['review_repair'] = {
            'manifest_id': 'manifest-abc',
            'candidate_id': 'prev-candidate',
            'source_patch': 'diff --git a/big.py b/big.py\n+big diff\n' * 500,
            'checks': [{'command': cmd_str, 'stdout': 'very verbose output ' * 500}],
            'defects': []
        }
        inspected_packet = {}
        def review(runtime, messages, tools, role):
            nonlocal inspected_packet
            inspected_packet = json.loads(messages[1]['content'])
            return call('review_decision', {
                'decision': 'APPROVE',
                'feedback': 'ok',
                'candidate_id': inspected_packet['candidate_id'],
                'criteria_outcomes': {'Both bounds work': {'passed': True, 'evidence': 'Passed'}}
            })
        self.engine.request = Mock(side_effect=review)
        result = checkpoint(self.engine, Runtime(task), {})
        self.assertEqual(result['decision'], 'APPROVE')

        # 1. repair_diff_since_claim must be current patch, not the 500-line source_patch diff
        self.assertNotIn('big diff', inspected_packet['repair_diff_since_claim'])
        self.assertEqual(inspected_packet['repair_diff_since_claim'], inspected_packet['diff'])

        # 2. repair_review must not duplicate checks
        self.assertNotIn('checks', inspected_packet['repair_review'])
        self.assertIn('checks', inspected_packet)
