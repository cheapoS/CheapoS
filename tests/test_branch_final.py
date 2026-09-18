import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from cheapos import branch_final as final, branch_evidence as evidence
from cheapos.verification import evidence_identity
from cheapos.workspace import git
import test_branch_commits as fixtures


class BranchFinalTests(unittest.TestCase):
    def setUp(self):
        fixtures.BranchCommitTests.setUp(self)
        self.run.update(schema_version=1, base_sha=self.run['workspace_mapping']['base_sha'],
                        feature_ref='refs/heads/feature/job', target_ref='refs/heads/main', pending_operations=[], items=[])
        self.task.update(branch_run=self.run, providers={'worker':{'model':'worker'},'reviewer':{'model':'reviewer'}}, checks=[], checks_generation=0)
        self.run['plan']['final_checks'] = [[sys.executable, '-c', 'print("final passed")']]
        self.item['instructions'] = 'Implement correct content'
        self.run['plan']['items'] = [copy.deepcopy(self.item)]
        operation = fixtures.BranchCommitTests.finish(self, fixtures.BranchCommitTests.prepare(self, 'two\n'))
        fixtures.BranchCommitTests.apply_result(self, operation)
        self.item.update(status='committed', commit_receipt=operation)
        self.run['items'] = [self.item]
        self.runtime = SimpleNamespace(task=self.task, guard=lambda: None)
        self.requests = []
        self.omit_coverage = False
        self.request_changes = False
        self.events = []
        self.engine = SimpleNamespace(store=SimpleNamespace(save=lambda task:None), event=lambda *args:self.events.append(args), checks=self.checks, request=self.request, parse_call=lambda call: (call['function']['name'], json.loads(call['function']['arguments'])))

    authorize = fixtures.BranchCommitTests.authorize
    receipt = fixtures.BranchCommitTests.receipt
    save = fixtures.BranchCommitTests.save

    def checks(self, runtime, command):
        import shlex
        argv = shlex.split(command)
        result = subprocess.run(argv, cwd=self.task['workspace'], capture_output=True, text=True)
        identity = evidence_identity({**self.task, 'check_command': argv})
        record = {'command':argv, 'passed':result.returncode == 0, 'exit_code':result.returncode,
                  'verification_identity':identity, 'input_identity':identity, 'output':result.stdout}
        self.task['checks'].append(record)
        return record

    def request(self, runtime, messages, tools, role, **kwargs):
        packet = json.loads(messages[1]['content']); self.requests.append(packet)
        result = {'decision':'REQUEST_CHANGES' if self.request_changes else 'APPROVE', 'manifest_id':packet['manifest_id'],
                  'chunk_ids':[] if self.omit_coverage else packet['chunk_ids'], 'criteria_ids':packet['criteria_ids'], 'feedback':'Read all supplied contents and checked the evidence.'}
        if self.request_changes:
            result['defects'] = [{'criterion': 'one:1', 'location': 'code:1', 'kind': 'static',
                                  'expected': 'Required content', 'observed': 'Missing edge handling',
                                  'support': 'The code path has no edge guard.', 'reproduction': ''}]
        return {'tool_calls':[{'id':'review', 'function':{'name':'final_review_decision','arguments':json.dumps(result)}}]}

    def test_cumulative_diff_clean_private_copy_and_actual_final_check(self):
        original=self.engine.request
        def request(*args,**kwargs):
            self.task['providers']['reviewer']['model']='replacement'
            return original(*args,**kwargs)
        self.engine.request=request
        result = final.final_check_review(self.engine, self.runtime)
        self.assertEqual(result['readiness']['reviewer_model'],'replacement')
        self.assertTrue(all(r['reviewer_model']=='replacement' for r in result['readiness']['reviews']))
        manifest = result['readiness']['manifest']
        from cheapos.review_context import read
        excerpt=read(self.run,manifest,{'manifest_id':manifest['id'],'path':'code','start_line':1,'end_line':10})
        self.assertEqual(excerpt['content'],'1: two')
        self.assertEqual(excerpt['candidate'],manifest['feature_tip'])
        self.assertTrue(excerpt['complete_file'])
        self.assertIn('+two', manifest['diff'])
        self.assertEqual(manifest['files'], [{'status':'M','path':'code','added_lines':1,'removed_lines':1,'item_ids':['one']}])
        self.assertEqual(result['decision'],'APPROVE')
        self.assertEqual(self.events[-1][3]['decision'],'APPROVE')
        self.assertEqual(self.task['checks'][0]['output'], 'final passed\n')
        count = len(self.requests)
        self.assertTrue(final.validate(result['readiness'], self.task))
        self.assertEqual(len(self.requests),count)
        self.assertIsNone(result['readiness']['integration_blocker'])

    def test_chunk_context_contains_bound_checks_and_still_allows_rejection(self):
        result = final.final_check_review(self.engine, self.runtime)
        ready = result['readiness']
        packets = [packet for packet in self.requests if 'chunk' in packet]
        self.assertEqual(len(packets), len(ready['manifest']['chunks']))
        for packet in packets:
            context = packet['review_context']
            from cheapos.context_evidence import read
            history=read(self.task,context['historical_evidence_reference'])
            self.assertEqual(history['kind'],'final_review_history')
            self.assertIn('original_item_evidence',history['content'])
            self.assertIn('check_evidence',history['content'])
            self.assertEqual(context['acceptance_criteria'], [
                {'id': r['id'], 'criterion': r['criterion']} for r in ready['manifest']['requirements']])
            self.assertEqual(len(context['final_checks']), len(ready['checks']))
            for summary, bound in zip(context['final_checks'], ready['checks']):
                self.assertEqual(summary, {
                    'candidate_id': ready['candidate']['id'], 'command': bound['command'],
                    'passed': True, 'exit_code': 0,
                    'verification_identity': bound['record']['verification_identity'],
                    'input_identity': bound['record']['input_identity'],
                    'record_digest': evidence._digest(bound['record'])})
                self.assertNotIn('output', summary)
        self.request_changes = True
        self.task['steer_guidance']='Reassess missing edge handling against the approved requirement.'
        self.requests.clear()
        rejected = final.final_check_review(self.engine, self.runtime)
        self.assertEqual(rejected['decision'], 'REQUEST_CHANGES')
        self.assertNotIn('readiness', rejected)
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(self.requests[0]['review_context']['final_checks'][0]['passed'])

    def test_chunk_scope_separates_background_from_synthesis_coverage(self):
        from unittest.mock import patch
        systems = []
        original = self.engine.request
        def request(runtime, messages, tools, role, **kwargs):
            systems.append(messages[0]['content'])
            return original(runtime, messages, tools, role, **kwargs)
        self.engine.request = request
        with patch.object(final, 'CHUNK_SIZE', 60):
            ready = final.final_check_review(self.engine, self.runtime)['readiness']
        packets = [packet for packet in self.requests if 'chunk' in packet]
        self.assertGreater(len(packets), 3)
        for kind in ('review_request', 'review'):
            events = [e[3] for e in self.events if e[1] == kind]
            self.assertEqual([(e['chunk_index'], e['chunk_total']) for e in events[:-1]],
                             [(i, len(packets)) for i in range(1, len(packets) + 1)])
            self.assertNotIn('chunk_index', events[-1])  # Synthesis is not another chunk.
        for index, packet in enumerate(packets, 1):
            self.assertEqual(packet['scope'], {
                'kind': packet['chunk']['kind'], 'chunk_index': index, 'chunk_total': len(packets),
                'context_role': 'global_background', 'criterion_completion_required': False})
            self.assertEqual(packet['chunk_ids'], [packet['chunk']['id']])
            self.assertEqual(packet['criteria_ids'], [])
            self.assertIn('not coverage required in this chunk', packet['instruction'])
            self.assertIn('mid-record or mid-hunk', packet['instruction'])
            self.assertIn('Do not reject solely', packet['instruction'])
            self.assertIn('Report concrete defects', packet['instruction'])
        self.assertEqual(self.requests[-1]['criteria_ids'], [r['id'] for r in ready['manifest']['requirements']])
        self.assertTrue(all('alone define the coverage' in message for message in systems))
        self.request_changes = True
        self.requests.clear()
        result = final.final_check_review(self.engine, self.runtime)
        self.assertEqual(result['decision'], 'REQUEST_CHANGES')
        self.assertNotIn('readiness', result)
        self.assertEqual(len(self.requests), 1)

    def test_oversized_context_is_rejected_without_truncation_or_request(self):
        packet = {'review_context': {'acceptance_criteria': [{'id': 'one:1', 'criterion': 'x' * 60000}]}}
        with self.assertRaisesRegex(ValueError, 'nothing was omitted'):
            final._review(self.engine, self.runtime, {'id': 'manifest'}, packet, [], [])
        self.assertEqual(self.requests, [])

    def test_overlapping_commits_and_reviewed_no_change_keep_history(self):
        for identity, text in [('two', 'three\n'), ('three', 'three\n')]:
            self.item = {'id': identity, 'title': identity, 'instructions': 'Implement correct content',
                         'required_checks': [], 'acceptance_criteria': ['correct content']}
            self.run['current_item_id'] = identity
            self.run['plan']['items'].append(copy.deepcopy(self.item))
            operation = fixtures.BranchCommitTests.finish(self, fixtures.BranchCommitTests.prepare(self, text))
            fixtures.BranchCommitTests.apply_result(self, operation)
            self.item.update(status='satisfied_without_change' if identity == 'three' else 'committed', commit_receipt=operation)
            self.run['items'].append(self.item)
        manifest = final.build_manifest(self.run)
        self.assertIn('+three', manifest['diff'])
        self.assertNotIn('+two', manifest['diff'])
        self.assertEqual(len(manifest['commits']), 3)
        self.assertEqual(manifest['commits'][-1]['old_tip'], manifest['commits'][-1]['new_tip'])
        self.assertEqual([r['id'] for r in manifest['requirements']], ['one:1', 'two:1', 'three:1'])
        # Existing approvals must retain the legacy serialized packet identity.
        legacy=final.build_manifest(self.run,version=1)
        self.assertNotIn('repair_evidence',legacy)
        self.assertEqual(''.join(c['content'] for c in legacy['chunks'] if c['kind']=='requirements'),final._json(legacy['requirements']))
        fields=dict(legacy);identity=fields.pop('id')
        self.assertEqual(identity,final._hash(fields))

    def test_missing_coverage_or_review_revision_never_ready(self):
        self.omit_coverage = True
        with self.assertRaisesRegex(ValueError,'coverage'): final.final_check_review(self.engine,self.runtime)
        self.assertEqual(len(self.requests),3)
        with self.assertRaisesRegex(ValueError,'coverage'): final.final_check_review(self.engine,self.runtime)
        self.assertEqual(len(self.requests),3)
        self.run.pop('final_review_corrections',None)  # A separate review scenario.
        self.omit_coverage = False; self.request_changes = True
        result=final.final_check_review(self.engine,self.runtime)
        self.assertEqual(result['decision'],'REQUEST_CHANGES')
        self.assertNotIn('readiness',result)

    def test_invalid_final_coverage_gets_specific_feedback_and_can_be_repaired(self):
        original=self.engine.request;seen=[]
        def request(runtime,messages,tools,role,**kwargs):
            if not seen:
                self.omit_coverage=True
            else:
                self.omit_coverage=False
                if len(seen)==1:
                    feedback=json.loads(messages[-1]['content'])
                    self.assertIn('chunk_ids',feedback['error'])
                    self.assertEqual(messages[-1]['tool_call_id'],'review')
            seen.append(1)
            return original(runtime,messages,tools,role,**kwargs)
        self.engine.request=request
        result=final.final_check_review(self.engine,self.runtime)
        self.assertEqual(result['decision'],'APPROVE')
        self.assertTrue(final.validate(result['readiness'],self.task))
        self.assertEqual(sum(self.run['final_review_corrections'].values()),1)

    def test_multichunk_exhaustive_content_and_digest(self):
        # A small chunk ceiling exercises the same deterministic splitting path.
        from unittest.mock import patch
        with patch.object(final,'CHUNK_SIZE',60):
            manifest=final.build_manifest(self.run)
            self.assertGreater(len(manifest['chunks']),3)
            self.assertEqual(''.join(c['content'] for c in manifest['chunks'] if c['kind']=='diff'),manifest['diff'])
            current=json.loads(''.join(c['content'] for c in manifest['chunks'] if c['kind']=='requirements'))
            self.assertEqual([r['id'] for r in current],['one:1'])
            self.assertNotIn('review',current[0])
            self.assertIn('review',manifest['requirements'][0])
            result=final.final_check_review(self.engine,self.runtime)
            self.assertEqual(len(result['readiness']['reviews']),len(manifest['chunks']))
            self.assertEqual(result['readiness']['review']['criteria_ids'],['one:1'])

    def test_stale_target_feature_environment_and_pending_refused(self):
        ready=final.final_check_review(self.engine,self.runtime)['readiness']
        (Path(self.task['workspace'])/'setup.cfg').write_text('[changed]\n')
        with self.assertRaises(ValueError): final.validate(ready,self.task)
        (Path(self.task['workspace'])/'setup.cfg').unlink()
        self.run['pending_operations']=[{'id':'pending'}]
        with self.assertRaises(ValueError): final.build_manifest(self.run)
        self.run['pending_operations']=[]
        (self.source/'code').write_text('target change\n');git(self.source,'add','code');git(self.source,'commit','-qm','external target')
        with self.assertRaisesRegex(ValueError,'changed'): final.validate(ready,self.task)
        self.assertIsNotNone(final.final_check_review(self.engine,self.runtime)['readiness']['integration_blocker'])
        git(self.source,'update-ref',self.run['feature_ref'],git(self.source,'rev-parse','HEAD').strip())
        with self.assertRaises(ValueError): final.build_manifest(self.run)

    def test_failure_does_not_create_readiness(self):
        self.run['plan']['final_checks']=[[sys.executable,'-c','raise SystemExit(1)']]
        result=final.final_check_review(self.engine,self.runtime)
        self.assertEqual(result['decision'],'REQUEST_CHANGES')
        self.assertNotIn('readiness',result)
        self.assertEqual(self.requests,[])


if __name__ == '__main__': unittest.main()
