"""Recovery boundaries, using fake requests and clocks; no network or Git fixtures."""
import copy
import io
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from cheapos import branch_planner, routing
from cheapos.branch_controller import BranchController
from cheapos.engine import Engine
from cheapos.providers import BudgetError, ProviderError, ToolCallValidationError, http_failure


class RoutingErrorRepairTests(unittest.TestCase):
    def test_gateway_tool_validation_is_distinct_and_does_not_expose_body(self):
        for detail in ({'code': 'tool_use_failed'}, {'message': 'Tool call validation failed: secret schema text'}):
            body = {'error': {**detail, 'failed_generation': 'secret output'}}
            error = HTTPError('http://localhost/v1/chat/completions', 400, '', {},
                              io.BytesIO(json.dumps(body).encode()))
            result = http_failure(error, {'gateway': 'omniroute'})
            self.assertIsInstance(result, ToolCallValidationError)
            self.assertNotIn('secret', str(result))
        for body in ({'error': {'message': 'Invalid request: secret'}}, ['invalid'], {'error': None}):
            error = HTTPError('http://localhost/v1/chat/completions', 400, '', {},
                              io.BytesIO(json.dumps(body).encode()))
            self.assertNotIsInstance(http_failure(error, {'gateway': 'omniroute'}), ToolCallValidationError)

    def planner_fixture(self, responses):
        inputs = {'source': '/fixture', 'prompt': 'Keep all requirements'}
        inputs['hash'] = branch_planner._digest(inputs)
        task = {'status': 'planning', 'execution': {'mode': 'remote'}, 'route': {'base_url': 'fixture'},
                'planning_limits': {'dollars': 0}, 'usage': {'cost': 0},
                'providers': {'planner': {'model': 'groq/planner', 'base_url': 'fixture'}}}
        runtime = SimpleNamespace(task=task, stop=threading.Event(), guard=Mock(), failed_models=set(), handoffs=0)
        engine = object.__new__(Engine)
        engine.store = Mock()
        engine.effective_role_mapping = Mock(return_value={})
        engine.event = Mock()
        engine.defer_route = Mock(side_effect=AssertionError('A schema repair must not change routes'))
        gateway = SimpleNamespace(settings={}, catalog=Mock(return_value={
            'status': 'ready', 'models': [{'id': 'groq/planner'}]}), pool=Mock())
        gateway.pool.observation.return_value = {'cooling_down': False}
        engine.connection_for = Mock(return_value=gateway)
        requests = []
        def request(*args, **kwargs):
            requests.append(copy.deepcopy(args[1]))
            task['usage']['cost'] += 1  # retained accounting, including rejected calls
            reply = responses.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        engine._request = request
        return engine, runtime, inputs, requests

    def planning_patches(self):
        from contextlib import ExitStack
        stack = ExitStack()
        for name, result in (('effective_settings', {}), ('validate_current', None),
                             ('eligible', True), ('guard', None), ('classify', 'public_free')):
            stack.enter_context(patch('cheapos.access_policy.' + name, return_value=result))
        stack.enter_context(patch.object(branch_planner, 'project_context', return_value='Saved repository context'))
        return stack

    def test_upstream_rejection_repairs_on_same_planner_with_saved_context(self):
        inspection = {'tool_calls': [{'id': 'read', 'function': {
            'name': 'inspect_project_file', 'arguments': '{"path":"README.md"}'}}]}
        checks = ['python3 -B -m unittest tests.test_reader']
        expected = {'items': [{'id': 'reader', 'title': 'Add reader', 'instructions': 'Preserve Unicode',
                              'dependencies': [], 'acceptance_criteria': ['Reader preserves Unicode'],
                              'required_checks': checks}], 'limits': {'dollars': 0}, 'final_checks': checks}
        proposal = {'tool_calls': [{'id': 'plan', 'function': {'name': 'propose_branch_plan',
                    'arguments': json.dumps({'status': 'plan', 'plan': expected, 'clarification': ''})}}]}
        engine, runtime, inputs, requests = self.planner_fixture([
            inspection, ToolCallValidationError(), proposal])
        with self.planning_patches(), patch.object(branch_planner, 'inspect_project_file', return_value={
                'path': 'README.md', 'contents': 'Retained evidence'}):
            self.assertEqual(branch_planner.plan(engine, runtime, inputs), expected)
        self.assertEqual(requests[0][:2], requests[-1][:2])
        self.assertIn('Retained evidence', str(requests[-1]))
        self.assertIn('plan.items', requests[-1][-1]['content'])
        self.assertEqual(sum(m.get('role') == 'tool' for m in requests[-1]), 1)
        self.assertEqual(runtime.task['usage']['cost'], 3)
        self.assertEqual(runtime.handoffs, 0)
        engine.defer_route.assert_not_called()
        self.assertFalse(any('error' in c.kwargs for c in engine.connection_for.return_value.pool.record.call_args_list))

    def test_schema_repair_remains_bounded_and_does_not_reset_accounting(self):
        engine, runtime, inputs, requests = self.planner_fixture([ToolCallValidationError() for _ in range(3)])
        from cheapos.branch_pause import PauseError
        with self.planning_patches(), patch('cheapos.routing._select_connections', side_effect=routing.RoutingPause('No alternate')):
            with self.assertRaises(routing.RoutingPause) as caught:
                branch_planner.plan(engine, runtime, inputs)
        self.assertIn('No alternate', str(caught.exception))
        self.assertEqual(len(requests), 3)
        self.assertEqual(runtime.task['usage']['cost'], 3)

    def test_auth_failure_is_not_repaired_as_a_proposal(self):
        error = ProviderError('Key rejected', code='http_401')
        engine, runtime, inputs, requests = self.planner_fixture([error])
        with self.planning_patches(), self.assertRaises(ProviderError) as caught:
            branch_planner.plan(engine, runtime, inputs)
        self.assertIs(caught.exception, error)
        self.assertEqual(len(requests), 1)
        self.assertFalse(any(c.args[1] == 'planning_repair' for c in engine.event.call_args_list))

    def test_request_configuration_errors_do_not_enter_proposal_repair(self):
        for error in (ValueError('Access policy changed'), TypeError('Request configuration invalid')):
            engine, runtime, inputs, requests = self.planner_fixture([error])
            with self.planning_patches(), self.assertRaises(type(error)) as caught:
                branch_planner.plan(engine, runtime, inputs)
            self.assertIs(caught.exception, error)
            self.assertEqual(len(requests), 1)

    def test_unscheduled_pause_never_invents_a_retry(self):
        for message in ('API key rejected', 'Invalid request', 'Handoffs exhausted'):
            error = routing.RoutingPause(message)
            runtime = SimpleNamespace(route_autorecover=True)
            engine = Mock()
            with patch.object(routing, '_select_connections', side_effect=error), self.assertRaises(routing.RoutingPause):
                routing.select_remote(engine, runtime)
            engine.wait_for_route.assert_not_called()
            engine.route_wait_info.assert_not_called()
            self.assertIsNone(error.retry_at)

    def test_scheduled_availability_wait_retries_without_clearing_work(self):
        task = {'status': 'planning', 'usage': {'cost': 3}, 'checks': ['saved']}
        runtime = SimpleNamespace(route_autorecover=True, task=task)
        engine = Mock()
        engine.route_wait_info.return_value = {'can_wait': True, 'retry_at': 123}
        with patch.object(routing, '_select_connections', side_effect=[routing.RoutingPause('Wait', retry_at=123), None]) as select:
            routing.select_remote(engine, runtime, 'planner')
        self.assertEqual(select.call_count, 2)
        engine.wait_for_route.assert_called_once_with(runtime)
        self.assertEqual(task['usage']['cost'], 3)
        self.assertEqual(task['checks'], ['saved'])
        self.assertEqual(task['status'], 'planning')

    def test_background_planner_enables_scheduled_recovery(self):
        task = {'id': 't', 'branch_run': {'inputs': {'prompt': 'original'}}}
        runtime = SimpleNamespace(task=task, stop=threading.Event(), branch_ledger=Mock())
        engine = SimpleNamespace(lock=threading.RLock(), runtimes={'t': runtime}, event=Mock(),
                                 store=SimpleNamespace(get=Mock(return_value=task)))
        controller = object.__new__(BranchController)
        controller.engine = engine
        controller.planning = {'p': {'cancelled': False}}
        controller.proposals = SimpleNamespace(lock=threading.RLock(), proposals={'proposal': {'task_id': 't'}})
        controller.prepare = Mock(return_value={'proposal_id': 'proposal', 'task_id': 't'})
        def plan(*args):
            self.assertTrue(runtime.route_autorecover)
            return {'items': ['proposed']}
        with patch.object(branch_planner, 'plan', side_effect=plan):
            controller._finish_plan({}, runtime, 'p')
        runtime.branch_ledger.begin.assert_called_once()
        runtime.branch_ledger.end.assert_called_once()

    def test_review_stops_keep_original_diagnostic_instead_of_rotating(self):
        from cheapos.engine import ProgressPause
        for error in (BudgetError('Budget reached'), ProgressPause('No progress'),
                      ValueError('Evidence changed'), ProviderError('Access denied', code='http_403')):
            task = {'pending_review': {'worker_summary': 'Saved review'}}
            runtime = SimpleNamespace(task=task, stop=threading.Event())
            controller = SimpleNamespace(engine=Mock())
            with patch('cheapos.branch_review.checkpoint', side_effect=error), self.assertRaises(type(error)) as caught:
                BranchController.continue_item(controller, runtime, {'id': 'one', 'status': 'reviewing'})
            self.assertIs(caught.exception, error)
            controller.engine.defer_route.assert_not_called()
            controller.engine._run_with_wait.assert_not_called()
