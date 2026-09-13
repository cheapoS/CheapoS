from unittest.mock import Mock
from cheapos.engine import Runtime, ProgressPause, WorkerTurnLimit
from cheapos.workspace import Workspace
from test_engine import LocalCase, call


class CheckpointBoundaryTests(LocalCase):
    def test_branch_recovery_at_boundary_gets_one_attempt_without_renewing_limits(self):
        task = self.fixture()
        task['branch_run']={'id':'run','current_item_id':'one','items':[{'id':'one','status':'working'}]}
        task.update(action_pending=True,worker_turns=12)
        runtime=Runtime(task);runtime.step_turns=12
        self.engine.checkpoint_boundary(runtime)
        self.assertEqual(runtime.step_turns,12)
        self.assertEqual(task['worker_turns'],12)
        # A restart and still-pending flag do not buy another free attempt.
        restarted=Runtime(task);restarted.step_turns=13
        with self.assertRaisesRegex(ProgressPause,'No meaningful'):
            self.engine.checkpoint_boundary(restarted)
        task['worker_turns']=task['limits']['worker_turns']
        with self.assertRaises(WorkerTurnLimit):
            self.engine.checkpoint_boundary(runtime)

    def test_thirteen_useful_turns_continue_to_real_check_and_review(self):
        task = self.fixture(paid=True)
        responses = [call('replace_text', {'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'})]
        responses += [call('write_file', {'path':f'note_{i}.md','content':f'Requested note {i}\n'}) for i in range(12)]
        responses += [call('checkpoint', {'summary':'All requested edits finished','uncertainties':''}), call('review_decision', {'decision':'APPROVE','feedback':'All requested files and bounds verified.'})]
        provider = Mock()
        provider.complete.side_effect = [(message, {'prompt_tokens':10,'completion_tokens':5,'cost':0}) for message in responses]
        self.engine.provider_factory = lambda *args: provider
        self.engine.start(task['id'])
        self.engine.runtimes[task['id']].thread.join(30)
        result = self.finish(task)
        self.assertEqual(result['status'], 'approved', result['error'])
        self.assertEqual(result['worker_turns'], 14)
        self.assertEqual(provider.complete.call_count, 15)
        self.assertEqual(len(result['checks']), 1)
        self.assertTrue(result['checks'][0]['passed'])
        self.assertEqual(len(result['checkpoints']), 1)
        self.assertTrue(any(e['title']=='Saved progress; continuing the remaining step' for e in result['events']))

    def test_boundary_resets_only_interval_and_never_approves_partial_work(self):
        task = self.fixture()
        runtime = Runtime(task)
        runtime.step_turns = 12
        runtime.argument_failures = 2
        runtime.handoffs = 1
        task['worker_turns'] = 12
        task['iterations'] = 2
        started = runtime.started
        Workspace(task['workspace']).write_file('unfinished.md', 'Still needs the remaining request.\n')
        self.engine.checkpoint_boundary(runtime)
        self.assertEqual(runtime.step_turns, 0)
        self.assertEqual(runtime.argument_failures, 2)
        self.assertEqual(runtime.handoffs, 1)
        self.assertEqual(runtime.started, started)
        self.assertEqual(task['worker_turns'], 12)
        self.assertEqual(task['iterations'], 2)
        self.assertEqual(task['checkpoints'], [])
        self.assertEqual(task['status'], 'ready')
        runtime.step_turns = 12
        with self.assertRaisesRegex(ProgressPause, 'No meaningful'):
            self.engine.checkpoint_boundary(runtime)

    def test_hard_turn_and_clock_limits_still_stop_progress(self):
        task = self.fixture()
        runtime = Runtime(task)
        Workspace(task['workspace']).write_file('progress.md', 'Saved\n')
        runtime.step_turns = 12
        task['worker_turns'] = task['limits']['worker_turns']
        with self.assertRaises(WorkerTurnLimit): self.engine.checkpoint_boundary(runtime)
        self.assertEqual(runtime.step_turns, 12)
        task['worker_turns'] = 12
        runtime.started -= 100000
        with self.assertRaises(ProgressPause): self.engine.checkpoint_boundary(runtime)
        self.assertEqual(runtime.step_turns, 12)
