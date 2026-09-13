import unittest
from cheapos import routing_trace as trace


class RoutingTraceTests(unittest.TestCase):
    def test_order_redaction_and_request_identity(self):
        task={};t=trace.begin(task,'worker','route/a')
        trace.candidate(t,'route/b','cooldown');trace.candidate(t,'route/a','eligible')
        trace.selected(t,'route/a')
        metric={'id':'request-1','role':'worker','model':'route/a','dispatched':True,'purpose':'probe',
                'status':'pending','api_key':'secret','prompt':'private','headers':{'Authorization':'secret'}}
        trace.request(task,metric)
        metric.update(status='responded',seconds=0.5,served_model='actual/b',identity_provenance='response_model')
        trace.request(task,metric)
        self.assertEqual(len(t['attempts']),1)
        self.assertEqual([c['reason'] for c in t['candidates']],['cooldown','eligible'])
        self.assertEqual(t['attempts'][0]['served_model'],'actual/b')
        self.assertEqual(t['gateway_attempts'],'unavailable')
        self.assertNotIn('secret',str(task));self.assertNotIn('private',str(task))
        trace.candidate(t,'https://user:secret@host','error containing prompt')
        self.assertEqual(t['candidates'][-1],{'model':'unknown','reason':'unknown'})

    def test_bounds_unknown_identity_and_no_phantom_dispatch(self):
        task={}
        trace.request(task,{'id':'not-sent','dispatched':False})
        self.assertEqual(task,{})
        for _ in range(40):trace.begin(task,'reviewer','route/b')
        self.assertEqual(len(task['routing_traces']),32)
        for i in range(80):trace.request(task,{'id':str(i),'role':'reviewer','model':'route/b','dispatched':True})
        t=task['routing_traces'][-1]
        self.assertEqual(len(t['attempts']),64)
        self.assertIsNone(t['attempts'][-1]['served_model'])
        self.assertEqual(t['attempts'][-1]['identity_provenance'],'unknown')
        task['metric_run_id']='new-turn'
        trace.request(task,{'id':'next','role':'reviewer','model':'route/b','dispatched':True})
        self.assertEqual(task['routing_traces'][-1]['run_id'],'new-turn')
        self.assertEqual(len(task['routing_traces'][-1]['attempts']),1)
        t=task['routing_traces'][-1]
        for i in range(70):trace.candidate(t,'excluded/'+str(i),'access_excluded')
        trace.candidate(t,'route/b','cached_probe')
        self.assertEqual(len(t['candidates']),64)
        self.assertTrue(t['candidates_truncated'])
        self.assertEqual(t['candidates'][-1],{'model':'route/b','reason':'cached_probe'})

    def test_context_fit_does_not_mistake_old_usage_for_current_need(self):
        model={'tool_calling':True,'context_length':1024}
        self.assertEqual(trace.context_fit({'request_metrics':[{'input_tokens':2000,'dispatched':True}]},model),'fit_unknown')
        self.assertEqual(trace.context_fit({'routing_required_context_tokens':2048},model),'context_insufficient')
        self.assertEqual(trace.context_fit({}, {'tool_calling':False}),'capability_missing')
        self.assertEqual(trace.context_fit({}, {'context_length':None}),'fit_unknown')
