from cheapos.routing import PROBE_MARKER
import threading
import time
from unittest.mock import Mock, patch
from cheapos.engine import Runtime
from cheapos.routing import RoutingPause, select_remote
from cheapos.storage import Store
from test_engine import LocalCase, wait_for
import test_routing


class FakeClock:
    def __init__(self, stop_at=None): self.value=1000.; self.stop_at=stop_at
    def now(self): return self.value
    def is_set(self): return self.stop_at is not None and self.value >= self.stop_at
    def wait(self, seconds): self.value += seconds; return self.is_set()


class CooldownWaitTests(LocalCase):
    chat = test_routing.RoutingTests.chat

    def waiting(self, clock, retry=2):
        task=self.chat('remote');runtime=Runtime(task);runtime.started=clock.now();runtime.stop=clock
        with patch('cheapos.engine.time.monotonic', clock.now), patch('cheapos.engine.time.time', clock.now):
            task['route_unavailable']=self.engine.route_wait_info(runtime,RoutingPause('Provider cooling down',retry_at=clock.now()+retry,scope='provider'))
        task['retry_wait_enabled']=True
        return task,runtime

    def test_no_work_before_expiry_then_one_saved_stage_continuation(self):
        clock=FakeClock();task,runtime=self.waiting(clock)
        def proceed(runtime):
            self.assertGreaterEqual(clock.now(),1002)
            runtime.task['status']='awaiting_reply'
        with patch('cheapos.engine.time.monotonic',clock.now),patch('cheapos.engine.time.time',clock.now),patch.object(self.engine,'_run_until_pause',side_effect=proceed) as run:
            self.engine._run(runtime)
        run.assert_called_once()
        self.assertEqual(task['progress_state']['wait_cycles'],1)
        self.assertEqual(runtime.started,1000)
        self.assertEqual(task['status'],'awaiting_reply')

    def test_pause_and_deadline_end_wait_without_a_probe(self):
        for stop_at in (1000.5,None):
            clock=FakeClock(stop_at);task,runtime=self.waiting(clock,retry=3)
            if stop_at is None: runtime.started-=task['limits']['run_minutes']*60-1
            with patch('cheapos.engine.time.monotonic',clock.now),patch('cheapos.engine.time.time',clock.now),patch.object(self.engine,'_run_until_pause') as run:
                self.engine._run(runtime)
            run.assert_not_called()
            self.assertEqual(task['status'],'paused' if stop_at is not None else 'budget_paused')
            self.assertIsNone(task['route_wait'])
            self.assertLessEqual(clock.now(),1001.25)

    def test_unknown_or_over_budget_retry_is_not_offered(self):
        task=self.chat('remote');runtime=Runtime(task)
        self.assertFalse(self.engine.route_wait_info(runtime,RoutingPause('Unknown'))['can_wait'])
        self.assertFalse(self.engine.route_wait_info(runtime,RoutingPause('Too late',time.time()+99999,'provider'))['can_wait'])
        task['progress_state']['wait_cycles']=3
        self.assertFalse(self.engine.route_wait_info(runtime,RoutingPause('Soon',time.time()+1,'provider'))['can_wait'])
        with self.assertRaisesRegex(ValueError,'No bounded known cooldown'):
            self.engine.start(task['id'],{'retry_when_available':True})

    def test_wait_occupies_active_slot_and_stop_is_immediate(self):
        task=self.chat('remote');other=self.fixture()
        runtime=Runtime(task)
        task.update(status='paused',route_unavailable=self.engine.route_wait_info(runtime,RoutingPause('Cooling',time.time()+20,'provider')))
        self.engine.store.save(task)
        self.engine.start(task['id'],{'retry_when_available':True})
        wait_for(lambda:self.engine.store.get(task['id'])['status']=='waiting_retry')
        with self.assertRaisesRegex(ValueError,'interactive slot is occupied'):self.engine.start(other['id'])
        self.engine.stop(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'paused')
        self.assertIn('Waiting paused',result['error'])

    def test_restart_marks_wait_interrupted_without_dispatch(self):
        task=self.chat('remote');task.update(status='waiting_retry',retry_wait_enabled=True,route_wait={'started_at':time.time()-1,'retry_at':time.time()+20},route_unavailable={'remaining_seconds':30,'can_wait':True})
        task['progress_state']['wait_cycles']=1
        self.engine.store.save(task)
        saved=Store(self.engine.store.root).get(task['id'])
        self.assertEqual(saved['status'],'interrupted')
        self.assertFalse(saved['retry_wait_enabled'])
        self.assertIsNone(saved['route_wait'])
        self.assertLess(saved['route_unavailable']['remaining_seconds'],30)
        self.assertEqual(saved['progress_state']['wait_cycles'],1)

    def test_probe_allowance_is_not_renewed_by_another_selection(self):
        task=self.chat('remote');runtime=Runtime(task)
        task['progress_state']['route_probes']={'worker':4}
        with patch.object(self.engine,'request') as request:
            with self.assertRaises(RoutingPause):select_remote(self.engine,runtime)
        request.assert_not_called()

    def test_exactly_one_probe_after_known_provider_expiry(self):
        from cheapos.providers import ProviderError
        from test_engine import call
        clock=FakeClock();task=self.chat('remote');runtime=Runtime(task);runtime.started=clock.now();runtime.stop=clock
        self.engine.gateway.catalog.return_value['models']=[test_routing.model('provider/a'),test_routing.model('provider/b')]
        with patch('cheapos.engine.time.time',clock.now),patch('cheapos.engine.time.monotonic',clock.now),patch.object(self.engine,'request',return_value=call('routing_ready', {'marker': PROBE_MARKER})) as request:
            self.engine.gateway.pool.record(task['route']['base_url'],'provider/a','worker',error=ProviderError('Cooling',code='gateway_cooldown',retry_after=2,scope='provider'),connection_revision=task['route']['access_policy']['connection_revision'])
            with self.assertRaises(RoutingPause) as stopped:select_remote(self.engine,runtime)
            request.assert_not_called()
            task['route_unavailable']=self.engine.route_wait_info(runtime,stopped.exception)
            self.engine.wait_for_route(runtime)
            select_remote(self.engine,runtime)
            request.assert_called_once()
        self.assertEqual(task['progress_state']['route_probes']['worker'],1)

    def test_pending_review_continues_after_expiry_without_worker_or_check_replay(self):
        import sys
        import test_model_pool
        from cheapos.providers import ProviderError
        from test_engine import call
        task=self.chat('remote');task.update(check_command=[sys.executable,'-m','unittest','discover','-v'],auto_approve_checks=True)
        self.engine.store.save(task)
        test_model_pool.FailoverTests.responding(self,[call('replace_text',{'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}),call('checkpoint',{'summary':'Fixed'}),ProviderError('Cooling',code='gateway_cooldown',retry_after=2,scope='provider')],names=('a','b'))
        self.engine.start(task['id']);paused=self.finish(task)
        self.assertTrue(paused['pending_review'])
        self.assertTrue(paused['route_unavailable']['can_wait'])
        requests=test_model_pool.FailoverTests.responding(self,[call('review_decision',{'decision':'APPROVE','feedback':'Verified'})],names=('a','b'))
        with patch('cheapos.engine.time.time',return_value=paused['route_unavailable']['retry_at']+1):
            self.engine.start(task['id'],{'retry_when_available':True});finished=self.finish(task)
        self.assertEqual(finished['status'],'approved',finished['error'])
        self.assertEqual(finished['worker_turns'],paused['worker_turns'])
        self.assertEqual(finished['checks'],paused['checks'])
        self.assertEqual(finished['iterations'],1)
        self.assertTrue(all(request['role']=='reviewer' for request in requests))
