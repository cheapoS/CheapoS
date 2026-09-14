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

 def test_specific_diagnostic_round_trip_and_new_attempt(self):
  import json
  from cheapos.server import public_task
  t=self.task();t.update(id='task',usage={},patch='')
  error=pause.PauseError('unknown',diagnostic={'kind':'safe_message','message':'The saved candidate receipt does not match the selected item.'})
  pause.apply(t,error)
  t=json.loads(json.dumps(t))
  self.assertIn('candidate receipt',public_task(t)['error'])
  self.assertIn('candidate receipt',pause.classify(ValueError('wrapper'),t)['explanation'])
  t['request_metrics'].append({'id':'r2','role':'reviewer'})
  self.assertNotIn('candidate receipt',pause.classify(ValueError('new failure'),t)['explanation'])
 def test_structured_runner_limit_and_review_details(self):
  t=self.task()
  d=pause.classify(pause.PauseError('missing_setup',diagnostic={'kind':'missing_executable','executable':'/private/operator/python-not-installed'}),t)
  self.assertIn('python-not-installed',d['explanation']);self.assertNotIn('/private',str(d));self.assertEqual(d['next_action'],'environment')
  d=pause.classify(LimitExceeded('requests',3,2),t)
  self.assertIn('3 used / 2 allowed',d['explanation'])
  d=pause.classify(ProviderError('private body',code='invalid_response_json'),t)
  self.assertIn('Review remains unfinished',d['explanation']);self.assertNotIn('private body',str(d))
 def test_diagnostic_contract_filters_private_markup_and_extra_fields(self):
  for message in ('<script>alert(1)</script>','Bearer token: abc','api_key=secret','https://user:pass@host','x'*401):
   d=pause.public({'version':1,'cause':'unknown','diagnostic':{'kind':'safe_message','message':message}})
   self.assertNotIn('diagnostic',d)
  d=pause.public({'version':1,'cause':'unknown','diagnostic':{'kind':'safe_message','message':'A saved receipt is missing.','private':'SECRET'}})
  self.assertNotIn('SECRET',str(d))

 def test_review_source_and_unidentified_attempt_never_reuse_old_failure(self):
  from cheapos.branch_disagreement import decision
  t=self.task()
  try:decision({'decision':'not-a-decision'})
  except ValueError as error:pause.apply(t,error)
  self.assertIn('explicit valid review decision',t['error'])
  t.pop('request_metrics');t['branch_run']['pause_detail'].pop('diagnostic_id',None)
  self.assertNotIn('explicit valid review decision',pause.classify(ValueError('new unrelated failure'),t)['explanation'])

 def test_review_stall_is_specific_and_preserves_inspection_action_after_public_round_trip(self):
  t=self.task();t['error_code']='progress_limit';t['pending_review']={'stop_diagnostic':{'kind':'review_stall','reason':'invalid_decision','coached':True}}
  d=pause.classify(ValueError('private outer exception'),t)
  self.assertIn('failed validation three times',d['explanation']);self.assertIn('already requested',d['explanation'])
  self.assertEqual(d['next_action'],'inspect');self.assertEqual(pause.public(d),d)
  for malformed in ({'kind':'review_stall','reason':[],'coached':True},{'kind':'review_stall','reason':'bad reason','coached':True},'not a diagnostic'):
   t['pending_review']['stop_diagnostic']=malformed
   self.assertNotIn('diagnostic',pause.classify(ValueError('private'),t))
