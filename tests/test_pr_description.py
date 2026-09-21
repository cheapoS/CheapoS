"""Pure metadata contracts; no Git, model, network or process fixtures."""
import unittest

from cheapos import pr_description as prose
from cheapos.engine import worker_system
from cheapos.tools import WORKER_TOOLS, REVIEW_TOOLS


class DescriptionTests(unittest.TestCase):
    def setUp(self):
        self.draft = {'title': 'Respect both clamp bounds', 'description': 'Apply the lower bound before returning the clamped value.'}
        self.check = {'command': ['python3', '-B', '-m', 'unittest', 'test_bounds'], 'directory': 'component',
                      'passed': True, 'exit_code': 0, 'output': 'private output is not PR metadata'}
        self.review = {'decision': 'APPROVE', 'pull_request': self.draft, 'checks': self.check}
        self.task = {'title': 'Please fix it', 'checkpoints': [self.review]}
        self.candidate = {'files': ['bounds.py']}

    def test_optional_metadata_is_offered_without_extra_dispatch(self):
        for tools, name in ((WORKER_TOOLS, 'checkpoint'), (REVIEW_TOOLS, 'review_decision')):
            schema = next(t['function']['parameters'] for t in tools if t['function']['name'] == name)
            self.assertIn('pull_request', schema['properties'])
            self.assertNotIn('pull_request', schema['required'])
        task = {'settings_snapshot': {'values': {'git': {'workflow': 'pull_request'}}}}
        self.assertIn(prose.WORKER, worker_system(task))
        self.assertNotIn(prose.WORKER, worker_system({}))

    def test_current_approved_review_and_actual_checks_supply_publication(self):
        preview = prose.preview(self.task, self.candidate)
        self.assertEqual(preview['title'], self.draft['title'])
        self.assertEqual(preview['description_source'], 'reviewer')
        self.assertIn('directory: component; exit 0', preview['validation'])
        self.assertIn('python3 -B -m unittest test_bounds', preview['validation'])
        body = prose.body({**preview, 'message': preview['title'], 'head': 'abc'})
        self.assertNotIn(self.check['output'], body)
        self.assertIn('`abc`', body)

    def test_stale_or_invalid_prose_never_reuses_an_older_review(self):
        self.task['checkpoints'].append({'decision': 'APPROVE', 'checks': self.check, 'pull_request': {'title': ['bad']}})
        preview = prose.preview(self.task, self.candidate)
        self.assertEqual(preview['description_source'], 'fallback')
        self.assertNotEqual(preview['title'], self.draft['title'])
        for value in (None, {}, {'title': 'x\ny', 'description': ''}, {'title': 'x', 'description': 5},
                      {'title': 'x', 'description': '\x00'}, {'title': 'x'*201, 'description': ''}):
            self.assertIsNone(prose.clean(value))

    def test_final_review_supersedes_item_drafts_and_old_check_results(self):
        final = {'decision': 'APPROVE', 'pull_request': {'title': 'Ship all bounds', 'description': 'Both boundaries now work.'}}
        self.task['branch_run'] = {'readiness': {'review': final, 'checks': [{'record': self.check}]}}
        self.task['checks'] = [{'passed': True, 'command': ['invented-old-check']}]
        result = prose.preview(self.task, self.candidate)
        self.assertEqual(result['title'], 'Ship all bounds')
        self.assertNotIn('invented-old-check', result['validation'])
        self.assertEqual(prose.item_drafts({'requirements': [{'review': self.review}, {'review': self.review}]}), [self.draft])

    def test_incomplete_checks_and_model_claims_never_become_recorded_success(self):
        for change in ({'passed': False}, {'exit_code': 1}, {'truncated': True}, {'outcome': 'process_timeout'}):
            self.review['checks'] = {**self.check, **change}
            self.assertNotIn('Passed:', prose.preview(self.task, self.candidate)['validation'])
        self.review.pop('checks')
        self.review['worker_summary'] = 'All 500 tests passed'
        self.assertNotIn('500', prose.preview(self.task, self.candidate)['validation'])
