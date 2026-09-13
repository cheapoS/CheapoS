"""Retain research across compaction and end read-only loops within existing limits."""
import json
from pathlib import Path
from unittest.mock import Mock

import test_chat
from cheapos.engine import Engine, observation_key
from cheapos.providers import ProviderError
from test_engine import LocalCase, call


class AnswerRecoveryTests(LocalCase):
    chat = test_chat.ChatTests.chat
    provider = test_chat.ChatTests.provider

    def unfinished_patch(self):
        t=self.fixture(paid=True)
        t['conversational']=True
        self.engine.file_tool(t,'write_file',{'path':'notes.txt','content':'Needs a correction\n'})
        t.update(status='error',error_code='stream_error',answer_pending=True,turn_start_patch=t['patch'])
        self.engine.store.save(t)
        return t

    def test_retry_of_old_answer_recovery_keeps_edit_tools_and_existing_limits(self):
        t=self.unfinished_patch()
        requests=self.provider([
            call('replace_text',{'path':'notes.txt','old_text':'Needs a correction','new_text':'Corrected notes'}),
            call('ask_user',{'question':'Should the notes include an example?'}),
        ])
        self.engine.start(t['id']);result=self.finish(t)
        tools={item['function']['name'] for item in requests[0][1]}
        self.assertIn('replace_text',tools);self.assertIn('run_checks',tools)
        self.assertIn('checkpoint',tools);self.assertIn('ask_user',tools)
        self.assertIn('read_file',tools);self.assertIn('list_files',tools)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertFalse(result['answer_pending']);self.assertFalse(result['action_pending'])
        self.assertEqual(result['limits'],t['limits'])
        self.assertEqual(result['request_worker_turns'],2)
        self.assertIn('Corrected notes',result['patch']);self.assertFalse(result['checkpoints'])

    def test_repeated_reads_of_unfinished_patch_can_recover_through_checks_and_review(self):
        t=self.unfinished_patch();t['answer_pending']=False;self.engine.store.save(t)
        requests=self.provider([call('read_file',{'path':'math_utils.py'})]*3+[
            call('replace_text',{'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}),
            call('run_checks'),call('checkpoint',{'summary':'Fixed bounds','uncertainties':''}),
            call('review_decision',{'decision':'APPROVE','feedback':'Both bounds work.'}),
        ])
        self.engine.start(t['id']);result=self.finish(t)
        self.assertEqual(result['status'],'approved',result['error'])
        self.assertEqual(len(requests),7)
        self.assertIn('read_file',{tool['function']['name'] for tool in requests[3][1]})
        self.assertEqual(len(result['checks']),1)
        self.assertEqual(result['checkpoints'][-1]['decision'],'APPROVE')
        self.assertEqual(result['limits'],t['limits'])

    def test_recovery_can_read_missing_context_without_guessing(self):
        t=self.unfinished_patch()
        requests=self.provider([call('read_file',{'path':'math_utils.py'}),call('ask_user',{'question':'Should I add an example?'})])
        self.engine.start(t['id']);result=self.finish(t)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertEqual(len(requests),2)
        self.assertTrue([e for e in result['events'] if e['title']=='read file'])

    def test_recovery_still_bounds_repeated_unchanged_reads(self):
        t=self.unfinished_patch()
        requests=self.provider([call('read_file',{'path':'math_utils.py'})]*5)
        self.engine.start(t['id']);result=self.finish(t)
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['error_code'],'progress_limit')
        self.assertLessEqual(len(requests),4)

    def test_interrupted_action_recovery_survives_restart_without_automatic_retry(self):
        t=self.unfinished_patch()
        provider=Mock();provider.complete.side_effect=ProviderError('Interrupted',code='stream_error')
        self.engine.provider_factory=lambda *args:provider
        self.engine.start(t['id']);first=self.finish(t)
        self.assertEqual(first['status'],'error');provider.complete.assert_called_once()
        self.assertTrue(first['action_pending']);self.assertFalse(first['answer_pending'])
        self.engine.shutdown();self.engine=Engine(self.engine.store.root)
        requests=self.provider([call('ask_user',{'question':'Which example should I add?'})])
        self.engine.start(t['id']);result=self.finish(t)
        self.assertEqual(result['status'],'awaiting_reply')
        self.assertTrue(requests[0][1]);self.assertEqual(len(requests),1)
        self.assertEqual(result['request_worker_turns'],2)
        self.assertEqual(result['usage']['uncertain_requests'],1)

    def test_action_recovery_still_respects_the_worker_turn_limit(self):
        t=self.unfinished_patch();t['request_worker_turns']=t['limits']['worker_turns'];self.engine.store.save(t)
        factory=Mock();self.engine.provider_factory=factory
        self.engine.start(t['id']);result=self.finish(t)
        self.assertEqual(result['status'],'budget_paused');factory.assert_not_called()

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

    def test_forced_answer_cannot_execute_tools_and_requires_correction_after_failure(self):
        t=self.chat();t.update(status='paused',error_code='progress_limit');self.engine.store.save(t)
        requests=self.provider([call('write_file',{'path':'unwanted.txt','content':'no'}),{'content':'Here is the answer.'}])
        self.engine.start(t['id']);first=self.finish(t)
        self.assertEqual(first['status'],'paused')
        self.assertTrue(first['answer_pending'])
        self.assertFalse((Path(t['workspace'])/'unwanted.txt').exists())
        with self.assertRaisesRegex(ValueError, 'specific correction'):
            self.engine.start(t['id'])
        self.assertEqual(requests[0][1], [])
        self.engine.start(t['id'], {'message':'Answer from the existing evidence. Do not edit.'});last=self.finish(t)
        self.assertEqual(last['status'],'awaiting_reply')
        self.assertEqual(last['request_worker_turns'],1)
        self.assertEqual(last['worker_turns'],2)

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

    def test_action_snapshot_keeps_current_file_middle_and_latest_request_without_old_read_noise(self):
        t=self.unfinished_patch()
        body='start\n'+'padding\n'*700+'CURRENT MIDDLE\n'+'padding\n'*400+'end\n'
        self.engine.file_tool(t,'write_file',{'path':'current.py','content':body})
        self.engine.event(t,'tool','read file',{'arguments':{'path':'current.py'},'result':{'content':'OLD STALE TEXT'}})
        t.update(action_pending=True,requests=[t['prompt'],'Convert only these tests to unittest.'])
        messages=self.engine.initial_messages(t);summary=json.loads(messages[1]['content'])
        current=next(f for f in summary['current_files'] if f['path']=='current.py')
        self.assertTrue(current['complete']);self.assertEqual(current['content'],body)
        self.assertEqual(summary['latest_message'],'Convert only these tests to unittest.')
        self.assertNotIn('OLD STALE TEXT',json.dumps(messages));self.assertNotIn('recent_activity',summary)

    def test_action_snapshot_limits_content_and_keeps_workspace_boundaries(self):
        t=self.unfinished_patch()
        self.engine.file_tool(t,'write_file',{'path':'large.py','content':'x'*13000})
        # An old/malformed observation cannot make context read outside the workspace.
        self.engine.event(t,'tool','read file',{'arguments':{'path':'../outside.txt'},'result':{}})
        t['action_pending']=True
        summary=json.loads(self.engine.initial_messages(t)[1]['content'])
        files=summary['current_files']
        self.assertLessEqual(sum(len(f.get('content','')) for f in files),24000)
        self.assertFalse(next(f for f in files if f['path']=='large.py')['complete'])
        self.assertIn('error',next(f for f in files if f['path']=='../outside.txt'))
