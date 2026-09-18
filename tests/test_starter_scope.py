"""Welcome suggestions must not turn inspection into an unsolicited repair."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

from cheapos import work_policy
from cheapos.engine import CHAT_TOOLS, COMPACT_WRITE, LINE_EDIT, Engine
import test_chat as chat_fixture
import test_routing as routing_fixture
from test_engine import LocalCase, call, wait_for


class StarterScopeTests(LocalCase):
    chat = chat_fixture.ChatTests.chat
    provider = chat_fixture.ChatTests.provider

    def assert_answer_only(self, task, original):
        self.assertEqual(task['status'], 'awaiting_reply', task['error'])
        self.assertEqual(task['changes'], [])
        self.assertEqual(task['checks'], [])
        self.assertEqual(task['checkpoints'], [])
        self.assertIsNone(task['pending_approval'])
        self.assertEqual((Path(task['workspace']) / 'math_utils.py').read_text(), original)
        self.assertEqual((Path(task['source']) / 'math_utils.py').read_text(), original)

    def test_actual_welcome_prompts_stay_read_only_through_multiple_reads(self):
        frontend = (Path(__file__).resolve().parents[1] / 'dist/app.js').read_text()
        for prompt in work_policy.READ_ONLY_STARTERS:
            with self.subTest(prompt=prompt):
                # Catches drift between the UI's actual submitted text and policy.
                self.assertIn('data-suggestion="' + prompt + '"', frontend)
                task = self.chat(prompt)
                original = (Path(task['workspace']) / 'math_utils.py').read_text()
                requests = self.provider([
                    call('list_files'), call('read_file', {'path': 'math_utils.py'}),
                    call('read_file', {'path': 'test_math_utils.py'}),
                    {'content': 'This sample has two Python files and no README. By inspection, clamp ignores the lower bound. I have not run tests or changed files.'},
                ])
                self.engine.start(task['id'])
                result = self.finish(task)
                self.assert_answer_only(result, original)
                self.assertEqual(result['work_stage'], 'explanation')
                for messages, tools in requests:
                    self.assertLessEqual({t['function']['name'] for t in tools}, work_policy.READ_ONLY_TOOLS)
                    self.assertIn('read-only explanation', messages[0]['content'])
                    self.assertNotIn('Current stage: implementation', json.dumps(messages))

    def test_mixed_unsolicited_edit_batch_is_blocked_before_any_action_in_every_mode(self):
        for mode in ('manual', 'local', 'remote', 'delegate'):
            with self.subTest(mode=mode):
                prompt = work_policy.READ_ONLY_STARTERS[0]
                if mode != 'manual':
                    # Previous subcases deliberately pinned local fixtures.
                    settings = self.engine.settings_store
                    settings.save({'roles.worker': {'strategy': 'automatic'},
                                   'roles.reviewer': {'strategy': 'automatic'}},
                                  expected_revision=settings.view()['revision'], operation_id='starter-' + mode)
                task = self.chat(prompt) if mode == 'manual' else routing_fixture.RoutingTests.chat(self, mode, prompt)
                original = (Path(task['workspace']) / 'math_utils.py').read_text()
                task['check_command'] = ['fixture-python-does-not-exist', '-m', 'unittest']
                task['auto_approve_checks'] = True
                self.engine.store.save(task)
                bad = call('read_file', {'path': 'test_math_utils.py'})
                bad['content'] = 'Tests confirm the bug. I fixed it.'
                bad['tool_calls'] += call('replace_text', {'path':'math_utils.py', 'old_text':'return min(value, upper)', 'new_text':'return max(lower, min(value, upper))'})['tool_calls']
                bad['tool_calls'] += call('run_checks')['tool_calls']
                replies = ([call('delegate_work', {'summary':'Fix clamp and verify it.'})] if mode == 'delegate' else []) + [
                    call('read_file', {'path':'math_utils.py'}), bad,
                    {'content':'The source ignores the lower bound. No tests ran and no edits were made.'},
                ]
                requests = self.provider(replies) if mode == 'manual' else routing_fixture.RoutingTests.responses(self, replies)
                self.engine.start(task['id'])
                result = self.finish(task)
                self.assert_answer_only(result, original)
                self.assertEqual(result['tool_actions'], 1)  # Even the read in the mixed batch is rejected.
                self.assertEqual(sum(e['title'] == 'Keeping this request read-only' for e in result['events']), 1)
                self.assertNotIn('I fixed it.', json.dumps(result['events']))
                self.assertNotIn('environment_setup', result)
                self.assertFalse(any(e['title'] == 'Switching to another free worker' for e in result['events']))
                self.assertGreater(result['usage']['worker']['tokens'], 0)
                if mode == 'manual':
                    self.assertEqual(len(requests), 3)
                    self.assertEqual(requests[-1][1], [])

    def test_unavailable_tools_and_compact_variants_cannot_leak_into_starter_scope(self):
        task = self.chat(work_policy.READ_ONLY_STARTERS[1])
        tools = work_policy.offered_tools(task, CHAT_TOOLS + [LINE_EDIT, COMPACT_WRITE])
        self.assertEqual({t['function']['name'] for t in tools}, work_policy.READ_ONLY_TOOLS)
        for name in ('write_file', 'replace_text', 'replace_lines', 'run_checks', 'checkpoint', 'review_decision', 'invented_shell'):
            with self.subTest(tool=name), self.assertRaises(work_policy.ReadOnlyViolation):
                work_policy.validate_response(task, call(name))
        task['limits']['output_tokens'] = 512
        task['compact_edits'] = True
        self.assertIsNone(work_policy.small_edit_reason(task))

    def test_repeated_violation_has_one_bounded_answer_retry(self):
        task = self.chat(work_policy.READ_ONLY_STARTERS[0])
        requests = self.provider([call('run_checks'), call('write_file', {'path':'bad.txt','content':'bad'})])
        self.engine.start(task['id'])
        result = self.finish(task)
        self.assertEqual(len(requests), 2)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error_code'], 'read_only_request')
        self.assertEqual(result['checks'], [])
        self.assertEqual(result['tool_actions'], 0)
        self.assertFalse((Path(task['workspace']) / 'bad.txt').exists())

    def test_explicit_followup_can_edit_verify_and_reach_review(self):
        task = self.chat(work_policy.READ_ONLY_STARTERS[1])
        requests = self.provider([
            {'content':'I suggest fixing the ignored lower bound.'},
            call('replace_text', {'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}),
            call('run_checks', {'command':sys.executable+' -m unittest discover -v'}),
            call('checkpoint', {'summary':'Fixed the lower bound.','uncertainties':''}),
            call('review_decision', {'decision':'APPROVE','feedback':'Bounds fixed and checks passed.'}),
        ])
        self.engine.start(task['id'])
        self.assertEqual(self.finish(task)['status'], 'awaiting_reply')
        self.engine.start(task['id'], {'message':'Yes, implement that fix.'})
        wait_for(lambda: self.engine.store.get(task['id'])['status'] == 'waiting_approval')
        self.engine.approve_check(task['id'], True)
        result = self.finish(task)
        self.assertEqual(result['status'], 'approved', result['error'])
        self.assertTrue(result['changes'])
        self.assertEqual(len(result['checks']), 1)
        self.assertTrue(result['checks'][0]['passed'])
        self.assertEqual(result['review_count'], 1)
        self.assertIn('replace_text', {t['function']['name'] for t in requests[1][1]})

    def test_resume_old_starter_preserves_saved_edits_without_executing_pending_work(self):
        task = self.chat(work_policy.READ_ONLY_STARTERS[0])
        path = Path(task['workspace']) / 'math_utils.py'
        path.write_text('def clamp(value, lower, upper):\n    return max(lower, min(value, upper))\n')
        self.engine.refresh_changes(task)
        saved_patch = task['patch']
        task.update(status='paused', error_code='environment_setup', check_command=['fixture-missing-python'],
                    pending_verification=True, pending_checkpoint={'summary':'Fix it'}, compact_edits=True,
                    action_pending=True, loop_guidance='Run tests and checkpoint now.')
        self.engine.store.save(task)
        self.engine.shutdown()
        self.engine = Engine(self.engine.store.root)
        self.provider([call('run_checks'), {'content':'The saved task copy clamps both bounds. Those earlier edits remain unreviewed; I ran no checks.'}])
        with patch.object(self.engine, 'checks', side_effect=AssertionError('No verification on explanation')), patch.object(self.engine, 'checkpoint_feedback', side_effect=AssertionError('No review on explanation')):
            self.engine.start(task['id'])
            result = self.finish(task)
        self.assertEqual(result['status'], 'awaiting_reply', result['error'])
        self.assertEqual(result['patch'], saved_patch)
        self.assertEqual(result['checks'], [])
        self.assertEqual(result['checkpoints'], [])
        self.assertNotIn('commits', result)
        self.assertIn('return min(value, upper)', (Path(task['source']) / 'math_utils.py').read_text())

    def test_inspection_does_not_promote_arbitrary_questions_to_implementation(self):
        task = self.chat('How does clamp work?')
        task['events'].append({'kind':'tool','title':'read file'})
        self.assertEqual(work_policy.stage(task), 'orientation')
        task['patch'] = task['turn_start_patch'] = 'previous unreviewed edits'
        task['changes'] = [{'path':'math_utils.py'}]
        self.assertEqual(work_policy.stage(task), 'orientation')
        self.assertEqual(work_policy.offered_tools(task, CHAT_TOOLS), CHAT_TOOLS)

    def test_scope_does_not_classify_edited_drafts_or_branch_items_as_starters(self):
        task = self.chat(work_policy.READ_ONLY_STARTERS[0])
        self.assertTrue(work_policy.read_only(task))
        task['requests'][-1] += ' Then fix any bug you find.'
        self.assertFalse(work_policy.read_only(task))
        task['requests'][-1] = work_policy.READ_ONLY_STARTERS[0]
        task['branch_run'] = {'current_item_id':'authorized-item'}
        self.assertFalse(work_policy.read_only(task))
