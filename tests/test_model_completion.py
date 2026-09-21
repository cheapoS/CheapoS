"""Tiny synthetic immutable receipts; no Git, Engine, HTTP or inference."""
import copy
import tempfile
import unittest
from unittest.mock import patch
from cheapos.model_pool import FreeModelPool, observe_completions
from cheapos import branch_evidence as ev

URL='http://localhost:1234/v1'


def saved_task():
    current={'version':1,'context':{'run_id':'run','item_id':'item','feature_parent':'a'*40},'criteria':['works'],
             'checks':[{'command':['python3','-V'],'verification_identity':'current'}],'patch':'change'}
    current['id']=ev._digest(current)
    record={'command':['python3','-V'],'passed':True,'exit_code':0,'verification_identity':'current','input_identity':'current'}
    checks=[ev.bind_check(current,record['command'],record)]
    receipt=ev.ready_receipt(current,checks,{'candidate_id':current['id'],'decision':'APPROVE','feedback':'yes'},'worker','reviewer',{'works':{'passed':True,'evidence':'check'}})
    item={'id':'item','status':'committed','acceptance_criteria':['works'],'required_checks':['python3 -V'],
          'commit_receipt':{'stage':'completed','run_id':'run','item_id':'item','candidate_id':current['id'],'receipt':receipt,'outcome':'ready','old_tip':'a'*40,'new_tip':'b'*40}}
    task={'id':'task','branch_run':{'id':'run','items':[item]},'request_metrics':[]}
    for role in ('worker','reviewer'):
        task['request_metrics'].append({'dispatched':True,'role':role,'model':role,'branch_item_id':'item',
          'dispatch_scope':{'base_url':URL,'connection_revision':'revision','model':role,'role':role}})
    return task


class CompletionTests(unittest.TestCase):
    def test_receipt_scope_restart_idempotence_and_invalidation(self):
        with tempfile.TemporaryDirectory() as root:
            pool=FreeModelPool(root);task=saved_task();observe_completions(pool,task)
            pool=FreeModelPool(root);observe_completions(pool,task)
            def evidence(revision='revision'):return pool.observation(URL,'worker',revision)['role_evidence']['worker']
            self.assertEqual(evidence()['completed'],1);self.assertEqual(evidence('other')['completed'],0)
            self.assertEqual(evidence(None)['completed'],0)
            receipt=__import__('json').loads(task['branch_run']['items'][0]['commit_receipt']['receipt'])['id']
            pool.adjudicate_completion(URL,'worker','worker',receipt,'a'*64,False,'revision')
            pool.adjudicate_completion(URL,'worker','worker',receipt,'a'*64,False,'revision')
            observe_completions(pool,task)
            self.assertEqual((evidence()['completed'],evidence()['independently_disproved']),(0,1))
            pool.adjudicate_completion(URL,'worker','worker',receipt,'b'*64,True,'revision')
            self.assertEqual(evidence()['completed'],0)
            with self.assertRaises(ValueError):pool.adjudicate_completion(URL,'worker','worker','invented','a'*64,True,'revision')
            pool.mark_integrated('task','run');pool.mark_integrated('task','run')
            self.assertEqual(evidence()['human_integrated'],1)
            self.assertEqual(pool.observation(URL,'reviewer','revision')['role_evidence']['reviewer']['completed'],1)

    def test_stale_checks_mismatch_historical_and_ambiguous_scope_rejected(self):
        for mutation in ('stage','run','checks','scope','ambiguous','parent','tip','length'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as root:
                task=saved_task();op=task['branch_run']['items'][0]['commit_receipt']
                if mutation=='stage':op['stage']='prepared'
                if mutation=='parent':op['old_tip']='c'*40
                if mutation=='tip':op['new_tip']='invalid'
                if mutation=='length':op['new_tip']='b'*41
                if mutation=='run':op['run_id']='wrong'
                if mutation=='checks':task['branch_run']['items'][0]['required_checks']=['python3 missing.py']
                if mutation=='scope':task['request_metrics']=[]
                if mutation=='ambiguous':
                    duplicate=copy.deepcopy(task['request_metrics'][0]);duplicate['dispatch_scope']['connection_revision']='another';task['request_metrics'].append(duplicate)
                pool=FreeModelPool(root);observe_completions(pool,task)
                self.assertEqual(pool.observation(URL,'worker','revision')['role_evidence']['worker']['completed'],0)

    def test_completion_beats_fast_envelopes_but_pin_and_scope_win(self):
        with tempfile.TemporaryDirectory() as root:
            pool=FreeModelPool(root);observe_completions(pool,saved_task())
            for i in range(3):pool.record_outcome(URL,'fast','worker',str(i),'other',{'checkpoints':1,'invalid_output':1},'revision')
            pool.record(URL,'fast','worker',seconds=.001)
            # A high catalog score cannot outrank recorded completion evidence.
            models = {'worker': {'id':'worker'}, 'fast': {'id':'fast', 'benchmarks': {
                'source':'Artificial Analysis', 'coding':99}}}
            rank=lambda model,pin=None,revision='revision':pool.rank(URL,models[model],'worker',pin,revision)
            self.assertLess(rank('worker'),rank('fast'))
            self.assertLess(rank('fast','fast'),rank('worker','fast'))
            self.assertEqual(pool.observation(URL,'worker','missing')['role_evidence']['worker']['completion_samples'],0)

    def test_reread_preserves_acceptance_and_timestamp(self):
        with tempfile.TemporaryDirectory() as root,patch('cheapos.model_pool.time.time',return_value=1000):
            pool=FreeModelPool(root);pool.record_outcome(URL,'worker','worker','r','task',{'checkpoints':1})
            pool.record_acceptance(URL,'worker','worker','task','r')
            with patch('cheapos.model_pool.time.time',return_value=2000):pool.record_outcome(URL,'worker','worker','r','task',{'checkpoints':1})
            e=pool.observation(URL,'worker')['role_evidence']['worker']
            self.assertEqual((e['accepted'],e['samples'],e['last_observed']),(1,1,1000))

    def test_connection_revision_isolates_cooldowns_and_compatibility(self):
        from cheapos.providers import ProviderError
        with tempfile.TemporaryDirectory() as root:
            pool=FreeModelPool(root)
            pool.record(URL,'worker','worker',probe=True,connection_revision='old')
            pool.record(URL,'worker','worker',error=ProviderError('quota',code='gateway_cooldown',scope='provider'),connection_revision='old')
            self.assertTrue(pool.observation(URL,'worker','old')['cooling_down'])
            for revision in (None,'new'):
                current=pool.observation(URL,'worker',revision)
                self.assertFalse(current['cooling_down']);self.assertFalse(current.get('tool_check_passed',False))
