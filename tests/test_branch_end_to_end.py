"""One independent, actual CLI proof through run, revision, review and local merge."""
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from cheapos import branch_completion as completion
from cheapos.workspace import git
from branch_fixture import Fixture


class BranchEndToEndTests(unittest.TestCase):
    def test_csv_job_repairs_revision_and_one_explicit_local_merge(self):
        fixture = Fixture()
        self.addCleanup(fixture.close)
        engine, source = fixture.engine, fixture.source
        started = time.monotonic()

        def source_state():
            return (git(source, 'rev-parse', 'HEAD'), git(source, 'write-tree'),
                    git(source, 'status', '--porcelain'),
                    {name: (source / name).read_bytes() for name in ('README.md', 'SPEC.md')})

        def finished(task_id):
            runtime = engine.runtimes[task_id]
            runtime.thread.join(120)
            self.assertFalse(runtime.thread.is_alive(), 'The bounded deterministic job did not finish')
            task = engine.store.get(task_id)
            self.assertEqual(task['branch_run']['status'], 'ready_for_merge', task.get('error'))
            return task

        baseline = source_state()
        values = fixture.values()
        # This proof measures run/review/revision/merge correctness, not work
        # caps. Keep prompt/schema growth from censoring its scripted baseline;
        # budget tests cover cap enforcement, and spending/permissions stay on.
        values['plan']['measurement'] = True
        proposal = engine.branch.prepare(values)
        task = engine.branch.authorize(proposal['task_id'], {'proposal_id': proposal['proposal_id'], 'approved': True, 'full_suite_approved': True})
        task = finished(task['id']); task_id = task['id']; run = task['branch_run']
        self.assertTrue(run['authorization']['contract']['plan']['measurement'])
        self.assertEqual([item['id'] for item in run['items']], ['csv', 'markdown', 'cli'])
        self.assertEqual([item['status'] for item in run['items']], ['committed'] * 3)
        self.assertEqual(len(run['completed_operations']), 3)
        self.assertEqual(git(source, 'rev-list', '--count', run['base_sha'] + '..' + run['feature_ref']).strip(), '3')
        self.assertEqual(source_state(), baseline)
        self.assertTrue(any(check.get('outcome') == 'test_failure' for check in task['checks']))
        self.assertTrue(fixture.provider.reviewer_revision)
        self.assertTrue(any(event['kind'] == 'review' and isinstance(event.get('detail'), dict) and event['detail'].get('decision') == 'REQUEST_CHANGES' for event in task['events']))
        self.assertFalse(any(event['kind'] == 'permission' and event['title'].startswith('Permission needed') for event in task['events']))
        self.assertEqual([event['detail']['item_id'] for event in run['events'] if event['kind'] == 'item_completed'], ['csv', 'markdown', 'cli'])

        # These assertions are independently specified, not imported from the
        # scripted provider's source/test strings or model completion feedback.
        sample = fixture.root / 'independent.csv'
        sample.write_text('name,note\n"Ada, L","x|y"\n')
        expected = '| name | note |\n| --- | --- |\n| Ada, L | x\\|y |\n'
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, 'csvmd.py', str(sample)], cwd=task['workspace'], env=environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected)
        malformed = fixture.root / 'malformed.csv'; malformed.write_text('a,b\n1\n')
        rejected = subprocess.run([sys.executable, 'csvmd.py', str(malformed)], cwd=task['workspace'], env=environment, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('Inconsistent row width', rejected.stderr)

        preview = completion.preview(engine.branch, task_id)
        self.assertTrue(preview['merge_available'], preview.get('blocker'))
        paths = {file['path'] for file in preview['files']}
        self.assertEqual(paths, {'README.md', 'csv_reader.py', 'markdown_table.py', 'csvmd.py', 'test_csv_reader.py', 'test_markdown_table.py', 'test_cli.py'})
        self.assertEqual([entry['item_id'] for entry in preview['commits']], ['csv', 'markdown', 'cli'])
        offset, pages = 0, []
        while offset is not None:
            page = completion.diff(engine.branch, task_id, {'preview_id': preview['preview_id'], 'offset': offset, 'limit': 1000})
            pages.append(page['diff']); offset = page['next_offset']
        complete_diff = ''.join(pages)
        self.assertEqual(len(complete_diff), preview['diff_length'])
        for path in paths: self.assertIn('b/' + path, complete_diff)
        initial_receipts = [item['ready_receipt'] for item in run['items']]
        old_readiness = run['readiness']['id']
        old_tip = run['expected_feature_tip']

        correction = completion.revise(engine.branch, task_id, {'message': 'Add a concrete CSV input and resulting Markdown example to the CLI usage documentation'})
        self.assertEqual(engine.store.get(task_id)['branch_run']['expected_feature_tip'], old_tip)
        completion.revise(engine.branch, task_id, {'proposal_id': correction['revision_proposal']['proposal_id'], 'approved': True})
        task = finished(task_id); run = task['branch_run']
        self.assertTrue(run['plan']['measurement'])
        self.assertEqual(len(run['items']), 4)
        self.assertEqual(run['items'][-1]['id'], 'revision-1')
        self.assertEqual([item['status'] for item in run['items']], ['committed'] * 4)
        self.assertEqual([item['ready_receipt'] for item in run['items'][:3]], initial_receipts)
        self.assertNotEqual(run['readiness']['id'], old_readiness)
        self.assertEqual(git(source, 'rev-parse', run['expected_feature_tip'] + '^').strip(), old_tip)
        self.assertEqual(git(source, 'rev-list', '--count', run['base_sha'] + '..' + run['feature_ref']).strip(), '4')
        self.assertEqual(source_state(), baseline)
        documentation = (Path(task['workspace']) / 'README.md').read_text()
        self.assertIn('```csv\nname,score\nAda,9\n```', documentation)
        self.assertIn('```markdown\n| name | score |\n| --- | --- |\n| Ada | 9 |\n```', documentation)
        with self.assertRaises(ValueError):
            completion.merge(engine.branch, task_id, {'preview_id': preview['preview_id'], 'approved': True})
        self.assertEqual(source_state(), baseline)

        final_preview = completion.preview(engine.branch, task_id)
        self.assertTrue(final_preview['merge_available'], final_preview.get('blocker'))
        self.assertEqual(len(final_preview['commits']), 4)
        checks_before, calls_before = len(task['checks']), len(fixture.provider.calls)
        merged = completion.merge(engine.branch, task_id, {'preview_id': final_preview['preview_id'], 'approved': True})
        self.assertEqual(merged['branch_run']['status'], 'merged')
        tip = run['expected_feature_tip']
        self.assertEqual(git(source, 'rev-parse', 'HEAD').strip(), tip)
        self.assertEqual(git(source, 'symbolic-ref', 'HEAD').strip(), 'refs/heads/main')
        self.assertEqual(git(source, 'write-tree').strip(), git(source, 'rev-parse', tip + '^{tree}').strip())
        self.assertEqual(git(source, 'status', '--porcelain'), '')
        self.assertEqual(len(merged['checks']), checks_before)
        self.assertEqual(len(fixture.provider.calls), calls_before)
        repeated = completion.merge(engine.branch, task_id, {'preview_id': final_preview['preview_id'], 'approved': True})
        self.assertEqual(repeated['branch_run']['merge_receipt']['id'], merged['branch_run']['merge_receipt']['id'])
        self.assertEqual(len([event for event in repeated['branch_run']['events'] if event['kind'] == 'merged']), 1)
        result = subprocess.run([sys.executable, 'csvmd.py', str(sample)], cwd=source, env=environment, capture_output=True, text=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout), (0, expected))
        self.assertGreater(run['consumption']['working_seconds'], 0)
        self.assertGreater(task['usage']['worker']['tokens'], 0)
        self.assertGreater(task['usage']['reviewer']['tokens'], 0)
        self.assertEqual(task['usage']['cost'], 0)
        print('\nBranch proof: ' + json.dumps({'elapsed_seconds': round(time.monotonic() - started, 2), 'active_seconds': run['consumption']['working_seconds'], 'feature_commits': 4, 'checks': checks_before, 'failed_checks': sum(not c['passed'] for c in task['checks']), 'reviewer_requested_repairs': int(fixture.provider.reviewer_revision), 'model_requests': calls_before, 'worker_tokens': task['usage']['worker']['tokens'], 'reviewer_tokens': task['usage']['reviewer']['tokens'], 'accounted_cost': task['usage']['cost'], 'provider': 'deterministic scripted fixture', 'intermediate_operator_approvals': 0, 'operator_actions': ['Start run', 'request documentation correction', 'confirm correction', 'approve local merge']}))


if __name__ == '__main__': unittest.main()
