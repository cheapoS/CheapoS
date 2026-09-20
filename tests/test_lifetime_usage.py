import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cheapos.lifetime_usage import LifetimeUsage, now


def record(id, role='worker', category='public_free', **extra):
    base = dict(id=id, dispatched=True, requested_at=now(), role=role, access_class=category,
                input_tokens=8, output_tokens=2, reasoning_tokens=2, cached_tokens=3,
                usage_reconciled=True, accounted_tokens=10, accounted_cost=0,
                requested_model='vendor/model', served_model='vendor/model')
    base.update(extra)
    return base


class LifetimeUsageTests(unittest.TestCase):
    def test_mixed_requests_and_export_deidentification(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = LifetimeUsage(directory)
            records = [record('free'), record('paid', 'reviewer', 'paid', reported_cost=.0004),
                       record('local', 'coordinator', 'local'), record('included', 'planner', 'included'),
                       record('charged', reported_cost=.0002), record('retry', status='failed'),
                       record('demo', synthetic=True)]
            pending = record('pending', category='unknown')
            pending.update(input_tokens=None, output_tokens=None, usage_reconciled=False, accounted_tokens=100,
                           reservation_tokens=100, reservation_cost=.001, accounted_cost=.001)
            records.append(pending)
            ledger.ingest(dict(id='private-id', prompt='secret prompt', workspace='/secret/path', request_metrics=records))
            summary = ledger.summary()
            self.assertEqual(summary['tokens']['reported'], 60)
            self.assertEqual(summary['tokens']['reserved'], 100)
            self.assertEqual(summary['tokens']['unknown_requests'], 1)
            self.assertEqual(summary['categories']['public_free']['tokens'], 20)
            self.assertEqual(summary['categories']['paid']['tokens'], 20)
            self.assertEqual(summary['charged_free_requests'], 1)
            self.assertAlmostEqual(summary['cost']['provider_reported'], .0006)
            self.assertAlmostEqual(summary['cost']['reserved'], .001)
            self.assertEqual(summary['roles']['planner']['tokens'], 10)
            raw = Path(directory, 'lifetime-usage.json').read_text()
            for forbidden in ['private-id', 'secret prompt', '/secret/path']:
                self.assertNotIn(forbidden, raw)
            ledger.ingest(dict(id='demo-task', demo=True, request_metrics=[record('x')]))
            self.assertEqual(ledger.summary(), summary)

    def test_reconciliation_restart_and_capped_history_residual(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = LifetimeUsage(directory)
            pending = record('r')
            pending.update(input_tokens=None, output_tokens=None, usage_reconciled=False, accounted_tokens=100,
                           reservation_tokens=100, reservation_cost=.01, accounted_cost=.01)
            task = dict(id='a', usage={'worker': {'tokens': 130, 'cost': .01}, 'cost': .01}, request_metrics=[pending])
            ledger.ingest(task)
            self.assertEqual(ledger.summary()['tokens']['accounted_historical'], 30)
            ledger = LifetimeUsage(directory)
            task['request_metrics'] = [record('r')]
            task['usage'] = {'worker': {'tokens': 40, 'cost': 0}, 'cost': 0}
            ledger.ingest(task)
            summary = ledger.summary()
            self.assertEqual(summary['tokens']['reported'], 10)
            self.assertEqual(summary['tokens']['reserved'], 0)
            self.assertEqual(summary['tokens']['accounted_historical'], 30)
            with patch('cheapos.lifetime_usage.os.replace', side_effect=AssertionError('duplicate write')):
                ledger.ingest(task)
            task['request_metrics'] = [record('r2')]
            task['request_metrics_truncated'] = True
            task['usage']['worker']['tokens'] = 50
            ledger.ingest(task)
            self.assertEqual(ledger.summary()['tokens']['reported'], 20)
            self.assertEqual(ledger.summary()['tokens']['accounted_historical'], 30)
            self.assertTrue(ledger.summary()['partial_earlier_history'])
            self.assertEqual(LifetimeUsage(directory).summary(), ledger.summary())
            self.assertEqual(ledger.summary(7)['tokens']['accounted_historical'], 0)

    def test_receipts_missing_subsets_and_synthetic_residual(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = LifetimeUsage(directory)
            worker = record('w')
            reviewer = record('r', role='reviewer')
            task = dict(id='review', request_metrics=[worker, reviewer], status='approved',
                        checkpoints=[{'decision': 'APPROVE'}], served_identity_version=1)
            ledger.ingest(task)
            self.assertEqual(ledger.summary()['completion']['independent_review_approved_jobs'], 0)
            reviewer['served_model'] = 'other/reviewer'
            reviewer['reasoning_tokens'] = None
            reviewer['cached_tokens'] = None
            ledger.ingest(task)
            self.assertEqual(ledger.summary()['completion']['independent_review_approved_jobs'], 1)
            self.assertEqual(ledger.summary()['tokens']['unknown_cached_requests'], 1)
            task['status'] = 'awaiting_reply'
            task['commits'] = ['private-commit']
            ledger.ingest(task)
            self.assertEqual(ledger.summary()['completion']['human_accepted_jobs'], 1)
            task['status'] = 'archived'
            ledger.ingest(task)
            self.assertEqual(ledger.summary()['completion']['human_accepted_jobs'], 1)
            ledger.ingest(dict(id='synthetic', request_metrics=[record('s', synthetic=True)],
                               usage={'worker': {'tokens': 10, 'cost': 0}, 'cost': 0}))
            self.assertEqual(ledger.summary()['tokens']['accounted_historical'], 0)
            # Restart needs no original task files; the deidentified ledger survives.
            self.assertEqual(LifetimeUsage(directory).summary(), ledger.summary())

    def test_unknown_category_identity_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = LifetimeUsage(directory)
            request = record('a', category='unknown', input_rate=0, output_rate=0)
            ledger.ingest(dict(id='a', request_metrics=[request]))
            self.assertEqual(ledger.summary()['categories']['unknown']['tokens'], 10)
            self.assertTrue(ledger.summary()['partial_earlier_history'])
            original = ledger.summary()
            with patch('cheapos.lifetime_usage.os.replace', side_effect=OSError('crash')):
                with self.assertRaises(OSError):
                    ledger.ingest(dict(id='b', request_metrics=[record('b')]))
            self.assertEqual(ledger.summary(), original)
            self.assertEqual(LifetimeUsage(directory).summary(), original)
            conflict = record('c')
            conflict['served_model'] = 'different/model'
            ledger.ingest(dict(id='c', request_metrics=[conflict]))
            self.assertEqual(ledger.summary()['categories']['unknown']['tokens'], 20)


    def test_model_health_purposes_and_pairs_telemetry(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = LifetimeUsage(directory)
            req_ok = record('r1', requested_model='vendor/flash', served_model='vendor/flash', purpose='work', status='responded')
            req_fail = record('r2', requested_model='vendor/flash', served_model='vendor/flash', purpose='recovery', status='failed', failure_category='rate_limit')
            req_rev = record('r3', role='reviewer', requested_model='vendor/auditor', served_model='vendor/auditor', purpose='review', status='responded')
            task = dict(
                id='pair-task',
                request_metrics=[req_ok, req_fail, req_rev],
                branch_run={'status': 'merged', 'merge_receipt': 'receipt-123'},
                checks=[{'passed': True}],
                checkpoints=[{'decision': 'APPROVE'}],
            )
            ledger.ingest(task)
            summ = ledger.summary()

            # Purpose telemetry
            self.assertEqual(summ['purposes']['work']['requests'], 1)
            self.assertEqual(summ['purposes']['recovery']['requests'], 1)
            self.assertEqual(summ['purposes']['review']['requests'], 1)

            # Model health telemetry
            flash_stats = summ['models']['vendor/flash']
            self.assertEqual(flash_stats['requests'], 2)
            self.assertEqual(flash_stats['successes'], 1)
            self.assertEqual(flash_stats['failures'], 1)
            self.assertEqual(flash_stats['success_rate'], 50.0)
            self.assertEqual(flash_stats['failure_breakdown']['rate_limit'], 1)

            # Model pair telemetry
            pair = summ['model_pairs']['vendor/flash + vendor/auditor']
            self.assertEqual(pair['worker'], 'vendor/flash')
            self.assertEqual(pair['reviewer'], 'vendor/auditor')
            self.assertEqual(pair['total_jobs'], 1)
            self.assertEqual(pair['merged_runs'], 1)
            self.assertEqual(pair['completion_rate'], 100.0)
            self.assertGreater(pair['total_tokens'], 0)
            self.assertEqual(pair['avg_tokens_per_job'], pair['total_tokens'])

            # Self-healing index
            self.assertIn('self_healing_index', summ)
            self.assertGreater(summ['self_healing_index']['initial_work_tokens'], 0)
            self.assertGreater(summ['self_healing_index']['recovery_tokens'], 0)
            self.assertGreater(summ['self_healing_index']['repair_overhead_pct'], 0.0)

            # Honest zero-cost metrics
            self.assertIsNone(summ['estimated_savings'])
            self.assertEqual(summ['zero_cost_share'], 100.0)

    def test_tasks_by_role_and_task_types(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = LifetimeUsage(directory)
            task = dict(
                id='multi-role-task',
                planner_model='vendor/planner',
                coordinator_model='vendor/coordinator',
                branch_run={'status': 'merged', 'merge_receipt': 'receipt-xyz'},
                checkpoints=[{'decision': 'APPROVE'}],
                request_metrics=[
                    record('r1', role='worker', purpose='work'),
                    record('r2', role='reviewer', purpose='review'),
                    record('r3', role='planner', purpose='planning'),
                    record('r4', role='coordinator', purpose='coordination'),
                ]
            )
            ledger.ingest(task)
            summ = ledger.summary()

            self.assertEqual(summ['tasks_by_role']['worker']['completed_tasks'], 1)
            self.assertEqual(summ['tasks_by_role']['reviewer']['completed_tasks'], 1)
            self.assertEqual(summ['tasks_by_role']['planner']['completed_tasks'], 1)
            self.assertEqual(summ['tasks_by_role']['coordinator']['completed_tasks'], 1)

            self.assertEqual(summ['task_types']['planning']['completed'], 1)
            self.assertEqual(summ['task_types']['implementation']['completed'], 1)
            self.assertEqual(summ['task_types']['reviewing']['completed'], 1)
            self.assertEqual(summ['task_types']['coordination']['completed'], 1)


if __name__ == '__main__':

    unittest.main()
