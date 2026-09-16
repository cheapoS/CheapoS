import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent))

from cheapos.engine import Runtime, REVIEW_TOOLS
from test_engine import LocalCase, call


class ReviewWorkflowTests(LocalCase):
    def chat(self):
        task = self.fixture(paid=True)
        task['conversational'] = True
        self.engine.store.save(task)
        return task
    def responses(self, replies):
        provider = Mock()
        provider.complete.side_effect = [(r, {'prompt_tokens':10,'completion_tokens':5,'cost':0}) for r in replies]
        self.engine.provider_factory = lambda *args: provider
        return provider

    def test_finished_edit_automatically_reaches_review_and_followups_remain_open(self):
        task = self.chat()
        self.responses([
            call('replace_text', {'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}),
            call('run_checks'), {'content':'The lower-bound fix is complete.'},
            call('review_decision', {'decision':'APPROVE','feedback':'Both bounds are covered.'}),
            {'content':'The max expression enforces the lower bound.'},
            call('write_file', {'path':'notes.txt','content':'Follow-up notes\n'}),
            {'content':'Added the requested notes.'},
            call('review_decision', {'decision':'APPROVE','feedback':'The notes satisfy the follow-up.'}),
        ])
        self.engine.start(task['id'])
        first = self.finish(task)
        self.assertEqual(first['status'], 'approved', first['error'])
        self.assertEqual(len(first['checks']), 1)
        self.assertEqual(first['review_count'], 1)
        self.assertTrue(any(e['kind']=='check_reused' for e in first['events']))
        self.engine.start(task['id'], {'message':'Explain the fix without editing.'})
        answer = self.finish(task)
        self.assertEqual(answer['status'], 'awaiting_reply')
        self.assertEqual(answer['checks'], first['checks'])
        self.assertEqual(answer['checkpoints'], first['checkpoints'])
        self.engine.reviewed_patch(answer)
        self.engine.start(task['id'], {'message':'Also add a notes file.'})
        revised = self.finish(task)
        self.assertEqual(revised['status'], 'approved', revised['error'])
        self.assertEqual(len(revised['checks']), 2)
        self.assertEqual(revised['review_count'], 2)
        self.assertNotEqual(revised['patch'], first['patch'])
        self.assertEqual(revised['checkpoints'][-1]['diff'], revised['patch'])

    def test_changed_check_command_requires_new_verification(self):
        task = self.chat()
        self.engine.file_tool(task, 'replace_text', {'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'})
        runtime = Runtime(task)
        self.engine.checks(runtime)
        task['check_command'] = [sys.executable, '-m', 'unittest', 'test_math_utils.ClampTests.test_above']
        self.responses([call('review_decision', {'decision':'APPROVE','feedback':'Current check passed.'})])
        self.engine.checkpoint(runtime, {'summary':'Review with the updated check','uncertainties':''})
        self.assertEqual(len(task['checks']), 2)
        self.assertEqual(task['checks'][-1]['command'], task['check_command'])

    def test_request_tests_decision_workflow(self):
        task = self.chat()
        self.responses([
            call('replace_text', {'path':'math_utils.py','old_text':'return min(value, upper)','new_text':'return max(lower, min(value, upper))'}),
            call('run_checks'), {'content':'Initial implementation complete.'},
            call('review_decision', {'decision':'REQUEST_TESTS','feedback':'Please add test cases for inverted bounds and NaN values.'}),
            call('write_file', {'path':'test_edge_cases.txt','content':'Edge case test coverage\n'}),
            call('run_checks'), {'content':'Added tests and verified.'},
            call('review_decision', {'decision':'APPROVE','feedback':'Test coverage is now sufficient.'}),
        ])
        self.engine.start(task['id'])
        first = self.finish(task)
        self.assertEqual(first['status'], 'approved', first['error'])
        self.assertEqual(first['review_count'], 2)
        self.assertEqual(first['checkpoints'][0]['decision'], 'REQUEST_TESTS')
        self.assertEqual(first['checkpoints'][0]['feedback'], 'Please add test cases for inverted bounds and NaN values.')
        self.assertEqual(first['checkpoints'][1]['decision'], 'APPROVE')

    def test_review_tools_schema_includes_request_tests(self):
        review_tool = next(t for t in REVIEW_TOOLS if t['function']['name'] == 'review_decision')
        enums = review_tool['function']['parameters']['properties']['decision']['enum']
        self.assertIn('REQUEST_TESTS', enums)
        self.assertIn('APPROVE', enums)
        self.assertIn('REQUEST_CHANGES', enums)
        self.assertIn('TAKE_OVER', enums)