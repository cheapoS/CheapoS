import json
import unittest
from cheapos import metrics
from cheapos.providers import reserve,reconcile


class MetricsTests(unittest.TestCase):
    def task(self):
        return {'id':'private-task-id','prompt':'PRIVATE PROMPT','source':'/private/source','status':'approved','metrics_schema':1,
                'limits':{'output_tokens':128,'reviewer_tokens':10000,'dollars':1},
                'usage':{'worker':{'tokens':0,'cost':0},'reviewer':{'tokens':0,'cost':0},'cost':0,'uncertain_requests':0,'estimated_requests':0},
                'events':[],'checks':[],'checkpoints':[{'decision':'APPROVE'}]}

    def test_reported_usage_reconciles_once_and_subsets_are_not_added(self):
        task=self.task();config={'input_rate':1,'output_rate':1}
        reservation=reserve(task,config,[],[],'worker')
        usage={'prompt_tokens':20,'completion_tokens':10,'cost':0.05,'prompt_tokens_details':{'cached_tokens':4},'completion_tokens_details':{'reasoning_tokens':3}}
        known=reconcile(task,config,reservation,usage)
        record={'dispatched':True,'role':'worker'};metrics.record_usage(record,usage,known);task['request_metrics']=[record]
        metrics.record_accounted(record,config,reservation,usage,known)
        self.assertEqual(record['accounted_tokens'],30)
        self.assertEqual(record['accounted_cost'],.05)
        self.assertTrue(record['usage_reconciled'])
        result=metrics.aggregate(task)
        self.assertAlmostEqual(result['cost']['accounted'],.05)
        self.assertEqual(result['cost']['provenance'],'provider_reported')
        self.assertEqual(result['tokens'],{'input_tokens':20,'output_tokens':10,'reasoning_tokens':3,'cached_tokens':4,'accounted_total':30})
        self.assertEqual(result['outcome'],'reviewer_approved');self.assertEqual(result['human_accepted_commits'],0)

    def test_missing_historical_fields_unknown_and_cancel_not_model_failure(self):
        task=self.task();task.pop('metrics_schema');task.pop('usage')
        result=metrics.aggregate(task)
        self.assertIsNone(result['tokens']['input_tokens']);self.assertIsNone(result['cost']['accounted']);self.assertIsNone(result['calls']['worker'])
        self.assertIsNone(result['time']['elapsed_seconds'])
        task.update(metrics_cancelled=True,status='paused',error_code='output_limit')
        self.assertEqual(metrics.aggregate(task)['outcome'],'cancelled');self.assertFalse(metrics.aggregate(task)['model_failure'])

    def test_uncertain_reservations_and_export_privacy(self):
        task=self.task();reserve(task,{'input_rate':1,'output_rate':1},[],[],'worker')
        task['request_metrics']=[{'dispatched':True,'role':'worker','status':'failed'}]
        result=metrics.aggregate(task)
        self.assertEqual(result['cost']['provenance'],'includes_uncertain_reservations');self.assertIsNone(result['tokens']['input_tokens'])
        exported=json.dumps(metrics.export([task]));self.assertNotIn('PRIVATE PROMPT',exported);self.assertNotIn('/private/source',exported);self.assertNotIn('private-task-id',exported)

    def test_later_failed_request_does_not_inherit_human_acceptance(self):
        task=self.task();task.update(commits=[{'commit':'old'}],status='error')
        self.assertEqual(metrics.aggregate(task)['outcome'],'error')

class TokenAccountingTests(unittest.TestCase):
    def test_reservation_breakdown_reconciles_and_survives_serialization(self):
        task = MetricsTests().task()
        config = {'input_rate': 0, 'output_rate': 0}
        failed = reserve(task, config, [{'role': 'user', 'content': 'café'}], [], 'worker')
        request = {'role': 'worker', 'model': 'fixture/model', 'purpose': 'probe',
                   'status': 'failed', 'error_code': 'http_403', 'reservation': failed}
        task['request_metrics'] = [request]
        good = reserve(task, config, [], [], 'worker')
        usage = {'prompt_tokens': 20, 'completion_tokens': 10}
        known = reconcile(task, config, good, usage)
        record = {'role': 'worker', 'reservation': good}
        metrics.record_usage(record, usage, known)
        metrics.record_accounted(record, config, good, usage, known)
        task['request_metrics'].append(record)
        result = metrics.token_accounting(json.loads(json.dumps(task)))
        self.assertEqual(result['reported'], 30)
        self.assertEqual(result['reserved'], failed['tokens'])
        self.assertEqual(result['accounted'], 30 + failed['tokens'])
        self.assertEqual(result['coverage'], 'complete')
        row = result['requests'][0]
        self.assertEqual(row['prompt_tokens'], row['prompt_bytes'] + 1024)
        self.assertEqual(row['tokens'], row['prompt_tokens'] + row['output_tokens'])
        self.assertEqual(row['purpose'], 'probe')
        self.assertEqual(row['error_code'], 'http_403')
        self.assertEqual(task['usage']['uncertain_requests'], 1)
        # Later complete evidence replaces the reservation, including on failure.
        known = reconcile(task, config, failed, usage)
        metrics.record_usage(request, usage, known)
        metrics.record_accounted(request, config, failed, usage, known)
        result = metrics.token_accounting(task)
        self.assertEqual((result['reported'], result['reserved'], result['requests']), (60, 0, []))

    def test_partial_historical_evidence_and_pending_request_are_not_reported_usage(self):
        task = {'usage': {'planner': {'tokens': 600}}, 'metrics_schema': 1,
                'request_metrics': [{'role': 'planner', 'reservation': {'tokens': 500,
                 'prompt_tokens': 400, 'completion_tokens': 100}, 'model': 'https://secret.example/token'}]}
        result = metrics.token_accounting(task)
        self.assertEqual((result['reported'], result['reserved'], result['unclassified']), (0, 500, 100))
        self.assertEqual(result['coverage'], 'partial')
        self.assertEqual(result['requests'][0]['status'], 'pending')
        self.assertIsNone(result['requests'][0]['prompt_bytes'])
        self.assertNotIn('secret', json.dumps(result))
        task['usage']['planner']['tokens'] = 500
        task['request_metrics_truncated'] = True
        self.assertEqual(metrics.token_accounting(task)['coverage'], 'partial')

    def test_public_projection_is_read_only_bounded_and_omits_payloads(self):
        from copy import deepcopy
        from cheapos.server import public_task
        task = MetricsTests().task()
        task['usage']['worker']['tokens'] = 60
        task['request_metrics'] = [{'role': 'worker', 'model': 'fixture/model',
             'reservation': {'tokens': 1}, 'prompt': 'SECRET PROMPT', 'api_key': 'SECRET KEY'} for _ in range(60)]
        before = deepcopy(task)
        result = public_task(task)
        self.assertEqual(task, before)
        self.assertNotIn('request_metrics', result)
        accounting = result['token_accounting']
        self.assertEqual((len(accounting['requests']), accounting['omitted_requests'], accounting['reserved']), (50, 10, 60))
        self.assertNotIn('SECRET', json.dumps(accounting))
