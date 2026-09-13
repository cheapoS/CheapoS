import copy
from cheapos.engine import Engine, Runtime, limits_from
from cheapos.providers import BudgetError, reserve
from test_engine import LocalCase, CONFIG


class WorkLimitTests(LocalCase):
    def test_defaults_and_custom_task_limits_are_independent_and_durable(self):
        source=self.fixture()['source']
        self.engine.config={'worker':dict(CONFIG),'reviewer':dict(CONFIG)}
        self.engine.save_preferences({'limits':{'dollars':0}})
        first=self.engine.create({'repository':source,'prompt':'First task','conversational':True})
        original=copy.deepcopy(first['limits'])
        self.engine.save_preferences({'limits':{**original,'run_minutes':45,'worker_turns':120,'iterations':10}})
        self.assertEqual(self.engine.store.get(first['id'])['limits'],original)
        second=self.engine.create({'repository':source,'prompt':'Extended task','conversational':True})
        self.assertEqual(second['limits']['run_minutes'],45)
        self.assertEqual(second['limits']['dollars'],0)
        self.engine.update_limits(second['id'],{'limits':{**second['limits'],'run_minutes':22}})
        self.engine.save_preferences({'limits':original})
        loaded=Engine(self.engine.store.root,fixture_delay=0)
        try:
            self.assertEqual(loaded.store.get(second['id'])['limits']['run_minutes'],22)
            self.assertEqual(loaded.preferences()['limits']['run_minutes'],15)
            self.assertEqual(loaded.store.get(first['id'])['providers'],first['providers'])
        finally:loaded.shutdown()

    def test_budget_preflight_identifies_the_specific_allowance(self):
        task=self.fixture();task['limits']['dollars']=0
        with self.assertRaises(BudgetError) as failure:reserve(task,CONFIG,[],[],'worker')
        self.assertEqual(failure.exception.limit_hit,{'key':'dollars','used':0,'allowed':0,'remaining':0})
        task['limits']['dollars']=1;task['limits']['reviewer_tokens']=512
        with self.assertRaises(BudgetError) as failure:reserve(task,CONFIG,[],[],'reviewer')
        self.assertEqual(failure.exception.limit_hit['key'],'reviewer_tokens')
        self.assertEqual(failure.exception.limit_hit['remaining'],512)

    def test_working_time_stop_has_a_specific_limit_without_increasing_any_cap(self):
        task=self.fixture();task['status']='running';runtime=Runtime(task)
        runtime.started-=10000
        limits=copy.deepcopy(task['limits'])
        self.engine._run(runtime)
        self.assertEqual(task['status'],'budget_paused')
        self.assertEqual(task['error_code'],'working_time_limit')
        self.assertEqual(task['limit_hit']['key'],'run_minutes')
        self.assertEqual(task['limits'],limits)
        self.assertEqual(task['worker_turns'],0)
