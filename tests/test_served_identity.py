import io
import json
import unittest
from cheapos.served_identity import metadata, apply, ensure_independent
from cheapos.providers import ProviderError
from cheapos.streaming import read_chat_stream


class IdentityTests(unittest.TestCase):
    def test_requested_reported_unknown_and_allowlist(self):
        result=metadata('gateway/alias','real/model')
        self.assertEqual((result['requested_model'],result['served_model'],result['identity_provenance']),('gateway/alias','real/model','response_model'))
        self.assertIsNone(result['gateway_internal_attempts'])
        for value in (None,'person@example.invalid','https://account.invalid/key','sk-secret','line\nsecret','x'*161,'auto/router'):
            self.assertEqual(metadata('named/model',value)['identity_provenance'],'unknown')
        record={'model':'named/model'};usage={'prompt_tokens':2,'_served_identity':result,'raw_header':'not consumed'}
        apply(record,usage)
        self.assertNotIn('raw_header',record);self.assertNotIn('_served_identity',usage)
        self.assertEqual(record['served_model'],'real/model')

    def test_same_served_aliases_and_opaque_unknown_are_not_independent(self):
        worker={'role':'worker','dispatched':True,'purpose':'work',**metadata('alias/a','real/model')}
        task={'served_identity_version':1,'request_metrics':[worker]}
        review={'role':'reviewer',**metadata('alias/b','real/model')}
        with self.assertRaisesRegex(ProviderError,'same'):ensure_independent(task,review)
        with self.assertRaisesRegex(ProviderError,'opaque'):ensure_independent(task,{'role':'reviewer',**metadata('auto/choice')})
        ensure_independent(task,{'role':'reviewer',**metadata('other/named')})
        ensure_independent({},review)  # Historical policy unchanged.
        ensure_independent(task,{**review,'purpose':'probe'})
        manual={'served_identity_version':1,'request_metrics':[{'role':'worker','dispatched':True,**metadata('same/named')}]}
        unknown_review={'role':'reviewer',**metadata('same/named')}
        ensure_independent(manual,unknown_review)
        with self.assertRaises(ProviderError):ensure_independent({**manual,'branch_run':{'id':'run'}},unknown_review)

    def test_stream_reports_model_only_when_consistent(self):
        def stream(models):
            frames=[{'model':m,'choices':[{'delta':{'content':'ok'}}]} for m in models]
            frames.append({'choices':[{'delta':{},'finish_reason':'stop'}]})
            data=''.join('data: '+json.dumps(f)+'\n\n' for f in frames)+'data: [DONE]\n\n'
            return read_chat_stream(io.BytesIO(data.encode()),lambda *a:None,lambda:False,ProviderError)
        self.assertEqual(stream(['real/model','real/model'])['model'],'real/model')
        self.assertIsNone(stream(['real/a','real/b'])['model'])
        self.assertIsNone(stream(['https://private.invalid'])['model'])

    def test_json_adapter_captures_only_response_model(self):
        from unittest.mock import Mock, patch
        from cheapos.providers import ChatProvider
        data={'model':'served/model','private_header':'not retained',
              'choices':[{'message':{'content':'ok'}}], 'usage':{'prompt_tokens':1,'completion_tokens':1}}
        response=io.BytesIO(json.dumps(data).encode())
        opener=Mock();opener.open.return_value=response
        provider=ChatProvider({'base_url':'http://127.0.0.1:1/v1','model':'requested/model','key_env':'UNUSED_FIXTURE_KEY'})
        with patch('cheapos.providers.build_opener',return_value=opener):
            message,usage=provider.complete([],[],10)
        self.assertEqual(usage['_served_identity']['served_model'],'served/model')
        self.assertNotIn('private_header',str(usage))
        self.assertEqual(message['content'],'ok')

class RevisionIdentityTests(unittest.TestCase):
    def task(self):
        return {'served_identity_version':1,'branch_run':{'expected_feature_tip':'commit','items':[
            {'id':'fix','status':'committed','commit_receipt':{'stage':'completed','new_tip':'commit'}},
            {'id':'verify','revision_of':'fix','status':'reviewing'}]},
            'pending_review':{'identity_scope':{'candidate_id':'candidate','item_id':'verify','no_change':True,'feature_parent':'commit'}},
            'request_metrics':[
                {'id':'author','role':'worker','dispatched':True,'branch_item_id':'fix',**metadata('named/author')},
                {'id':'old-inspection','role':'worker','dispatched':True,'branch_item_id':'verify',**metadata('auto/coding')},
                {'id':'current','role':'worker','dispatched':True,'branch_item_id':'verify',**metadata('named/worker')}]}

    def test_unchanged_revision_ignores_superseded_inspection_but_preserves_authors(self):
        task=self.task();review={'role':'reviewer','review_candidate_id':'candidate',**metadata('named/reviewer')}
        ensure_independent(task,review)
        self.assertEqual(review['identity_scope']['excluded_inspection_requests'],['old-inspection'])
        for model in ('named/author','named/worker'):
            with self.assertRaises(ProviderError):ensure_independent(task,{**review,**metadata(model)})
        self.assertEqual(len(task['request_metrics']),3)

    def test_changed_stale_and_unknown_authorship_remain_blocked(self):
        review={'role':'reviewer','review_candidate_id':'candidate',**metadata('named/reviewer')}
        for field,value in (('no_change',False),('candidate_id','stale'),('feature_parent','other')):
            task=self.task();task['pending_review']['identity_scope'][field]=value
            with self.assertRaises(ProviderError):ensure_independent(task,dict(review))
        task=self.task();task['request_metrics'][0].update(metadata('auto/author'))
        with self.assertRaises(ProviderError):ensure_independent(task,review)

    def test_final_review_retains_completed_no_change_provenance(self):
        task=self.task();item=task['branch_run']['items'][1]
        item.update(status='satisfied_without_change',evidence={'no_change':True},commit_receipt={'stage':'completed','new_tip':'commit'})
        review={'role':'reviewer','purpose':'branch_final',**metadata('named/reviewer')}
        ensure_independent(task,review)
        self.assertIn('identity_scope',review)
