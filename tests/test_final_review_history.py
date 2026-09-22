"""Historical claims cannot become fresh requirements; no Git or model calls."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import branch_final as final
from cheapos.server import LocalHandler


class HistoryTests(unittest.TestCase):
    def records(self):
        original={'id':'core:1','item_id':'core','title':'Build core','instructions':'Implement searchable snippets',
                  'criterion':'Search works','outcome':{'evidence':'old check'},'review':{'feedback':'earlier review'},
                  'check_evidence':[{'output':'old output'}]}
        repair={**original,'id':'revision-4:1','item_id':'revision-4',
                'instructions':'Historical claim: location_index has deleted scratch files'}
        return [original,repair]

    def test_only_original_requirements_are_inline_and_full_evidence_is_retained(self):
        records=self.records();before=copy.deepcopy(records)
        run=self.run_with_repair(records)
        active,history,current=final.requirement_projection(run,records)
        self.assertEqual(active,[records[0]]);self.assertEqual(history,[records[1]])
        self.assertEqual([r['id'] for r in current],['core:1'])
        text=json.dumps(current)
        for phrase in ('Historical claim','earlier review','old output','old check'):self.assertNotIn(phrase,text)
        self.assertIn('Search works',text);self.assertIn('Implement searchable snippets',text)
        self.assertEqual(records,before)
        # Reauthorization after target integration must not revive stale notes.
        run['operator_revision_history']=[{'amendments':run.pop('amendments')}]
        self.assertEqual(final.requirement_projection(run,records),(active,history,current))
        records[1]['instructions']='Operator explicitly revised this instruction'
        self.assertEqual(len(final.requirement_projection(run,records)[0]),2)

    def run_with_repair(self, records):
        repair=records[1]
        return {'amendments':[{'item':{'id':repair['item_id'],'title':repair['title'],
                'instructions':repair['instructions'],'acceptance_criteria':[repair['criterion']]}}]}

    def test_historical_finding_is_corrected_in_review_without_starting_worker_repair(self):
        from tests.test_branch_final_recovery import FinalRecoveryTests
        fixtures=FinalRecoveryTests();task,engine,runtime=fixtures.fixture();before=copy.deepcopy(task)
        records=self.records()
        active,_,_=final.requirement_projection(self.run_with_repair(records),records)
        manifest={'id':'m','requirements':active}
        bad={'decision':'REQUEST_CHANGES','manifest_id':'m','chunk_ids':['diff:1'],'criteria_ids':[],
             'feedback':'Old repair description is outdated','defects':[{'criterion':'revision-4:1','location':'vault.py:1',
             'expected':'Accurate old description','observed':'Old description differs from current index',
             'support':'Historical statement','reproduction':'','kind':'static'}]}
        engine.request.side_effect=[fixtures.call('final_review_decision',bad),fixtures.approval()]
        result=final._review(engine,runtime,manifest,{'current_candidate':'unchanged'},['diff:1'],[])
        self.assertEqual(result['decision'],'APPROVE');self.assertEqual(engine.request.call_count,2)
        self.assertEqual(task['branch_run']['items'],before['branch_run']['items'])
        self.assertNotIn('amendments',task['branch_run']);engine.checks.assert_not_called();engine.file_tool.assert_not_called()
        from cheapos.instructions.runtime import audit_tools, prompt
        self.assertIn(prompt('final_review'), engine.request.call_args.args[1][0]['content'])
        self.assertEqual(audit_tools('final_review', engine.request.call_args.args[2]), [])
        self.assertNotIn('REQUEST_TESTS', engine.request.call_args.args[1][0]['content'])
        self.assertNotIn('TAKE_OVER', engine.request.call_args.args[1][0]['content'])
        tool=engine.request.call_args.args[2][0]['function']['parameters']['properties']['defects']
        self.assertEqual(tool['items']['properties']['criterion']['enum'],['core:1'])
        self.assertEqual(final._review(engine,runtime,manifest,{'current_candidate':'unchanged'},['diff:1'],[]),result)
        self.assertEqual(engine.request.call_count,2)
        # A current source defect against an original requirement still blocks.
        task,engine,runtime=fixtures.fixture();bad['defects'][0].update(criterion='core:1',expected='Search works',observed='Search raises',support='Missing search implementation')
        engine.request.return_value=fixtures.call('final_review_decision',bad)
        self.assertEqual(final._review(engine,runtime,manifest,{'current_candidate':'broken'},['diff:1'],[])['decision'],'REQUEST_CHANGES')

    def test_existing_readiness_uses_its_saved_manifest_version(self):
        manifest={'version':1,'id':'legacy','chunks':[{'id':'requirements:1'}],
                  'requirements':[{'id':'core:1'},{'id':'revision-4:1'}]}
        candidate={'context':{},'check_specifications':[],'criteria':['core:1','revision-4:1'],'checks':[]}
        decision={'manifest_id':'legacy','chunk_ids':['requirements:1'],'decision':'APPROVE','feedback':'Reviewed'}
        ready={'manifest':manifest,'candidate':candidate,'checks':[],
               'reviews':[{**decision,'criteria_ids':[]}],
               'review':{**decision,'criteria_ids':candidate['criteria']},
               'worker_model':'worker','reviewer_model':'reviewer'}
        ready['id']=final._hash(ready)
        run={'id':'run'}
        with patch.object(final,'build_manifest',return_value=manifest) as build, patch.object(final.evidence,'candidate',return_value=candidate):
            self.assertTrue(final.validate(ready,{'branch_run':run}))
            build.assert_called_once_with(run,version=1)

    def test_token_expiry_is_typed_only_after_same_origin_validation(self):
        for headers,typed in (({'Host':'localhost:1234','X-CheapOS-Token':'old'},True),
                ({'Host':'localhost:1234','Origin':'https://other','X-CheapOS-Token':'old'},False),
                ({'Host':'localhost:1234','Sec-Fetch-Site':'cross-site','X-CheapOS-Token':'old'},False)):
            handler=SimpleNamespace(server=SimpleNamespace(server_port=1234,token='current'),headers=headers,reply=Mock())
            self.assertFalse(LocalHandler.trusted(handler,mutation=True))
            data,status=handler.reply.call_args.args
            self.assertEqual(status,403);self.assertEqual(data.get('code')=='local_token_expired',typed)
