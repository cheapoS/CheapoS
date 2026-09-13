"""Retain research across compaction and end read-only loops within existing limits."""
import json
from pathlib import Path
from unittest.mock import Mock

import test_chat
from cheapos.engine import Engine, observation_key
from test_engine import LocalCase, call


class AnswerRecoveryTests(LocalCase):
    chat = test_chat.ChatTests.chat
    provider = test_chat.ChatTests.provider

    def test_compaction_keeps_multiple_web_sources_local_context_and_direction(self):
        t=self.chat('Recommend setup instructions from https://example.org/docs')
        for index in range(3):
            self.engine.event(t,'tool','read url',{'arguments':{'url':f'https://example.org/doc{index}'},'result':{'source_url':f'https://example.org/doc{index}','title':f'Guide {index}','start_line':1,'end_line':120,'has_more':True,'content':f'Guide {index} start\n'+('evidence\n'*1400)+f'Guide {index} end','links':['https://example.org/'+str(n)+'x'*150 for n in range(60)]}})
        self.engine.file_tool(t,'read_file',{'path':'math_utils.py'})
        t['loop_guidance']='Give your answer now from the sources already read.'
        messages=self.engine.initial_messages(t)
        context=json.loads(messages[1]['content'])
        self.assertLess(len(json.dumps(context['recent_activity'])),24000)
        self.assertEqual(len(context['web_reads_this_request']),3)
        for index in range(3):
            self.assertIn(f'Guide {index} start',messages[1]['content'])
            self.assertIn(f'Guide {index} end',messages[1]['content'])
        self.assertIn('return min(value, upper)',messages[1]['content'])
        self.assertIn(t['loop_guidance'],messages[-1]['content'])
        self.assertNotIn('links',json.dumps(context['recent_activity']))

    def test_url_aliases_and_implicit_ranges_cannot_evade_repeat_detection(self):
        result={'source_url':'https://github.com/o/r/blob/main/README.md','content':'1: Same evidence','cached':False}
        first=observation_key('read_url',{'url':'https://github.com/o/r'},result)
        second=observation_key('read_url',{'url':result['source_url'],'start_line':1,'end_line':120},{**result,'cached':True})
        self.assertEqual(first,second)
        self.assertNotEqual(first,observation_key('read_url',{}, {**result,'content':'121: New evidence'}))

    def test_last_research_turn_is_reserved_for_an_accounted_answer(self):
        t=self.chat();t['limits']['checkpoint_turns']=3;self.engine.store.save(t)
        requests=self.provider([call('read_file',{'path':'math_utils.py'}),call('list_files'),{'content':'The project contains clamp and its tests.'}])
        self.engine.start(t['id']);result=self.finish(t)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertEqual(len(requests),3)
        self.assertEqual(requests[-1][1],[])
        self.assertEqual(result['request_worker_turns'],3)
        self.assertEqual(result['usage']['worker']['tokens'],45)
        self.assertEqual(result['limits'],t['limits'])
        self.assertEqual(result['checkpoints'],[])

    def test_resume_of_old_readonly_loop_answers_without_restarting_research(self):
        t=self.chat()
        self.engine.file_tool(t,'read_file',{'path':'math_utils.py'})
        t.update(status='paused',error_code='progress_limit',request_worker_turns=26,worker_turns=104)
        self.engine.store.save(t)
        requests=self.provider([{'content':'I read the source: the lower bound is not applied.'}])
        self.engine.start(t['id']);result=self.finish(t)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0][1],[])
        self.assertEqual(result['request_worker_turns'],27)
        self.assertEqual(result['worker_turns'],105)
        self.assertEqual(result['changes'],[])

    def test_forced_answer_cannot_execute_tools_and_resume_stays_in_answer_step(self):
        t=self.chat();t.update(status='paused',error_code='progress_limit');self.engine.store.save(t)
        requests=self.provider([call('write_file',{'path':'unwanted.txt','content':'no'}),{'content':'Here is the answer.'}])
        self.engine.start(t['id']);first=self.finish(t)
        self.assertEqual(first['status'],'paused')
        self.assertTrue(first['answer_pending'])
        self.assertFalse((Path(t['workspace'])/'unwanted.txt').exists())
        self.engine.start(t['id']);last=self.finish(t)
        self.assertEqual(last['status'],'awaiting_reply')
        self.assertTrue(all(tools==[] for _,tools in requests))
        self.assertEqual(last['request_worker_turns'],2)

    def test_answer_recovery_never_bypasses_edits_or_hard_budget(self):
        t=self.chat();self.engine.file_tool(t,'write_file',{'path':'new.txt','content':'unreviewed'})
        t.update(status='paused',error_code='progress_limit');self.engine.store.save(t)
        requests=self.provider([call('ask_user',{'question':'Which check should I run?'})])
        self.engine.start(t['id']);result=self.finish(t)
        self.assertTrue(requests[0][1])
        self.assertEqual(len(result['changes']),1)
        self.assertFalse(result['checkpoints'])
        fresh=self.chat();fresh.update(status='paused',error_code='progress_limit',request_worker_turns=40,worker_turns=40)
        self.engine.store.save(fresh)
        factory=Mock();self.engine.provider_factory=factory
        self.engine.start(fresh['id']);result=self.finish(fresh)
        self.assertEqual(result['status'],'budget_paused')
        factory.assert_not_called()
