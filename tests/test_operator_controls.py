"""Small deterministic operator redirects; no live provider or check process."""
import json
import threading
from pathlib import Path
from unittest.mock import patch
from test_engine import LocalCase, call


class OperatorControlsTests(LocalCase):
    def task(self):
        task=self.fixture(paid=True)
        task.update(conversational=True,execution={'mode':'manual','development_mode':True})
        task['limits']['uncapped_work']=True
        self.engine.store.save(task)
        return task

    def test_live_correction_discards_stale_tool_and_continues_same_runtime(self):
        task=self.task();entered=threading.Event();release=threading.Event();seen=[]
        class Provider:
            streams_output=True
            def complete_with_progress(_,messages,tools,maximum,emit,stopped):
                seen.append(json.dumps(messages))
                if len(seen)==1:
                    emit('answer','Following the old approach');entered.set()
                    if not release.wait(2):raise AssertionError('fixture release missing')
                    message=call('write_file',{'path':'stale.txt','content':'must not run'})
                elif len(seen)==2:
                    message=call('write_file',{'path':'direction.txt','content':'New direction followed'})
                else:message=call('ask_user',{'question':'The requested draft is saved. What should we do next?'})
                return message,{'prompt_tokens':10,'completion_tokens':10}
        self.engine.provider_factory=lambda *args:Provider()
        self.engine.start(task['id']);runtime=self.engine.runtimes[task['id']]
        self.assertTrue(entered.wait(2))
        response=self.engine.steer(task['id'],'Stop the old approach. Write direction.txt with the new direction instead.')
        self.assertEqual(response['operator_continue']['status'],'interrupting')
        release.set();result=self.finish(task)
        self.assertIs(self.engine.runtimes[task['id']],runtime)
        self.assertEqual(result['status'],'awaiting_reply',result.get('error'))
        self.assertFalse((Path(task['workspace'])/'stale.txt').exists())
        self.assertTrue((Path(task['workspace'])/'direction.txt').exists())
        self.assertIn('Write direction.txt',seen[1]);self.assertEqual(len(seen),3)
        self.assertEqual(result['usage']['worker']['tokens'],60)
        self.assertEqual(result['request_metrics'][0]['status'],'cancelled')
        self.assertTrue(result['operator_history'])

    def test_explicit_enable_and_chat_rescue_preserve_history_and_money(self):
        task=self.task();task['execution']['development_mode']=False
        task.update(status='paused',error_code='progress_limit',recovery_blocked=0)
        from cheapos import progress
        progress.state(task).update(route_probes={'worker':9},handoffs=8)
        self.engine.store.save(task)
        dollars=task['limits']['dollars']
        with self.assertRaises(ValueError):self.engine.operator_recovery(task['id'],{'action':'enable'})
        responses=iter([call('ask_user',{'question':'I can continue with the new approach. Which example comes next?'})])
        class Provider:
            def complete(_,messages,tools,maximum):return next(responses),{'prompt_tokens':2,'completion_tokens':2}
        self.engine.provider_factory=lambda *args:Provider()
        saved=self.engine.operator_recovery(task['id'],{'action':'takeover','approved':True,'message':'Use the saved files and explain the next step.'})
        result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply',result.get('error'))
        self.assertEqual(result['limits']['dollars'],dollars)
        self.assertEqual(result['operator_history'][-1]['progress_state']['route_probes']['worker'],9)

    def test_repeated_inspection_has_feedback_without_fixed_stop(self):
        task=self.task();responses=iter([call('read_file',{'path':'math_utils.py'})]*6 + [call('ask_user',{'question':'The file is inspected. Which behavior should change next?'})])
        class Provider:
            def complete(_,messages,tools,maximum):return next(responses),{'prompt_tokens':2,'completion_tokens':2}
        self.engine.provider_factory=lambda *args:Provider()
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply',result.get('error'))
        self.assertEqual(result['worker_turns'],7)
        self.assertTrue(any(e['title']=='Asking for a different approach' for e in result['events']))

    def test_operator_direction_archives_stale_worker_handoff(self):
        task={'execution':{'development_mode':True},'route':{'recovery':{
            'worker':{'from':'old-worker','reason':'old stall'},'reviewer':{'from':'reviewer'}}}}
        self.engine.archive_operator_state(task,'Operator correction')
        self.assertNotIn('worker',task['route']['recovery'])
        self.assertIn('reviewer',task['route']['recovery'])
        self.assertEqual(task['operator_route_history'][-1]['recovery']['worker']['reason'],'old stall')

    def test_malformed_check_calls_can_be_corrected_after_third_attempt(self):
        task=self.task()
        bad={'role':'assistant','tool_calls':[{'id':'bad-check','type':'function',
            'function':{'name':'run_checks','arguments':''}}]}
        responses=iter([bad]*4+[call('ask_user',{'question':'Which focused test should I run?'})])
        class Provider:
            def complete(_,messages,tools,maximum):
                return next(responses),{'prompt_tokens':2,'completion_tokens':2}
        self.engine.provider_factory=lambda *args:Provider()
        self.engine.start(task['id']);result=self.finish(task)
        self.assertEqual(result['status'],'awaiting_reply',result.get('error'))
        self.assertEqual(result['progress_state']['malformed_attempts'],4)
        self.assertEqual(result['usage']['worker']['tokens'],20)
        self.assertFalse(result.get('checks'))
