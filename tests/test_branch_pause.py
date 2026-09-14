import unittest
from cheapos import branch_pause as pause, branch_runs
from cheapos.providers import ProviderError
from cheapos.branch_budget import LimitExceeded

class PauseDetails(unittest.TestCase):
 def task(self):
  return {'branch_run':{'schema_version':1,'id':'run','event_sequence':0,'status':'running','current_item_id':'one','items':[{'id':'one','status':'working'}],'events':[]},'active_role':'reviewer','request_metrics':[{'id':'r1','role':'reviewer','model':'fixture/reviewer'}]}
 def test_typed_causes_never_guess_from_words(self):
  t=self.task()
  self.assertEqual(pause.classify(ValueError('SECRET limit exhausted'),t)['cause'],'unknown')
  self.assertEqual(pause.classify(LimitExceeded('requests',3,2),t)['cause'],'exhausted_work')
  q=pause.classify(ProviderError('SECRET https://key@example.com',code='gateway_cooldown'),t)
  self.assertEqual(q['cause'],'provider_quota');self.assertEqual(q['stage'],'reviewing');self.assertNotIn('SECRET',str(q));self.assertNotIn('retry_at',q)
 def test_public_retemplates_and_bounds(self):
  d=pause.public({'version':1,'cause':'provider_quota','explanation':'SECRET','next_action':'merge','model':'https://secret@host','diagnostic_id':'r1','retry_at':float('inf')})
  self.assertEqual(d['next_action'],'models');self.assertNotIn('SECRET',str(d));self.assertNotIn('model',d);self.assertNotIn('retry_at',d)
 def test_nested_pause_and_restart_preserve_cause_then_clear(self):
  t=self.task();pause.apply(t,ProviderError('SECRET',code='gateway_cooldown'))
  self.assertEqual(pause.classify(ValueError('generic outer'),t)['cause'],'provider_quota')
  t['branch_run']['schema_version']=1;branch_runs.recover_restart(t['branch_run']);self.assertEqual(t['branch_run']['pause_detail']['cause'],'provider_quota')
  t['branch_run']['status']='running';branch_runs.recover_restart(t['branch_run']);self.assertEqual(t['branch_run']['pause_detail']['cause'],'restart')
  pause.clear(t['branch_run']);self.assertNotIn('pause_detail',t['branch_run']);self.assertTrue(t['branch_run']['events'])
 def test_context_and_explicit_dispute(self):
  d=pause.classify(pause.PauseError('repeated_review_dispute',stage='reviewing',diagnostic_id='review-2'),self.task())
  self.assertEqual(d['item_id'],'one');self.assertEqual(d['diagnostic_id'],'review-2');self.assertEqual(d['next_action'],'review_dispute')

 def test_summary_and_full_public_pause_cannot_echo_raw_exception(self):
  from cheapos.server import public_task
  t=self.task();t.update(id='task',usage={},patch='')
  pause.apply(t,ProviderError('SECRET upstream https://key@host',code='gateway_cooldown'))
  for summary in (False,True):
   result=public_task(t,summary=summary)
   self.assertNotIn('SECRET',str(result));self.assertEqual(result['branch_run']['pause_detail']['cause'],'provider_quota')
  t['branch_run']['status']='merged'
  self.assertIsNone(public_task(t)['branch_run']['pause_detail']);self.assertIsNone(public_task(t)['error'])
