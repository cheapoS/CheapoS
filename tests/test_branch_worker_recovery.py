from cheapos.routing import PROBE_MARKER
import copy,json,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from cheapos.branch_worker_recovery import queue
from cheapos.engine import Runtime
from cheapos.routing import select_remote,RoutingPause
from test_engine import call
from test_routing import model
import test_branch_start as fixture

class RecoveryPolicyTests(unittest.TestCase):
 def fixture(self):
  task={'status':'paused','error_code':'progress_limit','error':'Repeated evidence','active_role':'worker','execution':{'mode':'remote'},'route':{},'providers':{'worker':{'model':'worker-a'}},'branch_run':{'workspace_mapping':{},'expected_feature_tip':'tip','check_scope':[]},'worker_turns':12,'usage':{'worker':{'tokens':123}}}
  task['route']={'ready':True};item={'id':'one','status':'working','recovery':{'attempts':0}}
  engine=SimpleNamespace(event=Mock(),store=SimpleNamespace(save=Mock()))
  controller=SimpleNamespace(engine=engine,validate_authority=Mock(),scopes=SimpleNamespace(authorize=Mock(return_value=True)))
  runtime=SimpleNamespace(task=task,stop=threading.Event(),guard=Mock(),handoffs=0,observations={},file_observations={},edit_versions={})
  return controller,runtime,item
 def test_exclusions_dispatch_nothing(self):
  changes=[{'status':'waiting_approval'},{'error_code':'environment_setup'},{'error_code':'worker_turn_limit'},{'pending_approval':{'command':['x']}},{'pending_review':{'id':'review'}},{'limit_hit':{'key':'requests'}},{'execution':{'mode':'manual'}},{'checks':[{'next_action':'Repeated evidence'}]}]
  for change in changes:
   c,r,i=self.fixture();r.task.update(change)
   with self.subTest(change=change):self.assertFalse(queue(c,r,i));c.engine.store.save.assert_not_called()
  for reason in ('operator','question','review'):
   c,r,i=self.fixture()
   if reason=='operator':r.stop.set()
   if reason=='question':r.task['branch_run']['waiting_for_user']='Question'
   if reason=='review':i['status']='reviewing'
   self.assertFalse(queue(c,r,i))
 def test_persisted_attempts_and_no_renewal(self):
  c,r,i=self.fixture()
  with patch('cheapos.branch_worker_recovery.branch_workspace.validate_owned'):
   for n in range(2):
    r.task.update(status='paused',error_code='progress_limit',error='Repeated evidence')
    self.assertTrue(queue(c,r,i));r.task=json.loads(json.dumps(r.task))
   r.task.update(status='paused',error_code='progress_limit',error='Repeated evidence')
   self.assertFalse(queue(c,r,i))
  self.assertEqual(r.task['branch_run']['implementation_recovery']['attempts'],2)
  self.assertEqual(i['recovery']['attempts'],2);self.assertEqual(r.task['worker_turns'],12);self.assertEqual(r.task['usage']['worker']['tokens'],123)
  self.assertEqual(c.engine.store.save.call_count,2)
 def test_drift_budget_and_missing_consent_cannot_queue(self):
  for stage in ('guard','authority','ownership','consent'):
   c,r,i=self.fixture();owned=Mock()
   if stage=='guard':r.guard.side_effect=ValueError('Limit reached')
   if stage=='authority':c.validate_authority.side_effect=ValueError('Authority changed')
   if stage=='ownership':owned.side_effect=ValueError('Branch changed')
   if stage=='consent':r.task['branch_run']['check_scope']=[{'command':['python']}];c.scopes.authorize.return_value=False
   with patch('cheapos.branch_worker_recovery.branch_workspace.validate_owned',owned):
    if stage=='consent':self.assertFalse(queue(c,r,i))
    else:
     with self.assertRaises(ValueError):queue(c,r,i)
   c.engine.store.save.assert_not_called()
 def test_worker_error_status_queues_recovery(self):
  c,r,i=self.fixture()
  r.task.update(status='error',error_code='stream_interrupted',error='Stream connection failed')
  with patch('cheapos.branch_worker_recovery.branch_workspace.validate_owned'):
   self.assertTrue(queue(c,r,i))
  self.assertEqual(r.task['status'],'running')
  self.assertIsNone(r.task['error'])
  self.assertEqual(r.task['route']['recovery']['worker']['from'],'worker-a')
  self.assertEqual(r.task['branch_run']['implementation_recovery']['failed_models'],['worker-a'])

class RecoveryExecutionTests(unittest.TestCase):
 setUp=fixture.BranchStartTests.setUp
 def test_stalled_author_hands_saved_file_to_distinct_worker_then_real_commit(self):
  self.engine.save_preferences({'execution':{'mode':'remote','coordinator_assistance':True,'coordinator_model':'local-helper'}})
  self.engine.config['worker']['model']='worker-a';self.engine.config['reviewer']['model']='zzz-reviewer'
  self.engine.gateway.matches=lambda _:True
  self.engine.gateway.catalog=lambda **_: {'status':'ready','models':[model(m) for m in ('worker-a','worker-b','zzz-reviewer')]}
  counters={};seen=[]
  def factory(role,config):
   def complete(messages,tools,max_tokens):
    names={t['function']['name'] for t in tools};name=config['model'];counters[name]=counters.get(name,0)+1
    if role=='coordinator':
     packet=json.loads(messages[1]['content']);self.assertTrue(packet['instruction_sources']['accepted_item']['acceptance_criteria'])
     return {'content':json.dumps({'outcome':'continue','action':'edit','next_step':'Add a focused regression for the saved work.py value.','expected_result':'A test demonstrates the accepted item behavior.','evidence':['e1']})},{'prompt_tokens':10,'completion_tokens':10,'cost':0}
    if 'routing_ready' in names:return call('routing_ready', {'marker': PROBE_MARKER}),{'prompt_tokens':2,'completion_tokens':2,'cost':0}
    if 'final_review_decision' in names:
     p=json.loads(messages[1]['content']);result={k:p[k] for k in ('manifest_id','chunk_ids','criteria_ids')};result.update(decision='APPROVE',feedback='Actual tests and complete file evidence satisfy the criteria.');return call('final_review_decision',result),{'prompt_tokens':10,'completion_tokens':10,'cost':0}
    if 'review_decision' in names:
     p=json.loads(messages[1]['content']);return call('review_decision',{'decision':'APPROVE','feedback':'Reviewed saved implementation and tests.','candidate_id':p['candidate_id'],'criteria_outcomes':{c:{'passed':True,'evidence':'Actual passing test and file'} for c in p['item']['acceptance_criteria']}}),{'prompt_tokens':10,'completion_tokens':10,'cost':0}
    if name=='worker-a':
     if counters[name]==2:result=call('write_file',{'path':'work.py','content':'value = 1\n'})
     else:result=call('read_file',{'path':'hello.py'})
    else:
     seen.append(copy.deepcopy(messages))
     if len(seen)==1:
      packet={}
      for m in messages:
       if m.get('role')=='user' and m.get('content','').startswith('{'):packet.update(json.loads(m['content']))
      self.assertIn('work.py',packet['available_files']);self.assertIn('work.py',packet['changed_files']);self.assertTrue(any('active_item' in (m.get('content') or '') for m in messages))
      result=call('write_file',{'path':'test_work.py','content':'import unittest\nimport work\nclass Check(unittest.TestCase):\n def test_value(self): self.assertEqual(work.value,1)\n'})
     else:result=call('checkpoint',{'summary':'Complete item with real regression','uncertainties':''})
    return result,{'prompt_tokens':10,'completion_tokens':10,'cost':0}
   return SimpleNamespace(complete=complete)
  self.engine.provider_factory=factory
  self.values['plan']['measurement']=True
  proposal=self.engine.branch.prepare(self.values);task=self.engine.branch.authorize(proposal['task_id'],{'proposal_id':proposal['proposal_id'],'approved':True,'full_suite_approved':True});self.launch(task['id'])
  rt=self.engine.runtimes[task['id']];rt.thread.join(60);self.assertFalse(rt.thread.is_alive())
  task=self.engine.store.get(task['id']);run=task['branch_run']
  self.assertEqual(run['status'],'ready_for_merge',task.get('error'));self.assertEqual(run['implementation_recovery']['attempts'],1)
  self.assertEqual(task['providers']['worker']['model'],'worker-b');self.assertEqual(task['providers']['reviewer']['model'],'zzz-reviewer')
  self.assertEqual(counters['local-helper'],1);self.assertEqual(task['usage']['coordinator']['tokens'],20)
  self.assertEqual(task['coordinator_recovery'][0]['state'],'applied')
  self.assertEqual(len([r for r in task['request_metrics'] if r['purpose']=='coordinator_recovery']),1)
  self.assertEqual(run['budget_ledger']['usage']['coordinator']['tokens'],20)
  self.assertEqual(len(run['completed_operations']),1);self.assertTrue(task['checks'][-1]['passed']);self.assertGreater(task['usage']['worker']['tokens'],0)
  # Even a fresh runtime cannot select the ineffective former author again.
  fresh=Runtime(task);self.engine.gateway.catalog=lambda **_: {'status':'ready','models':[model('worker-a')]}
  with self.assertRaises(RoutingPause):select_remote(self.engine,fresh,'worker',replace=True)
