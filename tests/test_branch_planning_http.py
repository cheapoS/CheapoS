import copy
import http.client
import json
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from cheapos.server import LocalServer
from cheapos.workspace import git
from cheapos.branch_workspace import _tip
from test_engine import call
import test_branch_start as fixture


class PlanningProvider:
    def __init__(self, command):
        self.command = command
        self.inputs = []
        self.clarify = False
        self.entered = threading.Event()
        self.release = None

    def complete(self, messages, tools, max_tokens):
        captured = json.loads(messages[1]['content'])
        self.inputs.append(captured['captured_inputs'])
        self.entered.set()
        if self.release is not None:
            if not self.release.wait(10): raise ValueError('Fixture planner timed out')
        value = {'status': 'clarification', 'plan': None, 'clarification': 'Keep or remove the original utility?'} if self.clarify else {
            'status': 'plan', 'clarification': '', 'plan': {'items': [{'id': 'utility', 'title': 'Implement utility', 'instructions': 'Implement the requested utility', 'acceptance_criteria': ['Utility works'], 'required_checks': [self.command]}], 'limits': captured['displayed_limits'], 'final_checks': [self.command]}}
        return call('propose_branch_plan', value), {'prompt_tokens': 20, 'completion_tokens': 10, 'cost': 0}


class BranchPlanningHTTPTests(unittest.TestCase):
    def setUp(self):
        fixture.BranchStartTests.setUp(self)
        self.provider = PlanningProvider(self.values['plan']['final_checks'][0])
        self.engine.provider_factory = lambda *args: self.provider
        self.server = LocalServer(('127.0.0.1', 0), Path(__file__).resolve().parent.parent / 'dist', self.engine)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(5)

    def post(self, path, values):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=30)
        connection.request('POST', path, json.dumps(values), {'Content-Type': 'application/json', 'X-CheapOS-Token': self.server.token})
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def request_values(self, prompt='Implement utility', document=None, suffix='job'):
        return {key: self.values[key] for key in ('repository', 'base_ref', 'target_ref')} | {'feature_ref': 'refs/heads/feature/' + suffix, 'planning_id': 'plan-' + suffix, 'prompt': prompt, 'document': document, 'limits': {'dollars': 0}}

    def test_prompt_document_and_combined_proposals_retain_input_usage_and_require_start(self):
        (self.source / 'tasks.md').write_text('Implement the utility and its tests. Plain prose is sufficient.\n')
        for n, (prompt, document) in enumerate([('Implement utility', None), ('', 'tasks.md'), ('Keep compatibility', 'tasks.md')]):
            with self.subTest(prompt=prompt, document=document):
                status, proposal = self.post('/api/branch-runs/plan', self.request_values(prompt, document, str(n)))
                self.assertEqual(status, 200, proposal)
                task = self.engine.store.get(proposal['task_id'])
                self.assertEqual(task['branch_run']['status'], 'awaiting_authorization')
                self.assertEqual(task['branch_run']['plan']['items'][0]['id'], 'utility')
                self.assertEqual(task['branch_run']['inputs']['prompt'], prompt)
                self.assertEqual(task['branch_run']['inputs']['document']['path'] if document else task['branch_run']['inputs']['document'], document)
                self.assertGreaterEqual(task['branch_run']['consumption']['requests'], 1)
                self.assertEqual(task['usage']['worker']['tokens'], 30)
                self.assertIsNone(_tip(self.source, 'refs/heads/feature/' + str(n)))
                self.assertFalse(self.engine.runtimes)
                # Ordinary draft selection/planning never authorizes a branch.
                start_status, _ = self.post('/api/tasks/' + task['id'] + '/branch-start', {'proposal_id': proposal['proposal_id'], 'approved': True})
                self.assertEqual(start_status, 200)
                self.assertIsNotNone(_tip(self.source, 'refs/heads/feature/' + str(n)))

    def test_project_defaults_to_main_not_current_feature_and_capture_errors_do_not_infer(self):
        git(self.source, 'checkout', '-qb', 'feature/operator')
        status, project = self.post('/api/branch-runs/project', {'repository': str(self.source)})
        self.assertEqual(status, 200)
        self.assertEqual((project['base_ref'], project['target_ref']), ('refs/heads/main', 'refs/heads/main'))
        for document in ('missing.md', '.env', '../escape'):
            status, _ = self.post('/api/branch-runs/plan', self.request_values('Keep this prompt', document))
            self.assertEqual(status, 400)
        self.assertFalse(self.provider.inputs)
        self.assertIsNone(_tip(self.source, 'refs/heads/feature/job'))

    def test_conflict_is_clarification_with_preserved_captured_request(self):
        (self.source / 'scope.md').write_text('Remove the original utility.')
        self.provider.clarify = True
        status, result = self.post('/api/branch-runs/plan', self.request_values('Keep the original utility', 'scope.md'))
        self.assertEqual(status, 400, result)
        self.assertIn('Keep or remove', result['error'])
        saved = next(iter(self.engine.store.tasks.values()))
        self.assertEqual(saved['branch_run']['inputs']['prompt'], 'Keep the original utility')
        self.assertEqual(saved['branch_run']['inputs']['document']['contents'], 'Remove the original utility.')
        self.assertIsNone(_tip(self.source, 'refs/heads/feature/job'))

    def test_cancellation_after_inference_before_preparation_does_not_publish_proposal(self):
        entered = threading.Event(); release = threading.Event(); results = []
        original = self.engine.branch.prepare
        def delayed(values, planning_task=None):
            entered.set()
            if not release.wait(10): raise ValueError('Fixture preparation timed out')
            return original(values, planning_task=planning_task)
        with patch.object(self.engine.branch, 'prepare', side_effect=delayed):
            worker = threading.Thread(target=lambda: results.append(self.post('/api/branch-runs/plan', self.request_values())))
            worker.start()
            try:
                self.assertTrue(entered.wait(10))
                status, result = self.post('/api/branch-runs/plan-stop', {'planning_id': 'plan-job'})
                self.assertEqual((status, result['stopped']), (200, True))
            finally:
                release.set(); worker.join(20)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0][0], 400, results)
        self.assertIsNone(_tip(self.source, 'refs/heads/feature/job'))
        self.assertFalse(any(t['branch_run']['status'] == 'awaiting_authorization' for t in self.engine.store.tasks.values()))

    def test_cancel_inflight_planning_and_duplicate_id_do_not_start_branch(self):
        self.provider.release = threading.Event()
        results = []
        worker = threading.Thread(target=lambda: results.append(self.post('/api/branch-runs/plan', self.request_values())))
        worker.start()
        try:
            self.assertTrue(self.provider.entered.wait(5))
            status, _ = self.post('/api/branch-runs/plan', self.request_values())
            self.assertEqual(status, 400)
            status, result = self.post('/api/branch-runs/plan-stop', {'planning_id': 'plan-job'})
            self.assertEqual((status, result['stopped']), (200, True))
        finally:
            self.provider.release.set(); worker.join(20)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0][0], 400, results)
        self.assertIsNone(_tip(self.source, 'refs/heads/feature/job'))
        self.assertFalse(self.engine.runtimes)
        task = next(iter(self.engine.store.tasks.values()))
        self.assertEqual(task['branch_run']['status'], 'paused')
        self.assertGreaterEqual(task['usage']['worker']['tokens'], 30)


if __name__ == '__main__': unittest.main()
