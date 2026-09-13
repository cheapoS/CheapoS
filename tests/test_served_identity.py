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
