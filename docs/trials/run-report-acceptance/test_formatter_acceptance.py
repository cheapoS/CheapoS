"""Run explicitly through scripts/dev_tests.py; absent exporter is expected baseline failure."""
import copy
import unittest
from contract import task, has, private_absent, commit_present, commit_absent, unavailable, escaped, SHA, check_counts, unknown_field, integration_unconfirmed, integration_confirmed, plain


class FormatterAcceptance(unittest.TestCase):
    def render(self, value):
        from cheapos.run_report import render_run_report
        return render_run_report(value)

    def test_real_schema_determinism_allowlist_and_example(self):
        value = task(); before = copy.deepcopy(value)
        report = self.render(value)
        has(report, 'Synthetic report', 'synthetic-run', 'feature/report', 'main', 'First item',
            'fixture/worker', 'fixture/reviewer', 'APPROVE', '31', '17', '12.5', 'estimate')
        commit_present(report); private_absent(report)
        check_counts(report, 2, 1)
        self.assertEqual(report, self.render(value)); self.assertEqual(value, before)
        from example import make_example
        self.assertEqual(make_example(), report)

    def test_stale_mismatched_and_unfinished_commit_receipts(self):
        for change in ({'stage': 'source_committed'}, {'run_id': 'other'}, {'item_id': 'other'}, {'new_tip': 'invalid'}):
            value = task(); value['branch_run']['items'][0]['commit_receipt'].update(change)
            with self.subTest(change=change): commit_absent(self.render(value))
        value = task(); value['branch_run']['items'][0]['commit_receipt'] = None
        commit_absent(self.render(value))
        value = task(); value['branch_run']['items'][0]['status'] = 'working'
        commit_absent(self.render(value))

    def test_no_change_creates_no_commit(self):
        value = task(); item = value['branch_run']['items'][0]
        item['status'] = 'satisfied_without_change'; item['commit_receipt']['outcome'] = 'satisfied_without_change'
        report = self.render(value); commit_absent(report)
        self.assertRegex(plain(report), r'no.change|without.change|already.satisfied')
        item['commit_receipt']['run_id'] = 'other'
        invalid = self.render(value)
        self.assertRegex(invalid.lower(), r'unconfirmed|unavailable|incomplete|pending|not.confirmed|unverified')

    def test_outcomes_and_merge_receipt_identity(self):
        value = task(); run = value['branch_run']
        for state in ('paused', 'left_on_branch', 'running'):
            run['status'] = state; report = self.render(value)
            self.assertRegex(report.lower(), {'paused':'paused', 'left_on_branch':r'left.*branch', 'running':r'running|progress|incomplete'}[state])
        run['status'] = 'merged'
        # A status alone cannot claim confirmed integration.
        missing = self.render(value)
        integration_unconfirmed(missing)
        run['merge_receipt'] = {'stage': 'completed', 'mapping': copy.deepcopy(run['workspace_mapping']),
                                'feature_tip': SHA, 'target_ref': run['target_ref']}
        confirmed = self.render(value); self.assertNotEqual(missing, confirmed)
        integration_confirmed(confirmed)
        for field, wrong in (('mapping', {'run_id':'other'}), ('feature_tip', 'c3'*20), ('target_ref', 'refs/heads/other'), ('stage', 'intent')):
            original = copy.deepcopy(run['merge_receipt'])
            run['merge_receipt'][field] = wrong
            integration_unconfirmed(self.render(value))
            run['merge_receipt'] = original
        run['workspace_mapping']['run_id'] = 'other'
        run['merge_receipt']['mapping']['run_id'] = 'other'
        integration_unconfirmed(self.render(value))

    def test_missing_partial_zero_and_uncertain_accounting(self):
        value = task()
        for key in ('usage', 'checks', 'checkpoints'): value.pop(key)
        value['branch_run']['consumption'] = {}
        missing = self.render(value)
        for label in (r'worker.*tokens|tokens.*worker', r'reviewer.*tokens|tokens.*reviewer', r'checks?', r'\breview(?:s| decisions)?\b', r'cost', r'working.*time|working.*seconds'):
            unknown_field(missing, label)
        value['usage'] = {'worker': {'tokens': 0}, 'cost': 0, 'uncertain_requests': 1}
        report = self.render(value); unavailable(report); has(report, '0', 'uncertain')
        unknown_field(report, r'reviewer.*tokens|tokens.*reviewer')
        self.assertRegex(report.lower(), r'worker[^\n]*0')

    def test_markdown_unicode_order_and_typed_pause(self):
        value = task(); run = value['branch_run']; value['title'] = '東京 |raw| [click](https://example.invalid) **bold** `code`\n# injected'
        run['status'] = 'paused'; run['pause_reason'] = 'recovery_exhausted'
        second = copy.deepcopy(run['items'][0]); second.update(id='second', title='Second item', status='pending', commit_receipt=None)
        run['items'].append(second)
        report = self.render(value); escaped(report)
        self.assertLess(report.index('First item'), report.index('Second item'))
        self.assertRegex(plain(report), r'recovery[ _-]exhausted')

    def test_invalid_inputs(self):
        for value in (None, {}, {'id':'interactive'}, {'branch_run': {'schema_version': 999}}):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                self.render(value)
