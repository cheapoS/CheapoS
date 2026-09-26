import copy
import contextlib
import io
import os
import json
import tempfile
import unittest
from pathlib import Path

from cheapos import evaluation
from scripts import task_metrics


def task(identity='one', tokens=10):
    return {'id': identity, 'metrics_schema': 1, 'status': 'approved',
            'branch_run': {'plan': {'measurement': True}},
            'usage': {'cost': 0.03, **{r: {'tokens': tokens, 'cost': 0.01 if r in ('worker', 'reviewer') else 0.005}
                                     for r in ('worker', 'reviewer', 'planner', 'coordinator')}},
            'events': [], 'checks': [{'passed': False}, {'passed': True}],
            'checkpoints': [{'decision': 'REQUEST_CHANGES'}, {'decision': 'APPROVE'}],
            'request_metrics': [{'id': 'req', 'role': 'worker', 'purpose': 'probe', 'dispatched': True,
                                 'status': 'failed', 'usage_reconciled': False,
                                 'cost_provenance': 'uncertain_reservation',
                                 'reservation': {'tokens': 10, 'cost': 0.01}}],
            'run_metrics': [{key: 1 for key in ('elapsed_seconds', 'provider_request_seconds',
                             'provider_cooldown_seconds', 'operator_wait_seconds', 'controller_work_seconds')}]}


def entry(identity, variant):
    return {'id': identity, 'case': 'bounds', 'variant': variant, 'repeat': 1,
            'kind': 'recorded_model_trial', 'source': identity + '.json',
            'contract': {key: 'a' * 64 for key in evaluation.CONTRACT_FIELDS},
            'assessment': {'completed': True, 'evidence_sha256': 'b' * 64}}


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.left, self.right = task('one'), task('two', 12)
        self.manifest = {'schema_version': 1, 'trials': [entry('one', 'baseline'), entry('two', 'candidate')]}

    def report(self):
        for name, data in [('one', self.left), ('two', self.right)]:
            (self.root / (name + '.json')).write_text(json.dumps(data))
        return evaluation.report(self.manifest, self.root)

    def test_matching_trials_preserve_accounting_and_provenance(self):
        result = self.report()
        pair = result['pairs'][0]
        self.assertTrue(pair['comparable'])
        self.assertTrue(pair['matched_success'])
        self.assertEqual(pair['delta_right_minus_left']['worker_reviewer_tokens'], 4)
        self.assertEqual(result['trials'][0]['measurements']['worker_reviewer_tokens'], 20)
        self.assertEqual(result['trials'][0]['request_evidence']['worker']['unreconciled'], 1)
        self.assertEqual(result['trials'][0]['request_evidence']['worker']['probes'], 1)
        self.assertIsNone(result['trials'][0]['request_evidence']['worker']['reported_tokens'])
        self.assertEqual(result['trials'][0]['request_evidence']['worker']['cost_provenance'], ['uncertain_reservation'])

    def test_all_contract_mismatches_and_missing_values_block_comparison(self):
        for key in evaluation.CONTRACT_FIELDS:
            for value in (None, 'c' * 64):
                with self.subTest(key=key, value=value):
                    manifest = copy.deepcopy(self.manifest)
                    self.manifest['trials'][1]['contract'][key] = value
                    pair = self.report()['pairs'][0]
                    self.assertFalse(pair['comparable'])
                    self.assertTrue(all(v is None for v in pair['delta_right_minus_left'].values()))
                    self.manifest = manifest

    def test_unknown_or_failed_completion_never_claims_efficiency(self):
        for assessment in (None, {'completed': False, 'evidence_sha256': 'b' * 64}):
            self.manifest['trials'][1]['assessment'] = assessment
            result = self.report()
            self.assertTrue(result['pairs'][0]['comparable'])
            self.assertFalse(result['pairs'][0]['matched_success'])
            self.assertTrue(all(v is None for v in result['pairs'][0]['delta_right_minus_left'].values()))
        self.assertEqual(self.report()['completion_counts'][1]['incomplete'], 1)

    def test_unknowns_and_recorded_zero_are_distinct(self):
        self.left.pop('usage')
        self.left.pop('events')
        self.left.pop('run_metrics')
        self.left.pop('metrics_schema')
        self.right['usage']['worker']['cost'] = 0
        result = self.report()
        missing, known = result['trials']
        self.assertIsNone(missing['measurements']['worker_tokens'])
        self.assertIsNone(missing['measurements']['repeated_reads'])
        self.assertIsNone(missing['measurements']['elapsed_seconds'])
        self.assertIsNone(missing['measurements']['check_approval_requests'])
        self.assertEqual(known['measurements']['worker_cost'], 0)
        self.assertIsNone(result['pairs'][0]['delta_right_minus_left']['worker_tokens'])

    def test_partial_role_accounting_does_not_invent_total(self):
        self.left['usage'].pop('reviewer')
        result = self.report()['trials'][0]['measurements']
        self.assertIsNone(result['worker_reviewer_tokens'])
        self.assertIsNone(result['total_accounted_tokens'])

    def test_resumed_snapshot_is_not_a_new_trial(self):
        self.right['id'] = 'one'
        with self.assertRaisesRegex(ValueError, 'only once'):
            self.report()
        self.manifest['trials'][1]['repeat'] = 2
        with self.assertRaisesRegex(ValueError, 'only once'):
            self.report()

    def test_measurement_mode_mismatch_or_unknown_blocks_pair(self):
        for value in (False, None):
            self.right['branch_run']['plan']['measurement'] = value
            self.assertFalse(self.report()['pairs'][0]['comparable'])
        self.left['branch_run']['plan']['measurement'] = None
        self.assertFalse(self.report()['pairs'][0]['comparable'])

    def test_repeated_reads_ignore_volatile_metadata_but_respect_content_and_item(self):
        def read(identity, content='1: body', item='a', title='read file'):
            return {'id': identity, 'kind': 'tool', 'title': title, 'item_id': item,
                    'detail': {'arguments': {'path': 'private/source.py', 'url': 'https://private.invalid'},
                               'result': {'content': content, 'fetched_at': identity}}}
        events = [read('a'), read('a'), read('b'), read('c', content='1: changed'),
                  read('d', item='b'), read('e', title='read url'), read('f', title='read url'),
                  {'kind': 'steer'}, {'kind': 'user'}, {'kind': 'repair_attempt'}]
        before = copy.deepcopy(events)
        result = evaluation.observations({'events': events})
        self.assertEqual(result['read_calls'], 6)
        self.assertEqual(result['repeated_reads'], 2)
        self.assertEqual(result['guidance'], 1)
        self.assertEqual(result['followups'], 1)
        self.assertEqual(result['repair_attempts'], 1)
        self.assertEqual(events, before)

    def test_repairs_are_observations_not_exact_efficiency_deltas(self):
        result = self.report()
        self.assertEqual(result['trials'][0]['measurements']['review_revision_decisions'], 1)
        self.assertEqual(result['trials'][0]['measurements']['failed_check_runs'], 1)
        self.assertIsNone(result['pairs'][0]['delta_right_minus_left']['review_revision_decisions'])

    def test_scripted_export_uses_pinned_baseline_and_cannot_mix_with_models(self):
        summary = {'fixture_id': 'f01', 'baseline_sha256': 'd' * 64, 'verified_outcome': True,
                   'cost': {'accounted': 0, 'provenance': 'scripted_no_model_requests'}}
        self.left = {'schema_version': 1, 'mode': 'deterministic_scripted_providers', 'fixtures': [summary]}
        trial = self.manifest['trials'][0]
        trial.update(kind='scripted_controller', fixture_id='f01')
        result = self.report()
        self.assertTrue(result['trials'][0]['completion']['completed'])
        self.assertEqual(result['trials'][0]['contract']['source_sha256'], 'd' * 64)
        self.assertEqual(result['trials'][0]['completion']['provenance'], 'scripted_fixture_assertions')
        self.assertFalse(result['pairs'][0]['comparable'])
        self.assertIn('Different evidence kinds', result['pairs'][0]['reasons'])
        self.left['mode'] = 'live'
        with self.assertRaises(ValueError): self.report()

    def test_repeats_are_paired_without_cherry_picking_unpaired_trials(self):
        self.manifest['trials'][1]['repeat'] = 2
        result = self.report()
        self.assertEqual(result['pairs'], [])
        self.assertEqual(result['unpaired_trials'], ['one', 'two'])

    def test_invalid_manifest_identifiers_and_assessments(self):
        original = copy.deepcopy(self.manifest)
        for field, value in [('id', '| injected\n'), ('repeat', True), ('kind', 'inferred'),
                             ('assessment', {'completed': True})]:
            self.manifest = copy.deepcopy(original)
            self.manifest['trials'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.report()
        self.manifest = original
        self.manifest['trials'].append(copy.deepcopy(self.manifest['trials'][0]))
        with self.assertRaises(ValueError): self.report()

    def test_privacy_and_no_mutation(self):
        secret = 'DO-NOT-EXPORT-SECRET'
        self.left.update(prompt=secret, repository='/private/' + secret, providers={'worker': {'api_key': secret}})
        self.left['events'] = [{'kind': 'assistant', 'detail': secret}]
        self.left['request_metrics'][0]['model'] = secret
        self.left['request_metrics'][0]['cost_provenance'] = secret
        original = copy.deepcopy(self.manifest)
        result = self.report()
        self.assertNotIn(secret, json.dumps(result) + evaluation.markdown(result))
        self.assertEqual(self.manifest, original)
        self.assertEqual(json.loads((self.root / 'one.json').read_text()), self.left)
        self.assertEqual(result, self.report())

    def test_cli_writes_json_and_markdown_without_changing_sources(self):
        self.report()
        manifest = self.root / 'trials.json'
        manifest.write_text(json.dumps(self.manifest))
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        output, md = self.root / 'report.json', self.root / 'report.md'
        self.assertEqual(task_metrics.main(['--trials', str(manifest), '--output', str(output), '--markdown', str(md)]), 0)
        self.assertEqual(json.loads(output.read_text())['scope'], 'local_trial_comparison')
        self.assertIn('worker_reviewer_tokens', md.read_text())
        self.assertIn('unavailable', md.read_text())
        for name, content in before.items(): self.assertEqual((self.root / name).read_bytes(), content)

    def test_cli_rejects_input_overwrite_and_demo_sources(self):
        self.report()
        manifest = self.root / 'trials.json'
        manifest.write_text(json.dumps(self.manifest))
        for output in (manifest, self.root / 'one.json'):
            with self.subTest(output=output.name), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                task_metrics.main(['--trials', str(manifest), '--output', str(output)])
        self.left['demo'] = True
        with self.assertRaises(ValueError): self.report()

    def test_missing_check_history_and_truncated_timing_remain_unknown(self):
        self.left.pop('checks')
        self.left.pop('checkpoints')
        self.left['request_metrics_truncated'] = True
        result = self.report()['trials'][0]
        self.assertIsNone(result['measurements']['failed_check_runs'])
        self.assertIsNone(result['measurements']['review_revision_decisions'])
        self.assertIsNone(result['measurements']['elapsed_seconds'])
        self.assertEqual(result['coverage'], 'partial_historical')

    def test_request_provenance_deduplicates_request_identity(self):
        self.left['request_metrics'] *= 2
        result = self.report()['trials'][0]['request_evidence']['worker']
        self.assertEqual(result['dispatched'], 1)
        self.assertEqual(result['failed'], 1)

    def test_completed_and_unknown_trials_are_both_counted(self):
        self.manifest['trials'][1].pop('assessment')
        result = self.report()
        self.assertEqual(result['completion_counts'][0]['completed'], 1)
        self.assertEqual(result['completion_counts'][1]['unknown'], 1)
        self.assertEqual(result['trials'][1]['completion']['provenance'], 'unavailable')

    def test_repair_cycles_require_matching_scope_and_keep_unfinished_work(self):
        def check(passed, item='a', command=None):
            return {'kind': 'checks', 'item_id': item, 'detail': {'passed': passed,
                    'command': command or ['python', 'test.py'], 'directory': '.'}}
        def review(decision, item='a'):
            return {'kind': 'review', 'item_id': item, 'detail': {'decision': decision}}
        events = [check(False), check(False), check(True, item='b'),
                  check(True, command=['node', 'test.js']), check(True), check(False),
                  review('REQUEST_CHANGES'), review('REQUEST_CHANGES'), review('APPROVE', 'b'),
                  review('APPROVE'), review('REQUEST_CHANGES'), {'kind': 'user'}, review('APPROVE')]
        result = evaluation.observations({'events': events})
        self.assertEqual(result['check_repair_cycles'], 1)
        self.assertEqual(result['review_repair_cycles'], 1)
        self.assertEqual(result['open_check_repair_cycles'], 1)
        self.assertEqual(result['open_review_repair_cycles'], 1)

    def test_event_detail_ownership_binds_final_repair_item(self):
        events = [{'kind': 'repair_attempt', 'item_id': 'old', 'detail': {'item_id': 'repair'}},
                  {'kind': 'review', 'item_id': 'old', 'detail': {'decision': 'APPROVE'}},
                  {'kind': 'review', 'item_id': 'repair', 'detail': {'decision': 'APPROVE'}}]
        result = evaluation.observations({'events': events})
        self.assertEqual(result['review_repair_cycles'], 1)
        self.assertEqual(result['open_review_repair_cycles'], 0)

    def test_absent_request_records_are_not_zero_requests(self):
        self.left.pop('request_metrics')
        evidence = self.report()['trials'][0]['request_evidence']['worker']
        self.assertEqual(evidence['coverage'], 'unavailable')
        self.assertIsNone(evidence['dispatched'])
        self.assertIsNone(evidence['unreconciled'])

    def test_output_cannot_overwrite_a_hard_link_to_input(self):
        self.report()
        manifest = self.root / 'trials.json'
        manifest.write_text(json.dumps(self.manifest))
        output = self.root / 'hard-link.json'
        os.link(self.root / 'one.json', output)
        before = output.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            task_metrics.main(['--trials', str(manifest), '--output', str(output)])
        self.assertEqual(output.read_bytes(), before)

    def test_existing_store_export_remains_available(self):
        folder = self.root / 'tasks' / 'one'
        folder.mkdir(parents=True)
        (folder / 'task.json').write_text(json.dumps(self.left))
        output = self.root / 'store-report.json'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(task_metrics.main(['--store', str(self.root), '--output', str(output)]), 0)
        result = json.loads(output.read_text())
        self.assertEqual(result['summary']['tasks'], 1)
        self.assertEqual(result['tasks'][0]['outcome'], 'reviewer_approved')

    def test_existing_benchmark_route_uses_existing_runner(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        runner = Mock(return_value={'mode': 'deterministic_scripted_providers', 'fixtures': []})
        output = self.root / 'benchmark.json'
        with patch.dict('sys.modules', {'cheapos.benchmark': SimpleNamespace(run=runner)}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(task_metrics.main(['--benchmark', '--output', str(output)]), 0)
        runner.assert_called_once_with()
        self.assertEqual(json.loads(output.read_text())['mode'], 'deterministic_scripted_providers')

    def test_scripted_variants_compare_controller_evidence_only(self):
        self.left = {'schema_version': 1, 'mode': 'deterministic_scripted_providers', 'fixtures': [
            {'fixture_id': 'f01', 'baseline_sha256': 'd' * 64, 'verified_outcome': True,
             'roles': {'worker': {'tokens': 5}, 'reviewer': {'tokens': 7}},
             'cost': {'accounted': 0, 'provenance': 'scripted_no_model_requests'}}]}
        self.right = copy.deepcopy(self.left)
        self.right['fixtures'][0]['roles']['worker']['tokens'] = 3
        for trial in self.manifest['trials']: trial.update(kind='scripted_controller', fixture_id='f01')
        result = self.report()
        self.assertTrue(result['pairs'][0]['comparable'])
        self.assertTrue(result['pairs'][0]['matched_success'])
        self.assertEqual(result['pairs'][0]['delta_right_minus_left']['worker_reviewer_tokens'], -2)
        self.assertEqual(result['trials'][0]['completion']['provenance'], 'scripted_fixture_assertions')
        self.assertIn('not model quality', result['limitations'])
