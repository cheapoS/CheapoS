"""Bounded smaller-action recovery, without executing truncated responses."""
import copy
import io
import json
import sys
from unittest.mock import Mock, patch

from cheapos.engine import OUTPUT_GUIDANCE
from cheapos.providers import ChatProvider, ProviderError
from cheapos.routing import PROBE_MESSAGES
from test_engine import LocalCase, call
import test_routing as routing_fixture
from test_routing import model


class OutputRecoveryTests(LocalCase):
    chat = routing_fixture.RoutingTests.chat

    def responses(self, replies):
        self.engine.gateway.catalog.return_value['models'] = [
            model(n, recovery_reasoning={'enabled': False}) for n in ('a', 'b', 'c', 'd')]
        queue = iter(replies)
        requests = []
        class Provider:
            def __init__(self, role, config): self.role, self.config = role, config
            def complete(self, messages, tools, maximum):
                if messages == PROBE_MESSAGES:
                    return call('routing_ready'), {'prompt_tokens': 3, 'completion_tokens': 1, 'cost': 0}
                requests.append({'model': self.config['model'], 'role': self.role, 'config': copy.deepcopy(self.config),
                                 'messages': copy.deepcopy(messages), 'maximum': maximum})
                reply = next(queue)
                if isinstance(reply, Exception): raise reply
                return reply, {'prompt_tokens': 10, 'completion_tokens': 5, 'cost': 0}
        self.engine.provider_factory = lambda role, config: Provider(role, config)
        return requests

    def limited(self, usage=None):
        return ProviderError('Output cap', code='output_limit', usage=usage)

    def test_retries_once_with_smaller_action_and_unchanged_limits_then_finishes_review(self):
        task = self.chat('remote')
        task.update(check_command=[sys.executable, '-m', 'unittest', 'discover', '-v'], auto_approve_checks=True)
        self.engine.store.save(task)
        edit = call('replace_text', {'path': 'math_utils.py', 'old_text': 'return min(value, upper)',
                                     'new_text': 'return max(lower, min(value, upper))'})
        requests = self.responses([self.limited({'prompt_tokens': 20, 'completion_tokens': 100, 'cost': 0}), edit,
                                  call('checkpoint', {'summary': 'Fixed clamp', 'uncertainties': ''}),
                                  call('review_decision', {'decision': 'APPROVE', 'feedback': 'Checks passed.'})])
        self.engine.start(task['id']); result = self.finish(task)
        self.assertEqual(result['status'], 'approved', result['error'])
        self.assertEqual([r['model'] for r in requests], ['a', 'a', 'a', 'b'])
        self.assertNotIn('_recovery_reasoning', requests[0]['config'])
        self.assertEqual(requests[1]['config']['_recovery_reasoning'], {'enabled': False})
        self.assertEqual(requests[1]['messages'][-1]['content'], OUTPUT_GUIDANCE)
        self.assertNotIn('_recovery_reasoning', requests[-1]['config'])
        self.assertEqual(result['request_worker_turns'], 3)
        self.assertEqual(result['usage']['uncertain_requests'], 0)
        self.assertEqual(result['limits'], task['limits'])
        self.assertTrue(all(r['maximum'] == task['limits']['output_tokens'] for r in requests if r['role'] == 'worker'))
        self.assertEqual(len(result['checks']), 1)
        self.assertFalse(result.get('commit_result'))

    def test_repeated_cap_switches_model_but_handoffs_are_bounded(self):
        task = self.chat('remote'); requests = self.responses([self.limited() for _ in range(6)])
        self.engine.start(task['id']); result = self.finish(task)
        self.assertEqual(result['status'], 'paused', result['error'])
        self.assertEqual(result['error_code'], 'routing_unavailable')
        self.assertEqual([r['model'] for r in requests], ['a', 'a', 'b', 'b', 'c', 'c'])
        self.assertEqual(result['request_worker_turns'], 6)
        self.assertEqual(result['usage']['uncertain_requests'], 6)
        self.assertEqual(result['limits'], task['limits'])
        self.assertFalse(result['changes'])

    def test_saved_output_limit_gets_different_retry_without_raising_cap(self):
        task = self.chat('remote'); self.responses([{'content': 'Ready.'}])
        self.engine.start(task['id']); task = self.finish(task)
        task.update(status='error', error_code='output_limit', error='Previous output cap')
        self.engine.store.save(task)
        requests = self.responses([self.limited(), {'content': 'Recovered.'}])
        self.engine.start(task['id']); result = self.finish(task)
        self.assertEqual(result['status'], 'awaiting_reply', result['error'])
        self.assertEqual([r['model'] for r in requests], ['a', 'b'])
        self.assertEqual(requests[0]['messages'][-1]['content'], OUTPUT_GUIDANCE)
        self.assertEqual(result['limits'], task['limits'])

    def test_worker_and_checkpoint_limits_stop_before_extra_request(self):
        for cap in ('worker_turns', 'checkpoint_turns'):
            task = self.chat('remote'); task['limits'][cap] = 1 if cap == 'worker_turns' else 2
            self.engine.store.save(task)
            requests = self.responses([self.limited(), self.limited()])
            self.engine.start(task['id']); result = self.finish(task)
            self.assertEqual(len(requests), task['limits'][cap])
            self.assertIn(result['status'], {'paused', 'budget_paused'})

    def test_reported_charge_or_incomplete_usage_stops_before_retry(self):
        for usage in ({'prompt_tokens': 20, 'completion_tokens': 100, 'cost': .01}, {'cost': .01}, {'prompt_tokens': 20}):
            task = self.chat('remote'); requests = self.responses([self.limited(usage)])
            self.engine.start(task['id']); result = self.finish(task)
            self.assertEqual(result['status'], 'budget_paused', result['error'])
            self.assertEqual(len(requests), 1)
            if usage.get('cost'):
                self.assertGreaterEqual(result['usage']['cost'], .01)

    def test_manual_local_and_reviewer_limits_still_pause(self):
        for mode in ('manual', 'local'):
            task = self.fixture(paid=True); task['execution'] = {'mode': mode}
            self.engine.store.save(task)
            provider = Mock(); provider.complete.side_effect = self.limited()
            self.engine.provider_factory = lambda *args: provider
            self.engine.start(task['id']); result = self.finish(task)
            self.assertEqual(result['error_code'], 'output_limit', result['error'])
            self.assertEqual(provider.complete.call_count, 1)
        task = self.chat('remote')
        task.update(check_command=[sys.executable, '-m', 'unittest', 'discover', '-v'], auto_approve_checks=True)
        self.engine.store.save(task)
        requests = self.responses([call('replace_text', {'path': 'math_utils.py', 'old_text': 'return min(value, upper)',
                                                       'new_text': 'return max(lower, min(value, upper))'}),
                                  call('checkpoint', {'summary': 'Ready', 'uncertainties': ''}), self.limited()])
        self.engine.start(task['id']); result = self.finish(task)
        self.assertEqual(result['error_code'], 'output_limit', result['error'])
        self.assertEqual([r['role'] for r in requests], ['worker', 'worker', 'reviewer'])

    def test_nonstreamed_length_never_returns_even_a_complete_looking_tool(self):
        usage = {'prompt_tokens': 10, 'completion_tokens': 100, 'cost': 0}
        response = io.BytesIO(json.dumps({'choices': [{'finish_reason': 'length', 'message': call('write_file',
            {'path': 'unsafe.py', 'content': 'x'})}], 'usage': usage}).encode())
        provider = ChatProvider({'base_url': 'http://localhost:1234/v1', 'model': 'fixture', 'key_env': 'CHEAPOS_TEST_KEY',
                                 '_recovery_reasoning': {'enabled': False}})
        with patch('cheapos.providers.build_opener') as opener:
            opener.return_value.open.return_value = response
            with self.assertRaises(ProviderError) as caught:
                provider.complete([], [], 4096)
            sent = json.loads(opener.return_value.open.call_args.args[0].data)
        self.assertEqual(caught.exception.code, 'output_limit')
        self.assertEqual(caught.exception.usage, usage)
        self.assertEqual(sent['reasoning'], {'enabled': False})
        self.assertEqual(sent['max_tokens'], 4096)
