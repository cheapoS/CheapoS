import tempfile
import unittest
from unittest.mock import patch
from cheapos.model_pool import FreeModelPool, observe_task

class OutcomeTests(unittest.TestCase):
    def test_threshold_recency_roles_idempotence_acceptance_and_legacy(self):
        with tempfile.TemporaryDirectory() as root, patch('cheapos.model_pool.time.time',return_value=10000000):
            pool=FreeModelPool(root);url='http://localhost:20128/v1'
            pool.record(url,'a','worker',error='outage')
            for i in range(3):
                pool.record_outcome(url,'a','worker',str(i),'private-task-name',{'invalid_output':1})
                pool.record_outcome(url,'z','worker',str(i),'private-task-name',{'checkpoints':1,'valid_calls':2})
            pool.record_outcome(url,'z','worker','2','private-task-name',{'checkpoints':1,'valid_calls':2})
            pool.record_acceptance(url,'z','worker','private-task-name','2')
            pool=FreeModelPool(root)
            evidence=pool.observation(url,'z')['role_evidence']['worker']
            self.assertEqual((evidence['samples'],evidence['accepted']),(3,1))
            self.assertLess(pool.rank(url,{'id':'z'},'worker'),pool.rank(url,{'id':'a'},'worker','a'))
            self.assertEqual(pool.rank(url,{'id':'z'},'reviewer')[0],0)
            self.assertTrue(pool.observation(url,'a')['cooling_down'])
            with patch('cheapos.model_pool.time.time',return_value=10000000+31*86400):
                self.assertEqual(pool.observation(url,'z')['role_evidence']['worker']['samples'],0)
            for i in range(70):pool.record_outcome(url,'z','worker',str(i),'private-task-name',{'valid_calls':1})
            self.assertEqual(pool.observation(url,'z')['role_evidence']['worker']['samples'],64)
            self.assertNotIn('private-task-name',pool.path.read_text())

    def test_outage_cancel_and_probe_are_not_quality_samples(self):
        with tempfile.TemporaryDirectory() as root:
            pool=FreeModelPool(root);url='http://localhost:20128/v1'
            task={'id':'private','providers':{'worker':{'base_url':url}},'request_metrics':[{'run_id':'r','role':'worker','model':'a','dispatched':True,'error_code':'http_503'}],'events':[]}
            observe_task(pool,task,'r')
            self.assertEqual(pool.observation(url,'a')['role_evidence']['worker']['samples'],0)
            task['request_metrics'][0]['error_code']='invalid_tool_envelope'
            task['metrics_cancelled']=True;observe_task(pool,task,'r')
            self.assertEqual(pool.observation(url,'a')['role_evidence']['worker']['samples'],0)
            task['metrics_cancelled']=False;observe_task(pool,task,'r')
            self.assertEqual(pool.observation(url,'a')['role_evidence']['worker']['invalid_output'],1)
