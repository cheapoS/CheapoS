"""In-memory final-review batches; no repository setup, inference or waits."""
import copy
import json
import unittest
from unittest.mock import patch

from cheapos import branch_final as final
from cheapos.engine import Engine
from tests import test_branch_final_recovery as fixtures
from tests.test_review_assessment import assessment


def call(name, args, identity):
    return {'id': identity, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}


def batch(*calls):
    return {'role': 'assistant', 'content': None, 'reasoning_details': [{'data': 'opaque'}], 'tool_calls': list(calls)}


class FinalReadBatchTests(unittest.TestCase):
    def fixture(self):
        f = fixtures.FinalRecoveryTests()
        task, engine, runtime = f.fixture()
        engine.parse_call = Engine.parse_call
        return f, task, engine, runtime

    def approval(self, f):
        return batch(call('final_review_decision', f.approval()['tool_calls'][0]['result'], 'decision'))

    def readers(self):
        return batch(*(call('read_final_context', {'manifest_id': 'm', 'path': path, 'start_line': 1}, path)
                       for path in ('one.py', 'two.py')))

    def excerpt(self, run, manifest, args):
        return {'path': args['path'], 'available': True, 'start_line': 1, 'end_line': 1, 'content': '1: exact source'}

    def test_read_batch_reaches_separate_validated_approval_and_preserves_pairing(self):
        f, task, engine, runtime = self.fixture(); task['review_contract_version'] = 1
        before = copy.deepcopy(task); request = self.readers(); seen = []
        def respond(rt, messages, tools, role, **kwargs):
            seen.append(copy.deepcopy(messages))
            if len(seen) == 1:
                return request
            self.assertEqual(messages[-3], request)
            self.assertEqual([m['tool_call_id'] for m in messages[-2:]], ['one.py', 'two.py'])
            sources = [json.loads(m['content'])['evidence_id'] for m in messages[-2:]]
            reply = f.approval()['tool_calls'][0]['result']
            reply['review_assessment'] = assessment(['packet'], source=sources[0], quote='exact source', checks=False)
            return batch(call('final_review_decision', reply, 'decision'))
        engine.request.side_effect = respond
        with patch.object(final.review_context, 'read', side_effect=self.excerpt) as read:
            result = f.review(engine, runtime)
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual((read.call_count, len(seen)), (2, 2))
        self.assertEqual(task['branch_run']['final_review_corrections'], {})
        self.assertEqual(len(result['_review_evidence']['excerpts']), 1)
        for key in ('checks', 'usage', 'limits', 'providers'): self.assertEqual(task[key], before[key])
        engine.checks.assert_not_called(); engine.file_tool.assert_not_called()

    def test_cancelled_batch_resumes_remaining_read_without_replaying_completed_read(self):
        f, task, engine, runtime = self.fixture(); request = self.readers()
        engine.request.side_effect = [request, self.approval(f)]
        paths = []
        def read(run, manifest, args):
            paths.append(args['path'])
            if paths == ['one.py', 'two.py']:
                raise InterruptedError('Pause during second read')
            return self.excerpt(run, manifest, args)
        with patch.object(final.review_context, 'read', side_effect=read):
            with self.assertRaises(InterruptedError): f.review(engine, runtime)
            state = next(iter(task['branch_run']['final_review_packets'].values()))
            self.assertNotIn('result', state)
            self.assertEqual(len(state['pending_read_batch']['results']), 1)
            self.assertFalse(any(c.args[1] == 'review' for c in engine.event.call_args_list))
            runtime.task = json.loads(json.dumps(task))
            result = f.review(engine, runtime)
        self.assertEqual(result['decision'], 'APPROVE')
        self.assertEqual(paths, ['one.py', 'two.py', 'two.py'])
        self.assertEqual(engine.request.call_count, 2)
        self.assertNotIn('pending_read_batch', next(iter(runtime.task['branch_run']['final_review_packets'].values())))

    def test_decision_mixed_with_reads_or_unoffered_tool_cannot_execute_or_approve(self):
        for extra in ('final_review_decision', 'write_file'):
            with self.subTest(extra=extra):
                f, task, engine, runtime = self.fixture()
                args = f.approval()['tool_calls'][0]['result'] if extra == 'final_review_decision' else {'path': 'example.py', 'content': 'not allowed'}
                mixed = self.readers(); mixed['tool_calls'].append(call(extra, args, 'unsafe'))
                engine.request.side_effect = [mixed, InterruptedError('observe correction')]
                with patch.object(final.review_context, 'read') as read:
                    with self.assertRaises(InterruptedError): f.review(engine, runtime)
                read.assert_not_called(); engine.file_tool.assert_not_called()
                state = next(iter(task['branch_run']['final_review_packets'].values()))
                self.assertNotIn('result', state)
                self.assertNotIn('pending_read_batch', state)
                self.assertIn('mixed batch cannot approve', json.dumps(state['messages']))

    def test_invalid_arguments_and_duplicate_ids_reject_whole_batch_before_reads(self):
        for failure in ('arguments', 'duplicate'):
            with self.subTest(failure=failure):
                f, task, engine, runtime = self.fixture(); request = self.readers()
                if failure == 'arguments': request['tool_calls'][1]['function']['arguments'] = '{bad'
                else: request['tool_calls'][1]['id'] = request['tool_calls'][0]['id']
                engine.request.side_effect = [request, InterruptedError('observe correction')]
                with patch.object(final.review_context, 'read') as read:
                    with self.assertRaises(InterruptedError): f.review(engine, runtime)
                read.assert_not_called()
                self.assertNotIn('result', next(iter(task['branch_run']['final_review_packets'].values())))
                if failure == 'duplicate':
                    self.assertFalse(any(m.get('tool_calls') for m in engine.request.call_args.args[1]))

    def test_failed_read_keeps_other_results_without_turning_error_into_evidence(self):
        f, task, engine, runtime = self.fixture(); engine.request.side_effect = [self.readers(), InterruptedError('inspect results')]
        def read(run, manifest, args):
            if args['path'] == 'one.py': raise ValueError('Missing candidate file')
            return self.excerpt(run, manifest, args)
        with patch.object(final.review_context, 'read', side_effect=read):
            with self.assertRaises(InterruptedError): f.review(engine, runtime)
        sent = engine.request.call_args.args[1]
        self.assertEqual(json.loads(sent[-2]['content'])['error'], 'Missing candidate file')
        self.assertEqual(json.loads(sent[-1]['content'])['path'], 'two.py')
        state = next(iter(task['branch_run']['final_review_packets'].values()))
        self.assertNotIn('result', state)
        self.assertEqual(next(iter(task['branch_run']['final_review_corrections'].values())), 1)

    def test_new_direction_invalidates_pending_batch_without_executing_old_reads(self):
        f, task, engine, runtime = self.fixture(); engine.request.return_value = self.readers()
        with patch.object(final.review_context, 'read', side_effect=InterruptedError('paused')):
            with self.assertRaises(InterruptedError): f.review(engine, runtime)
        runtime.task = json.loads(json.dumps(task))
        runtime.task['steer_guidance'] = 'Review the revised operator requirement.'
        engine.request.return_value = self.approval(f)
        with patch.object(final.review_context, 'read') as read:
            result = f.review(engine, runtime)
        self.assertEqual(result['decision'], 'APPROVE'); read.assert_not_called()
        run = runtime.task['branch_run']
        self.assertIn('pending_read_batch', run['final_review_packet_history'][-1])
        self.assertNotIn('pending_read_batch', next(iter(run['final_review_packets'].values())))
