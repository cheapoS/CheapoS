"""Tiny state/provider cases: no repositories, subprocesses, sleeps or inference."""
import copy
from decimal import Decimal
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from cheapos import branch_disagreement as disagreement, branch_final, branch_review, branch_runs
from cheapos.engine import ProgressPause


def defect(kind='static'):
    return {'criterion': 'exact values', 'location': 'report.py:12', 'expected': 'Exact decimal values',
            'observed': 'A value is rounded by float conversion', 'kind': kind,
            'support': 'The code path converts amount to float before formatting.',
            'reproduction': 'Format 9007199254740993.01 and compare exact digits' if kind == 'executable' else ''}


class DisagreementTests(unittest.TestCase):
    def test_explicit_decision_and_bounded_final_corrections(self):
        for value in (None, '', False, True, 1, [], {}, 'unknown'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                disagreement.decision({'decision':value,'feedback':'Looks good'})
        self.assertEqual(disagreement.decision({'decision':' approve '}),'APPROVE')
        with self.assertRaises(ValueError):
            disagreement.decision({'decision':'APPROVE','defects':[defect()]})
        runtime=SimpleNamespace(task={'branch_run':{}},guard=lambda:None)
        response={'manifest_id':'m','chunk_ids':[],'criteria_ids':[],'feedback':'Looks good'}
        engine=SimpleNamespace(store=SimpleNamespace(save=Mock()),event=Mock(),
            request=Mock(return_value={'tool_calls':[{'id':'d','result':response}]}),
            parse_call=lambda c:('final_review_decision',c['result']))
        for _ in range(2):
            with self.assertRaises(ValueError):branch_final._review(engine,runtime,{'id':'m'}, {}, [], [])
        self.assertEqual(engine.request.call_count,3)

    def test_legacy_findings_normalize_and_cannot_bypass_saved_guard(self):
        finding=defect('executable');finding.pop('kind')
        repair=disagreement.repair({'defects':[finding]},'candidate',[])
        self.assertEqual(repair['defects'][0]['kind'],'executable')
        item={'id':'one','review_repair':{'defects':[finding]}}
        task={'branch_run':{'items':[item],'current_item_id':'one'},'checks':[]}
        with self.assertRaisesRegex(ValueError,'Demonstrate'):disagreement.before_write(task,'report.py')
        for change in ({'kind':[]},{'reproduction':False},{'kind':None},{'location':'../secret:1'},
                       {'code_location':{'path':'x'}},{'expected_behavior':'conflicting'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                disagreement.validate({'defects':[{**defect(),**change}]},['exact values'])
        ambiguous=defect();ambiguous.pop('kind')
        with self.assertRaises(ValueError):disagreement.validate({'defects':[ambiguous]},['exact values'])

    def test_contract_static_executable_and_historical_decisions(self):
        finding = {'defects': [defect()]}
        self.assertEqual(disagreement.validate(finding, ['exact values']), finding['defects'])
        executable = defect('executable')
        disagreement.validate({'defects': [executable]}, ['exact values'])
        for changed in ({}, {'defects': []}, {'defects': [dict(executable, reproduction='')]},
                        {'defects': [dict(executable, criterion='unknown')]},
                        {'defects': [dict(executable, observed='')]}):
            with self.assertRaises(ValueError): disagreement.validate(changed, ['exact values'])
        historical = {'decision': 'APPROVE', 'feedback': 'Saved before evidence contract'}
        self.assertNotIn('defects', historical)  # No migration fabricates historical proof.

    def test_unsupported_decimal_claim_pauses_across_restart_without_edit(self):
        run = branch_runs.new_run({'items': [{'id': 'one', 'title': 'Report', 'instructions': 'Keep exact values',
                    'acceptance_criteria': ['exact values'], 'required_checks': ['python tests.py']}], 'limits': {'working_seconds': 600}})
        run.update(status='running', expected_feature_tip='tip', current_item_id='one')
        run['items'][0]['status'] = 'working'
        task = {'branch_run': run, 'active_role': 'worker', 'checks': [], 'review_count': 0,
                'providers': {'worker': 'worker', 'reviewer': 'reviewer'}}
        engine = SimpleNamespace(store=SimpleNamespace(save=Mock()), event=Mock(), checks=Mock(),
                    file_tool=Mock(), parse_call=lambda c: ('review_decision', c['result']), request=Mock())
        engine.request.return_value = {'tool_calls': [{'id': 'bad', 'result': {
                    'decision': 'REQUEST_CHANGES', 'candidate_id': 'candidate',
                    'feedback': 'Decimal .2f needs conversion to float.'}}]}
        runtime = SimpleNamespace(task=task, guard=lambda: None, stop=SimpleNamespace(is_set=lambda: False))
        current = {'id': 'candidate', 'checks': [], 'patch': ''}
        with patch.object(branch_review.evidence, 'candidate', return_value=current), \
             patch.object(branch_review.evidence, 'current_checks', return_value=[]), \
             patch.object(branch_review.evidence, 'review_packet', return_value={}):
            with self.assertRaises(ProgressPause): branch_review.checkpoint(engine, runtime, {})
            self.assertEqual(engine.request.call_count, 3)
            task['branch_run'] = json.loads(json.dumps(task['branch_run']))
            with self.assertRaisesRegex(ProgressPause, 'Unsupported'): branch_review.checkpoint(engine, runtime, {})
        self.assertEqual(engine.request.call_count, 3)
        self.assertNotIn('review_repair', task['branch_run']['items'][0])
        engine.file_tool.assert_not_called()
        # Concrete counterprobe disproves the proposed float conversion.
        exact = Decimal('9007199254740993.01')
        self.assertEqual(format(exact, '.2f'), '9007199254740993.01')
        self.assertNotEqual(format(float(exact), '.2f'), '9007199254740993.01')
        self.assertEqual(format(Decimal('.10') + Decimal('.20'), '.2f'), '0.30')

    def test_final_unsupported_claim_is_bounded_and_supported_static_stays_actionable(self):
        task = {'branch_run': {}}
        runtime = SimpleNamespace(task=task, guard=lambda: None)
        response = {'decision': 'REQUEST_CHANGES', 'manifest_id': 'm', 'chunk_ids': ['diff:1'],
                    'criteria_ids': [], 'feedback': 'Missing edge handling'}
        engine = SimpleNamespace(store=SimpleNamespace(save=Mock()), event=Mock(),
                    request=Mock(side_effect=lambda *a, **k: {'tool_calls': [{'id': 'review', 'result': copy.deepcopy(response)}]}),
                    parse_call=lambda c: ('final_review_decision', c['result']))
        manifest = {'id': 'm', 'requirements': [{'id': 'exact values'}]}
        with self.assertRaises(ProgressPause): branch_final._review(engine, runtime, manifest, {}, ['diff:1'], [])
        self.assertEqual(engine.request.call_count, 3)
        with self.assertRaises(ProgressPause): branch_final._review(engine, runtime, manifest, {}, ['diff:1'], [])
        self.assertEqual(engine.request.call_count, 3)
        fresh = SimpleNamespace(task={'branch_run': {}}, guard=lambda: None)
        response['defects'] = [defect()]
        result = branch_final._review(engine, fresh, manifest, {}, ['diff:1'], [])
        self.assertEqual(result['decision'], 'REQUEST_CHANGES')
        self.assertEqual(result['defects'], [defect()])

    def test_identical_actionable_claim_cannot_repeat_repairs_forever(self):
        task = {'branch_run': {}, 'checks': []}
        item = {}
        result = disagreement.repair({'defects': [defect()]}, 'candidate', [])
        for _ in range(3): disagreement.attach(task, item, result)
        restored = json.loads(json.dumps(task))
        with self.assertRaisesRegex(ProgressPause, 'same review disagreement'):
            disagreement.attach(restored, item, result)

    def test_executable_gate_requires_current_failed_check_and_preserves_counterprobe(self):
        item = {'id': 'one'}
        task = {'branch_run': {'current_item_id': 'one', 'items': [item]}, 'checks': []}
        disagreement.attach(task, item, disagreement.repair({'defects': [defect('executable')]}, 'candidate', []))
        with patch('cheapos.verification.evidence_identity', return_value='current'):
            disagreement.before_write(task, 'tests/test_precision.py')
            for path in ('report.py', '../test_report.py'):
                with self.assertRaisesRegex(ValueError, 'Demonstrate'): disagreement.before_write(task, path)
            record = {'passed': True, 'outcome': 'passed', 'exit_code': 0, 'command': ['python', 'tests.py'], 'input_identity': 'current'}
            task['checks'].append(record)
            with self.assertRaises(ValueError): disagreement.before_write(task, 'report.py')
            record.update(passed=False, outcome='test_failure', exit_code=1, input_identity='stale')
            with self.assertRaises(ValueError): disagreement.before_write(task, 'report.py')
            record['input_identity'] = 'current'
            disagreement.before_write(task, 'report.py')
        self.assertEqual(item['review_repair']['probe_observed']['input_identity'], 'current')
        self.assertIn('Preserve original assertions', item['review_repair']['repair_instruction'])
        self.assertIn('not execution consent', item['review_repair']['repair_instruction'])


if __name__ == '__main__': unittest.main()
