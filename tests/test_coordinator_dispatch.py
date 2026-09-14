"""Tiny existing demo fixture: no real inference, check process or full Git run."""
import copy
import json
from unittest.mock import patch
from cheapos.engine import Runtime
from cheapos import coordinator_dispatch as recovery
from cheapos import coordinator_recovery as contract
from cheapos.providers import ProviderError
from test_engine import LocalCase, call


class CoordinatorDispatchTests(LocalCase):
    def prepare(self):
        task = self.fixture(paid=True)
        task.update(conversational=True, status='running', action_pending=True,
                    loop_guidance='Use current evidence to finish the edit.',
                    execution={'mode':'manual','coordinator_assistance':True,'coordinator_model':'fixture-local'})
        runtime = Runtime(task)
        runtime.steer_queue = []
        return task, runtime

    def answer(self, **extra):
        return {'outcome':'continue','action':'edit','next_step':'Correct the lower bound in math_utils.py.',
                'expected_result':'The saved patch applies both clamp bounds.', 'evidence':['e1'], **extra}

    def test_existing_fixture_consults_once_then_worker_edits_without_counter_reset(self):
        task, runtime = self.prepare()
        calls=[]
        class Provider:
            def complete(_, messages, tools, maximum):
                calls.append((messages, tools, maximum))
                return {'content':json.dumps(self.answer())}, {'prompt_tokens':10,'completion_tokens':20}
        self.engine.provider_factory=lambda *args: Provider()
        before=copy.deepcopy(task['limits']); turns=task['worker_turns']
        self.assertTrue(recovery.consult(self.engine,runtime,'Repeated current file evidence.'))
        self.assertFalse(recovery.consult(self.engine,runtime,'Repeated current file evidence.'))
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][1],[]);self.assertLessEqual(calls[0][2],512)
        self.assertEqual(task['worker_turns'],turns);self.assertEqual(task['limits'],before)
        self.assertEqual(task['usage']['coordinator']['tokens'],30)
        self.assertEqual(task['request_metrics'][-1]['purpose'],'coordinator_recovery')
        self.assertNotIn('user',[e['kind'] for e in task['events']])
        self.assertIn('lower bound',recovery.continuation(task));self.assertIsNone(recovery.continuation(task))
        self.assertFalse(self.engine.admission.resources['local_inference'].locked())
        # Replay this synthetic accounting record in an isolated non-demo ledger;
        # no provider call or personal store is involved.
        from cheapos.lifetime_usage import LifetimeUsage
        accounted=copy.deepcopy(task);accounted['synthetic']=False;accounted['sample']=False
        for record in accounted['request_metrics']:record['synthetic']=False
        ledger=LifetimeUsage(self.root/'accounting-check')
        ledger.ingest(accounted);ledger.ingest(accounted)
        self.assertEqual(ledger.summary()['tokens']['reported'],30)

    def test_skip_and_failed_attempts_are_durable_and_never_infer_twice(self):
        task,runtime=self.prepare();task['execution']['coordinator_assistance']=False
        with patch.object(self.engine,'request') as request:
            self.assertFalse(recovery.consult(self.engine,runtime,'Repeated evidence'))
            request.assert_not_called()
        task['execution']['coordinator_assistance']=True
        for changed in ({'environment_setup':{'status':'missing'}},{'reconciliation':{'conflicts':['work.py']}},{'pending_approval': {'command':['test']}}, {'pending_review':{'id':'review'}}, {'limit_hit':{'key':'worker_turns'}}, {'active_role':'reviewer'}, {'status':'awaiting_reply'}):
            before=copy.deepcopy(task)
            task.update(changed)
            with patch.object(self.engine,'request') as request:
                self.assertFalse(recovery.consult(self.engine,runtime,'Repeated evidence'))
                request.assert_not_called()
            task.clear();task.update(before)
        with patch.object(self.engine,'request',side_effect=ProviderError('Unavailable local model')) as request:
            self.assertFalse(recovery.consult(self.engine,runtime,'Repeated evidence'))
            self.assertFalse(recovery.consult(self.engine,runtime,'Repeated evidence'))
            self.assertEqual(request.call_count,1)
        self.assertEqual(task['coordinator_recovery'][0]['state'],'failed')
        # Independent outcome variants reuse the same small workspace fixture.
        for advice,expected in (({'content':'try harder'},False), ({'content':json.dumps({'outcome':'needs_user','question':'Should deletion include archived conversations too?', 'reason':'Archive retention is not specified in the accepted scope.', 'evidence':['e1']})},True)):
            task.pop('coordinator_recovery',None)
            with patch.object(self.engine,'request',return_value=advice):
                self.assertEqual(recovery.consult(self.engine,runtime,'Repeated evidence'),expected)
        self.assertEqual(task['status'],'awaiting_reply')
        self.assertIn('archived conversations',task['events'][-2]['detail'])
        task.update(status='running');task.pop('coordinator_recovery',None)
        class CancelledProvider:
            def complete(_,messages,tools,maximum):
                runtime.stop.set()
                raise InterruptedError('Cancelled fixture request')
        self.engine.provider_factory=lambda *args:CancelledProvider()
        with self.assertRaises(InterruptedError):recovery.consult(self.engine,runtime,'Repeated evidence')
        self.assertEqual(task['request_metrics'][-1]['status'],'cancelled')
        self.assertGreater(task['usage']['coordinator']['tokens'],0)
        self.assertEqual(task['usage']['uncertain_requests'],1)
        self.assertFalse(self.engine.admission.resources['local_inference'].locked())

    def test_late_advice_after_pause_or_candidate_change_is_not_applied(self):
        task,runtime=self.prepare()
        def response(*args,**kwargs):
            runtime.stop.set()
            return {'content':json.dumps(self.answer())}
        with patch.object(self.engine,'request',side_effect=response):
            self.assertFalse(recovery.consult(self.engine,runtime,'Repeated evidence'))
        self.assertNotIn('coordinator_guidance',task)
        self.assertEqual(task['coordinator_recovery'][0]['state'],'skipped')

    def test_uncertain_and_completed_saved_attempts_reuse_only_current_advice(self):
        task,runtime=self.prepare()
        episode={'id':'one','key':contract.episode_key(task),'identity':contract.identity(task),
                 'state':'dispatched'}
        task['coordinator_recovery']=[episode]
        self.engine.store.save(task)
        from cheapos.storage import Store
        task=Store(self.engine.store.root).get(task['id']);task['status']='running';runtime.task=task
        episode=task['coordinator_recovery'][0]
        with patch.object(self.engine,'request') as request:
            for state in ('prepared','dispatched'):
                episode['state']=state
                self.assertFalse(recovery.consult(self.engine,runtime,'Repeated evidence'))
            request.assert_not_called()
        episode.update(state='completed',advice=self.answer(),packet=contract.packet(self.engine,runtime,'Repeated evidence'))
        self.engine.store.save(task)
        task=Store(self.engine.store.root).get(task['id']);task['status']='running';runtime.task=task
        self.assertTrue(recovery.consult(self.engine,runtime,'Repeated evidence'))
        self.assertFalse(recovery.consult(self.engine,runtime,'Repeated evidence'))

    def test_real_worker_loop_uses_guidance_then_normal_edit(self):
        task,runtime=self.prepare()
        task.update(status='ready',action_pending=False,requests=[task['prompt']])
        self.engine.file_tool(task,'write_file',{'path':'notes.txt','content':'Implementation in progress\n'})
        calls=[]
        worker=iter([call('read_file',{'path':'math_utils.py'})]*4 + [
            call('read_file',{'path':'test_math_utils.py','start_line':1,'end_line':20}),
            call('replace_text',{'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}),
            call('ask_user',{'question':'The focused edit is saved; which extra examples are required?'})])
        class Provider:
            def __init__(_,role):_.role=role
            def complete(_,messages,tools,maximum):
                calls.append(_.role)
                message={'content':json.dumps({'outcome':'need_context','path':'test_math_utils.py','start_line':1,'end_line':20, 'reason':'The current packet omits the existing test expectations.', 'decision':'Determine which bound the existing tests require.', 'evidence':['e1']})} if _.role=='coordinator' else next(worker)
                return message,{'prompt_tokens':10,'completion_tokens':20}
        self.engine.provider_factory=lambda role,config:Provider(role)
        self.engine.store.save(task);self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply',result.get('error'))
        self.assertEqual(calls.count('coordinator'),1)
        self.assertIn('max(lower',result['patch'])
        self.assertEqual(result['request_worker_turns'],7)
        self.assertEqual(len(result['request_metrics']),8)
        self.assertEqual(result['coordinator_recovery'][0]['state'],'applied')
        self.assertEqual(result['coordinator_recovery'][0]['result']['action'],'replace_text')
