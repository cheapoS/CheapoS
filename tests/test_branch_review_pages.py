"""Large-item continuation with in-memory evidence, no Git or live models."""
import copy
import hashlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_evidence as evidence, branch_review, branch_review_pages as pages
from cheapos import branch_runs, branch_review_recovery, context_evidence, routing
from cheapos import branch_integration_review
from cheapos.engine import Engine, ProgressPause
from cheapos.providers import BudgetError
from tests.test_branch_disagreement import defect


class ItemPageTests(unittest.TestCase):
    def fixture(self):
        command = ['python', 'tests.py']
        run = branch_runs.new_run({'items': [{'id': 'one', 'title': 'Combine changes',
            'instructions': 'Preserve exact values while combining both branches.',
            'acceptance_criteria': ['exact values'], 'required_checks': ['python tests.py']}],
            'uncapped_work': True, 'limits': {'working_seconds': 600}})
        run.update(status='running', expected_feature_tip='tip', current_item_id='one')
        run['items'][0]['status'] = 'working'
        record = {'command': command, 'passed': True, 'exit_code': 0,
                  'verification_identity': 'inputs', 'input_identity': 'inputs'}
        current = {'context': branch_review.context(run, run['items'][0]), 'workspace': '/fixture',
            'check_specifications': ['python tests.py'], 'criteria': ['exact values'],
            'patch': 'diff --git a/report.py b/report.py\n' + '+preserve both branches\n' * 6000,
            'checks': [{'command': command, 'verification_identity': 'inputs'}]}
        current['id'] = evidence._digest(current)
        task = {'id': 'task', 'workspace': '/fixture', 'branch_run': run, 'active_role': 'worker',
            'checks': [record], 'review_count': 0, 'checkpoints': [], 'events': [],
            'providers': {'worker': {'model': 'worker'}, 'reviewer': {'model': 'reviewer'}},
            'execution': {'mode': 'remote'}, 'route': {'base_url': 'gateway'},
            'usage': {'cost': 0}, 'limits': {'dollars': 0, 'uncapped_work': True}}
        runtime = SimpleNamespace(task=task, guard=Mock(), stop=SimpleNamespace(is_set=lambda: False))
        engine = SimpleNamespace(store=SimpleNamespace(save=Mock()), event=Mock(), checks=Mock(),
            file_tool=Mock(), parse_call=lambda c: (c['name'], c['result']), request=Mock())
        engine.request.side_effect = self.respond
        source = patch.object(evidence, 'candidate', return_value=current)
        source.start(); self.addCleanup(source.stop)
        return task, engine, runtime, current

    def call(self, name, result):
        return {'role': 'assistant', 'tool_calls': [{'id': 'answer', 'name': name, 'result': result}]}

    def respond(self, runtime, messages, tools, role, **kwargs):
        packet = json.loads(messages[1]['content'])
        self.assertLess(len(messages[1]['content']), 60000)
        if 'chunk' in packet:
            return self.call('final_review_decision', {'decision': 'APPROVE', 'feedback': 'Inspected this part.',
                'manifest_id': packet['manifest_id'], 'chunk_ids': packet['chunk_ids'], 'criteria_ids': []})
        self.assertIn('packet_coverage', packet)
        self.assertNotIn('If packet diff is empty', messages[0]['content'])
        return self.call('review_decision', {'decision': 'APPROVE', 'feedback': 'Both branches preserved.',
            'candidate_id': packet['candidate_id'],
            'criteria_outcomes': {'exact values': {'passed': True, 'evidence': 'Combined source and checks.'}}})

    def test_large_patch_reaches_real_receipt_without_losing_evidence_or_rechecking(self):
        task, engine, runtime, current = self.fixture()
        before = copy.deepcopy({k: task[k] for k in ('checks', 'limits', 'usage')})
        self.assertEqual(branch_review.checkpoint(engine, runtime, {})['decision'], 'APPROVE')
        receipt = json.loads(task['branch_run']['items'][0]['ready_receipt'])
        self.assertEqual(receipt['candidate'], current)
        coverage = receipt['review']['packet_coverage']
        source = task['context_evidence'][coverage['packet_reference']]['text']
        parts = [json.loads(c.args[1][1]['content'])['chunk']['content']
                 for c in engine.request.call_args_list if 'chunk' in json.loads(c.args[1][1]['content'])]
        self.assertEqual(''.join(parts), source)
        self.assertEqual(json.loads(source)['diff'], current['patch'])
        self.assertEqual(len(coverage['chunks']), len(parts))
        requests = [c.args[3] for c in engine.event.call_args_list if c.args[1] == 'review_request'
                    and c.args[3].get('stage') == 'chunk']
        completed = [c.args[3] for c in engine.event.call_args_list if c.args[1] == 'review'
                     and c.args[3].get('chunk_ids')]
        for records in (requests, completed):
            self.assertEqual([(r['chunk_index'], r['chunk_total']) for r in records],
                             [(i, len(parts)) for i in range(1, len(parts) + 1)])
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), coverage['packet_reference'])
        for key, value in before.items(): self.assertEqual(task[key], value)
        engine.checks.assert_not_called()
        self.assertGreater(runtime.guard.call_count, len(parts))
        self.assertNotIn('active_final_review', task['branch_run'])
        for mutation in ('missing', 'stale', 'same_model', 'wrong_coverage'):
            bad = copy.deepcopy(receipt['review'])
            if mutation == 'missing': bad['packet_coverage']['chunks'].pop()
            elif mutation == 'stale': bad['packet_coverage']['candidate_id'] = 'other'
            elif mutation == 'same_model': bad['packet_coverage']['chunks'][0]['review']['reviewer_model'] = 'worker'
            else: bad['packet_coverage']['chunks'][0]['review']['chunk_ids'] = ['other']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                evidence.ready_receipt(current, receipt['checks'], bad, 'worker', 'reviewer', receipt['criteria_outcomes'])

    def test_resume_reuses_completed_pages_and_keeps_original_check_evidence(self):
        task, engine, runtime, current = self.fixture()
        def interrupted(*args, **kwargs):
            if engine.request.call_count == 2: raise InterruptedError('Stop requested')
            return self.respond(*args, **kwargs)
        engine.request.side_effect = interrupted
        with self.assertRaises(InterruptedError):
            branch_review.checkpoint(engine, runtime, {'summary': 'Combined target', 'uncertainties': 'Check rounding'})
        self.assertNotIn('ready_receipt', task['branch_run']['items'][0])
        runtime.task = json.loads(json.dumps(task))
        engine.request.reset_mock(side_effect=True); engine.request.side_effect = self.respond
        saved = runtime.task['pending_review']
        self.assertEqual(saved['worker_summary'], 'Combined target')
        self.assertEqual(saved['uncertainties'], 'Check rounding')
        self.assertEqual(branch_review.checkpoint(engine, runtime, {
            'summary': saved['worker_summary'], 'uncertainties': saved['uncertainties']})['decision'], 'APPROVE')
        first = json.loads(engine.request.call_args_list[0].args[1][1]['content'])
        self.assertEqual(first['chunk_ids'], ['item:2'])
        engine.checks.assert_not_called()

    def test_integration_comparison_keeps_full_receipt_and_resumes_paged_review(self):
        for paged in (False, True):
            with self.subTest(paged=paged):
                task, engine, runtime, current = self.fixture()
                run = task['branch_run']
                merge = {'old_tip': 'tip', 'target_tip': 'frozen-target', 'tree': 'suggested',
                         'conflicts': ['report.py']}
                key = evidence._digest(merge)
                run['plan']['items'][0]['instructions'] += ' Captured context: ' + key
                run['conflict_resolution'] = {'item_id': 'one', 'status': 'working',
                                              'context': merge, 'context_digest': key}
                run['workspace_mapping'] = {'source': '/source', 'workspace': '/fixture',
                                            'workspace_head': 'private-head'}
                current['private_baseline'] = 'private-head'
                current.pop('id'); current['id'] = evidence._digest(current)
                target_diff = '+task change\n' * (6000 if paged else 1)
                def respond(rt, messages, tools, role, **kwargs):
                    packet = json.loads(messages[1]['content'])
                    basis = packet.get('integration_comparison', packet.get('integration_review'))
                    self.assertEqual(basis['target_tip'], 'frozen-target')
                    self.assertIn('empty target diff is not proof', basis['instruction'])
                    if 'chunk' in packet:
                        return self.respond(rt, messages, tools, role, **kwargs)
                    if not paged:
                        self.assertEqual(packet['diff'], target_diff)
                        self.assertEqual(basis['resolution_diff'], '-dropped task change\n')
                    return self.call('review_decision', {'decision': 'APPROVE', 'feedback': 'Verified integration.',
                        'candidate_id': packet['candidate_id'], 'integration_review': {'target_tip': 'invented'},
                        'criteria_outcomes': {'exact values': {'passed': True, 'evidence': 'Checked combined source.'}}})
                engine.request.side_effect = respond
                with patch.object(branch_integration_review.branch_workspace, 'validate_owned'), \
                     patch.object(branch_integration_review, 'comparisons',
                                  return_value=('candidate-tree', target_diff, '-dropped task change\n')):
                    if paged:
                        def interrupt(*args, **kwargs):
                            if engine.request.call_count == 2: raise InterruptedError('Stop requested')
                            return respond(*args, **kwargs)
                        engine.request.side_effect = interrupt
                        with self.assertRaises(InterruptedError): branch_review.checkpoint(engine, runtime, {})
                        runtime.task = json.loads(json.dumps(task))
                        engine.request.reset_mock(side_effect=True); engine.request.side_effect = respond
                    self.assertEqual(branch_review.checkpoint(engine, runtime, {})['decision'], 'APPROVE')
                if paged:
                    first = json.loads(engine.request.call_args_list[0].args[1][1]['content'])
                    self.assertEqual(first['chunk_ids'], ['item:2'])
                receipt = json.loads(runtime.task['branch_run']['items'][0]['ready_receipt'])
                self.assertEqual(receipt['candidate'], current)
                self.assertEqual(receipt['review']['integration_review']['target_tip'], 'frozen-target')
                engine.checks.assert_not_called()
                for field in ('candidate_id', 'task_tip', 'full_patch_digest', 'invalid_shape'):
                    bad = copy.deepcopy(receipt['review'])
                    if field == 'invalid_shape': bad['integration_review'] = 'invalid'
                    else: bad['integration_review'][field] = 'stale'
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        evidence.ready_receipt(current, receipt['checks'], bad, 'worker', 'reviewer',
                                               receipt['criteria_outcomes'])

    def test_chunk_failure_switches_reviewer_automatically_with_saved_history(self):
        task, engine, runtime, current = self.fixture()
        def respond(*args, **kwargs):
            result = self.respond(*args, **kwargs)
            if task['providers']['reviewer']['model'] == 'reviewer':
                result['tool_calls'][0]['result']['chunk_ids'] = ['wrong']
            return result
        def select(e, rt, role, replace):
            self.assertIn('reviewer', branch_review_recovery.failed_models(rt.task))
            rt.task['providers']['reviewer']['model'] = 'replacement'
        engine.request.side_effect = respond
        with patch.object(routing, 'select_remote', side_effect=select) as handoff:
            self.assertEqual(branch_review.checkpoint(engine, runtime, {})['decision'], 'APPROVE')
        handoff.assert_called_once()
        self.assertTrue(task['branch_run']['final_review_recovery'])
        engine.checks.assert_not_called()

    def test_concrete_chunk_defect_returns_to_worker_instead_of_approving(self):
        task, engine, runtime, current = self.fixture()
        finding = defect()
        def respond(*args, **kwargs):
            result = self.respond(*args, **kwargs)
            result['tool_calls'][0]['result'].update(decision='REQUEST_CHANGES', defects=[finding])
            return result
        engine.request.side_effect = respond
        result = branch_review.checkpoint(engine, runtime, {})
        self.assertEqual(result['decision'], 'REQUEST_CHANGES')
        self.assertEqual(result['source_patch'], current['patch'])
        self.assertEqual(task['branch_run']['items'][0]['status'], 'working')
        self.assertNotIn('ready_receipt', task['branch_run']['items'][0])
        engine.request.assert_called_once()

    def test_passing_pages_do_not_replace_required_criterion_review(self):
        task, engine, runtime, current = self.fixture()
        task['operator_reviewer_model'] = 'reviewer'
        def respond(*args, **kwargs):
            result = self.respond(*args, **kwargs)
            if result['tool_calls'][0]['name'] == 'review_decision':
                result['tool_calls'][0]['result']['criteria_outcomes'] = {}
            return result
        engine.request.side_effect = respond
        with self.assertRaises(ProgressPause): branch_review.checkpoint(engine, runtime, {})
        self.assertNotIn('ready_receipt', task['branch_run']['items'][0])

    def test_spending_guard_and_changed_candidate_still_prevent_approval(self):
        task, engine, runtime, current = self.fixture()
        runtime.guard.side_effect = BudgetError('Authorized cost cap')
        with self.assertRaisesRegex(BudgetError, 'Authorized cost cap'):
            branch_review.checkpoint(engine, runtime, {})
        engine.request.assert_not_called()
        runtime.guard.side_effect = None
        def change(*args, **kwargs):
            response = self.respond(*args, **kwargs)
            evidence.candidate.return_value = {**current, 'id': 'changed'}
            return response
        engine.request.side_effect = change
        with self.assertRaisesRegex(ValueError, 'changed|branch|Branch'):
            branch_review.checkpoint(engine, runtime, {})
        self.assertNotIn('ready_receipt', task['branch_run']['items'][0])

    def test_context_reads_use_current_candidate_and_retained_full_evidence(self):
        task, engine, runtime, current = self.fixture()
        packet = {'diff': current['patch'], 'acceptance_criteria': current['criteria']}
        with patch.object(pages.Workspace, 'path', return_value=SimpleNamespace(exists=lambda: True)), \
             patch.object(pages.Workspace, 'read_file', return_value={'content': '1: current merged file'}) as read:
            result = pages.read_candidate(task, current, {'id': 'manifest'}, {
                'manifest_id': 'manifest', 'path': 'report.py', 'start_line': 1})
        self.assertEqual(result['candidate_id'], current['id'])
        self.assertIn('current merged file', result['content']); read.assert_called_once()
        compact, coverage, finding = pages.prepare(engine, runtime, current, packet)
        original = context_evidence.read(task, compact['diff_evidence']['reference'])
        self.assertEqual(original['offset'], 0); self.assertTrue(original['has_more'])
        self.assertIsNone(finding)
        with self.assertRaisesRegex(ValueError, 'identity'):
            pages.read_candidate(task, current, {'id': 'manifest'}, {'manifest_id': 'stale', 'path': 'report.py'})

    def test_refresh_keeps_large_branch_patch_without_changing_interactive_guard(self):
        task, engine, runtime, current = self.fixture()
        with patch('cheapos.engine.Workspace') as workspace:
            workspace.return_value.patch.return_value = current['patch']
            workspace.return_value.changes.return_value = [{'path': 'report.py'}]
            Engine.refresh_changes(engine, task)
            self.assertEqual(task['patch'], current['patch'])
            task.pop('branch_run')
            with self.assertRaises(BudgetError): Engine.refresh_changes(engine, task)
