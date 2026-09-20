"""Small storage and GET routing checks; no server, inference or Git setup."""
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from cheapos.storage import Store
from cheapos.server import LocalHandler as Handler


class LifetimeIntegrationTests(unittest.TestCase):
    def test_restart_recovers_legacy_route_without_rewriting_task(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            scope = dict(base_url='http://private.invalid/v1', connection_revision='r1', model='groq/vendor/model', role='worker')
            task = dict(id='legacy', status='ready', created_at='2026-09-14T00:00:00Z',
                        gateway_connections=[{**scope, 'gateway_type': 'omniroute'}],
                        request_metrics=[dict(id='request', dispatched=True, role='worker', requested_model=scope['model'],
                                              dispatch_scope=scope, requested_at='2026-09-14T00:00:00Z',
                                              input_tokens=10, output_tokens=5, usage_reconciled=True)])
            with patch('cheapos.lifetime_usage.historical_route_metadata', return_value={}):
                store.save(task)
            self.assertEqual(store.lifetime.raw_requests()[0]['request_provider'], 'unknown')
            path = store.root / 'tasks' / 'legacy' / 'task.json'
            original = path.read_bytes()
            reopened = Store(root)
            self.assertEqual(reopened.lifetime.raw_requests()[0]['request_provider'], 'groq')
            self.assertEqual(reopened.lifetime.summary()['tokens']['reported'], 15)
            self.assertEqual(path.read_bytes(), original)

    def test_store_reloads_and_reconciles_without_counting_twice(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root)
            task={'id':'test','status':'ready','created_at':'2026-09-14T00:00:00Z','usage':{'worker':{'tokens':300,'cost':.01},'cost':.01},
                  'request_metrics':[{'id':'request','dispatched':True,'role':'worker','requested_at':'2026-09-14T00:00:00Z','reservation_tokens':300,'reservation_cost':.01}]}
            store.save(task)
            self.assertEqual(store.lifetime.summary()['tokens']['reserved'],300)
            task['request_metrics'][0].update(input_tokens=10,output_tokens=5,reported_cost=.001,cost_provenance='provider_reported',usage_reconciled=True)
            task['usage']={'worker':{'tokens':15,'cost':.001},'cost':.001}
            store.save(task);store.save(task)
            reopened=Store(root)
            self.assertEqual(reopened.lifetime.summary()['tokens']['reported'],15)
            self.assertEqual(reopened.lifetime.summary()['tokens']['reserved'],0)
            self.assertEqual(reopened.lifetime.summary()['cost']['accounted'],.001)

    def test_usage_get_accepts_only_supported_periods(self):
        with tempfile.TemporaryDirectory() as root:
            handler=Handler.__new__(Handler)
            handler.server=SimpleNamespace(engine=SimpleNamespace(store=Store(root)))
            handler.trusted=lambda:True
            replies=[]
            handler.reply=lambda body,status=200:replies.append((body,status))
            for period in ('all','7','30','invalid'):
                handler.path='/api/lifetime-usage?days='+period
                handler.do_GET()
            self.assertEqual([code for _,code in replies],[200,200,200,400])
            self.assertEqual([body['period'] for body,_ in replies[:3]],['all',7,30])
