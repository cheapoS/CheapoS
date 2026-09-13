import copy
from unittest.mock import Mock
from cheapos import progress
from cheapos.engine import Engine
from test_engine import LocalCase, call
import test_chat


class ProgressRecoveryTests(LocalCase):
    chat = test_chat.ChatTests.chat
    provider = test_chat.ChatTests.provider

    def test_progress_ignores_cycles_reads_and_cosmetic_messages(self):
        task = {'patch':'', 'checks':[], 'requests':['Do work'], 'status':'running'}
        self.assertFalse(progress.observe(task))
        task['patch'] = 'first'
        self.assertTrue(progress.observe(task))
        task['patch'] = ''
        self.assertFalse(progress.observe(task))
        task['patch'] = 'first'
        task['events'] = [{'kind':'assistant','detail':'I made progress'}]
        self.assertFalse(progress.observe(task))
        task['checks'] = [{'command':['test'],'digest':'first','passed':False,'outcome':'test_failure','output':'assertion'}]
        self.assertTrue(progress.observe(task))
        task['checks'][-1]['duration'] = 999
        task['checks'][-1]['run_id'] = 'new-run'
        self.assertFalse(progress.observe(task))
        task['checks'][-1].update(passed=True,outcome='passed',output='OK')
        self.assertTrue(progress.observe(task))
        revision = progress.state(task)['revision']
        restored = copy.deepcopy(task)
        self.assertFalse(progress.observe(restored))
        self.assertEqual(progress.state(restored)['revision'], revision)

    def test_exhausted_answer_requires_changed_input_after_restart(self):
        task = self.chat('Explain this repository')
        requests = self.provider([call('read_file', {'path':'math_utils.py'})] * 4)
        self.engine.start(task['id']); stopped = self.finish(task)
        self.assertEqual(stopped['status'], 'paused')
        self.assertIn('answer from gathered evidence', stopped['pause_summary']['attempted'])
        self.assertEqual(len(requests), 4)
        usage = copy.deepcopy(stopped['usage'])
        self.engine.shutdown(); self.engine = Engine(self.engine.store.root, fixture_delay=0)
        factory = Mock(); self.engine.provider_factory = factory
        for _ in range(3):
            with self.assertRaisesRegex(ValueError, 'specific correction'):
                self.engine.start(task['id'])
        factory.assert_not_called()
        self.assertEqual(self.engine.store.get(task['id'])['usage'], usage)
        requests = self.provider([{'content':'clamp returns the bounded value.'}])
        self.engine.start(task['id'], {'message':'Use the evidence already read. Explain clamp in one sentence.'})
        result = self.finish(task)
        self.assertEqual(result['status'], 'awaiting_reply')
        self.assertEqual(len(requests), 1)
        self.assertGreater(result['usage']['worker']['tokens'], usage['worker']['tokens'])
        self.assertEqual(progress.state(result)['answer_attempts'], 0)

    def test_new_request_resets_recovery_only_not_usage_or_turn_history(self):
        task = self.chat()
        state = progress.state(task)
        state.update(handoffs=2, malformed_attempts=3, answer_attempts=2)
        task['worker_turns'] = 9
        task['usage']['cost'] = .2
        task['requests'].append('Clarified scope')
        self.assertEqual(progress.state(task)['handoffs'], 0)
        self.assertEqual(task['worker_turns'], 9)
        self.assertEqual(task['usage']['cost'], .2)

    def test_pending_manual_review_keeps_its_call_bound_on_resume(self):
        task = self.fixture(paid=True)
        responses = [call('replace_text', {'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}), call('checkpoint', {'summary':'Fix bounds','uncertainties':''})]
        responses += [{'content':'Still assessing.'}] * 8
        provider = Mock()
        provider.complete.side_effect = [(message, {'prompt_tokens':10,'completion_tokens':5,'cost':0}) for message in responses]
        self.engine.provider_factory = lambda *args: provider
        self.engine.start(task['id']); stopped = self.finish(task)
        self.assertEqual(stopped['status'], 'budget_paused', stopped['error'])
        self.assertEqual(stopped['pending_review']['review_requests'], 8)
        checks = copy.deepcopy(stopped['checks'])
        self.engine.start(task['id']); resumed = self.finish(task)
        self.assertEqual(resumed['status'], 'budget_paused')
        self.assertEqual(provider.complete.call_count, 10)
        self.assertEqual(resumed['checks'], checks)
        self.assertEqual(resumed['iterations'], 1)
