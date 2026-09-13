import threading
import unittest
from unittest.mock import patch

from cheapos import branch_planner
import test_branch_start as fixtures


class BranchPlanningRaceTests(unittest.TestCase):
    setUp=fixtures.BranchStartTests.setUp

    def test_concurrent_captures_only_register_one_planner_and_reject_other_before_inference(self):
        barrier=threading.Barrier(2)
        entered=threading.Event();rejected=threading.Event();release=threading.Event()
        original=branch_planner.capture_inputs
        calls=[];errors=[]
        def capture(*args,**kwargs):
            value=original(*args,**kwargs);barrier.wait(timeout=5);return value
        def plan(engine,runtime,inputs):
            calls.append(runtime.task['id']);entered.set()
            if not release.wait(5):raise RuntimeError('Audit fixture did not release planner')
            raise ValueError('Fixture ends without inference')
        def invoke(identity):
            try:self.engine.branch.plan({**self.values,'planning_id':identity,'limits':{'dollars':0}})
            except Exception as error:
                errors.append(str(error))
                if 'Another task started' in str(error):rejected.set()
        with patch.object(branch_planner,'capture_inputs',capture),patch.object(branch_planner,'plan',plan):
            threads=[threading.Thread(target=invoke,args=(identity,)) for identity in ('one','two')]
            for thread in threads:thread.start()
            try:
                self.assertTrue(entered.wait(5));self.assertTrue(rejected.wait(5))
                self.assertEqual(len(self.engine.runtimes),1)
                self.assertEqual(len(calls),1)
                self.engine.startup.busy=lambda:False
                with self.assertRaises(ValueError):self.engine.start(calls[0])
                with self.assertRaises(ValueError):self.launch(calls[0])
            finally:
                release.set()
                for thread in threads:thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(len(calls),1)
        self.assertEqual(self.engine.runtimes,{})
        self.assertEqual(self.engine.branch.planning,{})
        refused=next(task for task in self.engine.store.list() if 'Another task started' in (task.get('error') or ''))
        self.assertEqual(refused['status'],'paused')
        self.assertEqual(refused['branch_run']['consumption']['requests'],0)
        self.assertEqual(refused['branch_run']['consumption']['working_seconds'],0)


if __name__=='__main__':unittest.main()
