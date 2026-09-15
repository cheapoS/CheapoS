import unittest
from cheapos import route_schedule
from cheapos.provider_recovery import provider

class ScheduleTests(unittest.TestCase):
    def test_new_round_retains_lifetime_accounting(self):
        task={'progress_state':{'route_probes':{'worker':99}}}
        first=route_schedule.begin(task,'worker',100)
        first['probes']=4
        self.assertEqual(route_schedule.begin(task,'worker',129)['probes'],4)
        second=route_schedule.begin(task,'worker',130)
        self.assertEqual(second['probes'],0)
        self.assertEqual(second['round'],2)
        self.assertEqual(task['progress_state']['route_probes']['worker'],99)

    def test_rejections_expire_and_legacy_records_are_not_permanent(self):
        self.assertFalse(route_schedule.rejected({'model':'a'},100))
        self.assertTrue(route_schedule.rejected({'retry_at':110},100))
        self.assertFalse(route_schedule.rejected({'retry_at':110},110))

    def test_transport_alias_shares_provider_identity(self):
        self.assertEqual(provider('no-think/antigravity/claude'),provider('antigravity/claude'))

    def test_catalog_outage_is_retryable_but_credentials_need_action(self):
        from cheapos.routing import catalog_pause
        self.assertIsNotNone(catalog_pause('unavailable').retry_at)
        self.assertIsNotNone(catalog_pause('starting').retry_at)
        self.assertIsNone(catalog_pause('auth_required').retry_at)
        self.assertIn('API key',str(catalog_pause('auth_required')))

    def test_restart_only_resumes_marked_waits_and_keeps_consent_boundary(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        import threading
        from cheapos.engine import Engine
        tasks={'a':{'id':'a','route_resume_on_start':True},
               'b':{'id':'b','route_resume_on_start':True,'branch_run':{}},
               'c':{'id':'c','status':'interrupted'}}
        stop=Mock();stop.is_set.return_value=False
        engine=SimpleNamespace(route_restore_stop=stop,lock=threading.RLock(),startup=SimpleNamespace(busy=lambda:False),
            store=SimpleNamespace(tasks=tasks,lock=threading.RLock(),save=Mock(),get=lambda key:tasks[key]),
            start=Mock(),branch=SimpleNamespace(resume=Mock(return_value={'needs_consent':True})))
        with patch('cheapos.engine.threading.Thread') as thread:
            Engine.restore_route_waits(engine)
            thread.call_args.kwargs['target']()
        engine.start.assert_called_once_with('a',{'retry_when_available':True})
        engine.branch.resume.assert_called_once_with('b',{})
        self.assertFalse(tasks['a']['route_resume_on_start'])
        self.assertFalse(tasks['b']['route_resume_on_start'])

    def test_transport_failures_use_availability_recovery(self):
        from cheapos.provider_recovery import outage
        for code in ('stream_error','stream_interrupted','http_503','model_connection'):
            self.assertTrue(outage({},'worker',{'error_code':code}))
        self.assertFalse(outage({},'worker',{'error_code':'invalid_response_json'}))
