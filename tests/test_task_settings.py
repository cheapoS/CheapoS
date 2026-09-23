"""Task settings transitions use in-memory tasks, no providers/Git/waits."""
import copy
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from cheapos import task_settings
from cheapos.engine import limits_from
from cheapos.settings_store import SettingsConflict


class MemoryStore:
    def __init__(self, task):
        self.tasks = {task['id']: copy.deepcopy(task)}
        self.writes = 0
    def get(self, key):
        return copy.deepcopy(self.tasks[key])
    def save(self, task):
        self.tasks[task['id']] = copy.deepcopy(task)
        self.writes += 1


class TaskSettingsTests(unittest.TestCase):
    def setUp(self):
        provider = {'gateway': 'omniroute', 'connection_id': 'default', 'base_url': 'http://127.0.0.1:20128/v1', 'input_rate': 0, 'output_rate': 0}
        limits = limits_from({'dollars': 0})
        self.task = {'id': 'a', 'status': 'paused', 'source': '/example', 'execution': {'mode': 'remote'},
            'providers': {'worker': {**provider, 'model': 'writer'}, 'reviewer': {**provider, 'model': 'old-review'}},
            'route': {}, 'limits': limits, 'usage': {'cost': 0, 'tokens': 1234},
            'checks': [{'passed': True, 'input_identity': 'candidate'}], 'patch': 'saved edits',
            'findings': [{'id': 'real-defect'}], 'command_grants': ['authorized check'],
            'events': [], 'active_role': 'reviewer'}
        gateway = SimpleNamespace(settings={'base_url': provider['base_url']}, models=[{'id': 'new-review', 'free': True, 'tool_calling': True}])
        self.engine = SimpleNamespace(lock=threading.RLock(), store=MemoryStore(self.task), runtimes={},
            require_active_task=Mock(), guard_route=Mock(), connection_for=lambda _: gateway,
            start=Mock(), branch=SimpleNamespace(validate_authority=Mock(), resume=Mock(return_value={'task': {'id': 'a'}})))

    def request(self, patch=None, intent='apply', operation='one', revision=0):
        return {'patch': patch or {'limits.uncapped_work': True}, 'intent': intent,
                'expected_revision': revision, 'operation_id': operation}

    def make_branch(self):
        run_limits = {'dollars': 0, 'worker_turns': 40, 'working_seconds': 900, 'reviewer_tokens': 200000, 'output_tokens': 2048, 'check_seconds': 360}
        plan = {'limits': copy.deepcopy(run_limits), 'items': [{'id': '1', 'instructions': 'keep scope'}]}
        policy = {'execution': copy.deepcopy(self.task['execution']), 'providers': copy.deepcopy(self.task['providers']), 'spending': 'free'}
        self.task['branch_run'] = {'status': 'paused', 'current_item_id': None, 'stage': 'finalizing',
            'limits': run_limits, 'plan': plan, 'model_policy': policy,
            'authorization': {'id': 'auth', 'contract': {'plan': copy.deepcopy(plan), 'limits': copy.deepcopy(run_limits),
                                                       'model_policy': copy.deepcopy(policy), 'check_scope': ['original'], 'scope': 'same'}},
            'final_review_packets': {'chunk:1': {'result': {'decision': 'APPROVE'}, 'messages': ['failed attempt']}},
            'final_evidence': {'review_approved': True}, 'readiness': {'old': True},
            'review_disagreements': {'real': 'retain'}, 'items': [{'id': '1', 'status': 'committed'}]}
        self.engine.store = MemoryStore(self.task)

    def test_view_uses_approved_allowance_without_rewriting_snapshot(self):
        self.make_branch()
        task = self.engine.store.get('a')
        captured = {'execution': {'mode': 'remote'}, 'limits': {'worker_turns': 200,
                    'run_minutes': 90, 'dollars': 2}, 'roles': {'worker': {'strategy': 'automatic'}}}
        task['settings_snapshot'] = {'revision': 3, 'values': captured,
            'sources': {'limits.worker_turns': {'scope': 'app'}}}
        task['branch_run']['limits']['working_seconds'] = 901
        self.engine.store.save(task)
        before = self.engine.store.get('a')
        result = task_settings.view(self.engine, 'a')
        self.assertEqual(result['values']['limits']['worker_turns'], 40)
        self.assertEqual(result['values']['limits']['dollars'], 0)
        self.assertEqual(result['values']['limits']['run_minutes'], 901 / 60)
        self.assertEqual(result['approved_allowance']['working_seconds'], 901)
        self.assertEqual(result['sources']['limits.worker_turns'],
                         {'scope': 'task', 'provenance': 'approved_plan'})
        self.assertEqual(result['values']['roles']['worker'], {'strategy': 'automatic'})
        self.assertEqual(result['revision'], 3)
        self.assertEqual(self.engine.store.get('a'), before)

    def test_apply_is_one_record_and_does_not_touch_other_chat(self):
        self.engine.store.tasks['b'] = {**copy.deepcopy(self.task), 'id': 'b'}
        before_b = copy.deepcopy(self.engine.store.tasks['b'])
        result = task_settings.save(self.engine, 'a', self.request())
        self.assertTrue(result['saved'])
        self.assertFalse(result['continuing'])
        self.assertEqual(self.engine.store.writes, 1)
        self.assertEqual(self.engine.store.tasks['b'], before_b)
        saved = self.engine.store.get('a')
        for key in ('checks', 'usage', 'patch', 'command_grants', 'findings'):
            self.assertEqual(saved[key], self.task[key])
        self.assertEqual(saved['settings_snapshot']['sources']['limits.uncapped_work']['scope'], 'task')

    def test_selected_budget_increase_continues_exact_saved_review_without_reset(self):
        from cheapos.work_budgets import guard
        from cheapos.providers import BudgetError
        self.make_branch()
        task = self.engine.store.get('a')
        task['limits'].update(work_policy_version=2, work_requests=2)
        task['branch_run']['plan']['limits'].update(work_policy_version=2,work_requests=2)
        task['session_actions']={'coverage':'complete','counts':{'worker':2,'tools':4}}
        with self.assertRaises(BudgetError): guard(task,additions={'work_requests':1})
        self.engine.store.save(task)
        original=copy.deepcopy(task)
        request=self.request({'limits.work_requests':3},intent='apply-and-continue')
        result=task_settings.save(self.engine,'a',request)
        self.assertTrue(result['continuing'])
        task_settings.save(self.engine,'a',request)
        self.engine.branch.resume.assert_called_once_with('a',{})
        saved=self.engine.store.get('a');guard(saved,additions={'work_requests':1})
        for key in ('session_actions','checks','usage','command_grants','findings'):
            self.assertEqual(saved[key],original[key])
        self.assertEqual(saved['branch_run']['final_review_packets'],original['branch_run']['final_review_packets'])
        self.assertEqual(saved['branch_run']['authorization']['contract']['limits']['work_requests'],3)

    def test_explicit_planning_budget_change_survives_restore_without_authorizing_work(self):
        from cheapos.branch_controller import run_limits, restore_planning_allowance
        task=copy.deepcopy(self.task)
        task['planning_request']={'prompt':'Keep the captured work'}
        task['planning_limits']=run_limits({},3)
        task['limits'].update({key:task['planning_limits'][key] for key in ('dollars','reviewer_tokens','output_tokens')})
        task['planning_task_limits']=copy.deepcopy(task['limits'])
        task['branch_run']={'status':'paused','stage':'planning','limits':copy.deepcopy(task['planning_limits']),
                           'plan':{'limits':copy.deepcopy(task['planning_limits'])},'consumption':{'requests':2}}
        self.engine.store=MemoryStore(task)
        result=task_settings.save(self.engine,'a',self.request({'limits.work_policy_version':2,'limits.work_requests':3},intent='apply-and-continue'))
        self.assertTrue(result['continuing'])
        saved=self.engine.store.get('a');restore_planning_allowance(saved)
        self.assertEqual(saved['planning_limits']['work_requests'],3)
        self.assertEqual(saved['limits']['work_requests'],3)
        self.assertEqual(saved['branch_run']['consumption'],{'requests':2})
        self.assertNotIn('authorization',saved['branch_run'])
        self.assertEqual(saved['planning_request'],task['planning_request'])

    def test_replay_does_not_redispatch(self):
        request = self.request(intent='apply-and-continue')
        first = task_settings.save(self.engine, 'a', request)
        self.assertEqual(task_settings.save(self.engine, 'a', request), first)
        self.engine.start.assert_called_once_with('a', {})
        self.assertTrue(first['continuing'])
        with self.assertRaisesRegex(ValueError, 'different settings'):
            task_settings.save(self.engine, 'a', {**request, 'patch': {'limits.dollars': 1}})

    def test_invalid_combined_patch_has_no_partial_write(self):
        before = copy.deepcopy(self.engine.store.tasks)
        with self.assertRaises(ValueError):
            task_settings.save(self.engine, 'a', self.request({'limits.dollars': 1, 'execution.coordinator_assistance': 'yes'}))
        self.assertEqual(self.engine.store.tasks, before)
        self.assertEqual(self.engine.store.writes, 0)

    def test_stale_or_active_edits_preserve_draft_and_task(self):
        with self.assertRaises(SettingsConflict):
            task_settings.save(self.engine, 'a', self.request(revision=99))
        self.engine.runtimes['a'] = SimpleNamespace(thread=SimpleNamespace(is_alive=lambda: True))
        current = task_settings.view(self.engine, 'a')
        self.assertTrue(current['capabilities']['pause_to_apply'])
        self.assertFalse(current['capabilities']['pause_apply_and_continue'])
        with self.assertRaisesRegex(ValueError, 'Pause to apply'):
            task_settings.save(self.engine, 'a', self.request())
        self.assertEqual(self.engine.store.writes, 0)

    def test_failed_dispatch_reports_saved_separately(self):
        self.engine.start.side_effect = ValueError('waiting for provider')
        result = task_settings.save(self.engine, 'a', self.request(intent='apply-and-continue'))
        self.assertTrue(result['saved'])
        self.assertTrue(result['pending'])
        self.assertFalse(result['continuing'])
        self.assertEqual(result['reason'], 'waiting for provider')
        saved = self.engine.store.get('a')
        self.assertTrue(saved['limits']['uncapped_work'])
        self.assertEqual(saved['settings_operations']['one']['stage'], 'waiting')

    def test_reviewer_change_continues_final_review_and_retains_evidence(self):
        self.make_branch()
        result = task_settings.save(self.engine, 'a', self.request({'roles.reviewer': {'strategy': 'only', 'model': 'new-review', 'connection_id': 'default'}}, intent='apply-and-continue'))
        saved = self.engine.store.get('a')
        self.assertTrue(result['continuing'])
        self.engine.branch.resume.assert_called_once_with('a', {})
        self.engine.start.assert_not_called()
        self.assertEqual(saved['branch_run']['stage'], 'finalizing')
        self.assertIsNone(saved['branch_run']['current_item_id'])
        self.assertEqual(saved['active_role'], 'reviewer')
        self.assertEqual(saved['checks'], self.task['checks'])
        self.assertEqual(saved['findings'], self.task['findings'])
        self.assertEqual(saved['usage'], self.task['usage'])
        self.assertEqual(saved['branch_run']['review_disagreements'], {'real': 'retain'})
        self.assertEqual(saved['branch_run']['final_review_packets'], {})
        self.assertTrue(saved['branch_run']['final_review_packet_history'])
        self.assertEqual(saved['branch_run']['authorization']['contract']['check_scope'], ['original'])
        self.assertEqual(saved['providers']['reviewer']['model'], 'new-review')

    def test_reviewer_provider_metadata_belongs_to_new_route(self):
        from cheapos.request_pacer import provider_identity
        self.task['providers']['reviewer']['provider'] = 'nvidia'
        gateway = self.engine.connection_for({})
        for metadata in ({'provider': 'groq'}, {}):
            gateway.models = [{'id': 'groq/new-review', 'free': True, 'tool_calling': True, **metadata}]
            with self.subTest(metadata=metadata):
                cfg = task_settings.reviewer_config(self.engine, self.task,
                    {'strategy': 'only', 'model': 'groq/new-review', 'connection_id': 'default'})
                self.assertEqual(provider_identity(cfg), 'groq')
                self.assertEqual(cfg.get('provider'), metadata.get('provider'))
                self.assertEqual(self.task['providers']['reviewer']['provider'], 'nvidia')

    def test_persisted_pending_continuation_dispatches_once_after_restart(self):
        task_settings.save(self.engine, 'a', self.request())
        task = self.engine.store.get('a')
        operation = task['settings_operations']['one']
        operation.update(stage='pending', intent='apply-and-continue')
        operation['result']['pending'] = True
        self.engine.store.save(task)
        result = task_settings.continue_operation(self.engine, 'a', 'one')
        self.assertTrue(result['continuing'])
        task_settings.continue_operation(self.engine, 'a', 'one')
        self.engine.start.assert_called_once_with('a', {})

    def test_interrupted_dispatch_is_not_blindly_repeated(self):
        task_settings.save(self.engine, 'a', self.request())
        task = self.engine.store.get('a')
        task['settings_operations']['one']['stage'] = 'dispatching'
        self.engine.store.save(task)
        task_settings.continue_operation(self.engine, 'a', 'one')
        self.engine.start.assert_not_called()

    def test_forbidden_placement_and_worker_edits_never_apply(self):
        for patch in ({'execution.mode': 'local'}, {'roles.worker': {'strategy': 'automatic'}}, {'command_grants': ['everything']}):
            with self.assertRaisesRegex(ValueError, 'cannot be changed'):
                task_settings.save(self.engine, 'a', self.request(patch))
        self.assertEqual(self.engine.store.writes, 0)

    def test_branch_limit_update_retains_consumption_and_scope(self):
        self.make_branch()
        self.task['branch_run']['consumption'] = {'worker_turns': 30}
        self.engine.store = MemoryStore(self.task)
        task_settings.save(self.engine, 'a', self.request({'limits.worker_turns': 10, 'limits.dollars': 0}))
        saved = self.engine.store.get('a')
        self.assertEqual(saved['branch_run']['limits']['worker_turns'], 10)
        self.assertEqual(saved['branch_run']['consumption']['worker_turns'], 30)
        self.assertEqual(saved['branch_run']['authorization']['contract']['plan']['items'], self.task['branch_run']['plan']['items'])
        self.assertEqual(saved['status'], 'paused')
