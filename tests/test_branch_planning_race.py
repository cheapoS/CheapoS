import threading
import copy
import json
import unittest
from unittest.mock import patch

from cheapos import branch_planner
import test_branch_start as fixtures


class BranchPlanningRaceTests(unittest.TestCase):
    setUp=fixtures.BranchStartTests.setUp

    def test_concurrent_captures_only_register_one_planner_and_reject_other_before_inference(self):
        entered=threading.Event();rejected=threading.Event();release=threading.Event()
        original=branch_planner.capture_inputs
        calls=[];errors=[]
        def capture(*args,**kwargs):
            return original(*args,**kwargs)
        def plan(engine,runtime,inputs):
            calls.append(runtime.task['id']);entered.set()
            if not release.wait(5):raise RuntimeError('Audit fixture did not release planner')
            raise ValueError('Fixture ends without inference')
        def invoke(identity):
            try:self.engine.branch.plan({**self.values,'planning_id':identity,'limits':{'dollars':0}})
            except Exception as error:
                errors.append(str(error))
                if 'slot is occupied' in str(error):rejected.set()
        with patch.object(branch_planner,'capture_inputs',capture),patch.object(branch_planner,'plan',plan):
            threads=[threading.Thread(target=invoke,args=(identity,)) for identity in ('one','two')]
            for thread in threads:thread.start()
            try:
                self.assertTrue(entered.wait(5));self.assertTrue(rejected.wait(5))
                self.assertEqual(len(self.engine.runtimes),1)
                self.assertEqual(len(calls),1)
                self.engine.startup.busy=lambda:False
                with self.assertRaises(ValueError):self.engine.start(calls[0])
                saved_before=self.engine.store.get(calls[0])
                with self.assertRaises(ValueError):self.launch(calls[0])
                with self.assertRaises(ValueError):self.engine.branch.resume(calls[0],{})
                self.assertEqual(self.engine.store.get(calls[0]),saved_before)
                # A separate Interactive read/respond finishes while the planner
                # remains at its deterministic barrier; no live model calls.
                responses=iter([{'role':'assistant','content':None,'tool_calls':[{'id':'read','type':'function','function':{'name':'read_file','arguments':json.dumps({'path':'hello.py'})}}]},
                                {'role':'assistant','content':'hello.py assigns value to 1.'}])
                class Provider:
                    def complete(self, messages, tools, maximum):
                        return next(responses), {'prompt_tokens':3,'completion_tokens':2,'cost':0}
                self.engine.provider_factory=lambda role,config:Provider()
                chat=self.engine.create({'repository':str(self.source),'prompt':'Explain hello.py','conversational':True})
                before=copy.deepcopy(self.engine.store.get(calls[0])['usage'])
                self.engine.start(chat['id'])
                self.engine.runtimes[chat['id']].thread.join(3)
                self.assertFalse(self.engine.runtimes[chat['id']].thread.is_alive())
                result=self.engine.store.get(chat['id'])
                self.assertEqual(result['status'],'awaiting_reply')
                self.assertEqual(result['usage']['worker']['tokens'],10)
                self.assertEqual(self.engine.store.get(calls[0])['usage'],before)
                self.assertFalse(release.is_set())
                self.engine.runtimes.pop(chat['id'])

            finally:
                release.set()
                for thread in threads:thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(len(calls),1)
        self.assertEqual(self.engine.runtimes,{})
        self.assertEqual(self.engine.branch.planning,{})
        # Capacity is reserved before capture, so the refused request never
        # creates a task or consumes planning work.
        self.assertEqual(len(self.engine.store.list()),2)
        self.assertEqual(self.engine.admission.pending,{})
        self.assertTrue(any('slot is occupied' in error for error in errors))


if __name__=='__main__':unittest.main()
