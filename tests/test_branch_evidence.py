import copy
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from cheapos import branch_evidence as evidence
from cheapos.verification import evidence_identity
from cheapos.workspace import Workspace, git


class BranchEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        git(self.root, 'init', '-q')
        git(self.root, 'config', 'user.email', 'fixture@example.invalid')
        git(self.root, 'config', 'user.name', 'Fixture')
        (self.root / 'code.py').write_text('value = 1\n')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'Base')
        self.task = {'workspace': str(self.root), 'workspace_generation': 0, 'check_command': ['untouched']}
        self.context = dict(run_id='run', plan_revision=1, item_id='one', item_revision=1, feature_parent='source-sha', acceptance_criteria=['value is correct'])
        self.specs = [[sys.executable, '-c', 'assert 1 == 1'], [sys.executable, '-c', 'assert 2 == 2']]

    def collect(self):
        current = evidence.candidate(self.task, self.context, self.specs)
        records = []
        for command in evidence.commands(self.specs):
            before = evidence_identity({**self.task, 'check_command': command})
            record = Workspace(self.root).run_checks(command, threading.Event())
            record.update(input_identity=before, verification_identity=evidence_identity({**self.task, 'check_command': command}))
            records.append(record)
        return current, records

    def receipt(self, current, records, **overrides):
        values = dict(current=current, checks=evidence.current_checks(current, records), review={'candidate_id': current['id'], 'decision': 'APPROVE', 'feedback': 'Inspected criteria'}, worker_model='worker', reviewer_model='reviewer', criteria_outcomes={'value is correct': {'passed': True, 'evidence': 'Read code.py and checked value'}})
        values.update(overrides)
        return evidence.ready_receipt(**values)

    def test_actual_checks_receipt_and_immutable_history(self):
        (self.root / 'code.py').write_text('value = 2\n')
        current, records = self.collect()
        receipt = self.receipt(current, records)
        records[0]['passed'] = False
        self.assertEqual(evidence.revalidate(receipt, self.task, self.context, self.specs)['outcome'], 'ready')
        self.assertEqual(self.task['check_command'], ['untouched'])
        git(self.root, 'commit', '-am', 'Advance')
        with self.assertRaises(ValueError): evidence.revalidate(receipt, self.task, self.context, self.specs)
        self.assertEqual(json.loads(receipt)['candidate']['id'], current['id'])

    def test_rejects_bad_checks_and_accepts_repair(self):
        current, records = self.collect()
        failed = {**records[0], 'passed': False, 'exit_code': 1}
        self.receipt(current, [failed] + records)
        for change in ({'passed': False}, {'exit_code': 1}, {'truncated': True}, {'reason': 'timed out'}, {'input_identity': 'stale'}, {'verification_identity': 'stale'}, {'outcome': 'inputs_changed'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.receipt(current, [{**records[0], **change}, records[1]])
        with self.assertRaises(ValueError): self.receipt(current, records + [failed])

    def test_requires_independent_bound_review_and_every_criterion(self):
        current, records = self.collect()
        for decision in ('TAKE_OVER', 'REQUEST_CHANGES', 'COMPLETE', 'completed'):
            with self.subTest(decision=decision), self.assertRaises(ValueError):
                self.receipt(current, records, review={'candidate_id': current['id'], 'decision': decision, 'feedback': 'done'})
        for overrides in ({'reviewer_model': 'worker'}, {'worker_model': 'openrouter/vendor/model:free', 'reviewer_model': 'vendor/model'}, {'criteria_outcomes': {}}, {'review': {'candidate_id': 'old', 'decision': 'APPROVE', 'feedback': 'yes'}}):
            with self.assertRaises(ValueError): self.receipt(current, records, **overrides)
        self.assertEqual(json.loads(self.receipt(current, records))['outcome'], 'satisfied_without_change')

    def test_current_files_plan_parent_generation_specs_environment(self):
        current, records = self.collect()
        receipt = self.receipt(current, records)
        for key in ('plan_revision', 'item_revision', 'feature_parent', 'run_id'):
            with self.subTest(key=key), self.assertRaises(ValueError): evidence.revalidate(receipt, self.task, {**self.context, key: 'changed'}, self.specs)
        with self.assertRaises(ValueError): evidence.revalidate(receipt, {**self.task, 'workspace_generation': 2}, self.context, self.specs)
        with self.assertRaises(ValueError): evidence.revalidate(receipt, self.task, self.context, self.specs[:1])
        (self.root / 'code.py').write_text('value = 3\n')
        with self.assertRaises(ValueError): evidence.revalidate(receipt, self.task, self.context, self.specs)
        (self.root / 'code.py').write_text('value = 1\n')
        with patch('cheapos.verification.runner_identity', return_value={'executable': 'changed'}):
            with self.assertRaises(ValueError): evidence.revalidate(receipt, self.task, self.context, self.specs)
        with patch('cheapos.verification.runner_identity', return_value=None):
            with self.assertRaises(ValueError): evidence.candidate(self.task, self.context, self.specs)

    def test_tests_that_edit_files_cannot_pass(self):
        self.specs = [[sys.executable, '-c', "open('code.py','w').write('value = 9\\n')"]]
        current, records = self.collect()
        with self.assertRaises(ValueError): self.receipt(current, records)

    def test_normalization_and_packet_preserve_contract(self):
        self.assertEqual(evidence.commands(['python -m unittest', {'command': 'git diff --check'}]), [['python', '-m', 'unittest'], ['git', 'diff', '--check']])
        current, records = self.collect()
        packet = evidence.review_packet(current, {'acceptance_criteria': current['criteria'], 'instructions': 'Do work'}, {'items': ['one']}, evidence.current_checks(current, records), 'No additional assumptions')
        self.assertEqual(packet['candidate_id'], current['id'])
        packet['context']['plan_revision'] = 20
        self.assertEqual(current['context']['plan_revision'], 1)
        modified = json.loads(self.receipt(current, records))
        modified['outcome'] = 'ready'
        with self.assertRaises(ValueError): evidence.revalidate(json.dumps(modified), self.task, self.context, self.specs)


if __name__ == '__main__': unittest.main()
