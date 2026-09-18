import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from cheapos import reviewer_recovery as recovery
from cheapos.providers import ProviderError
from cheapos.served_identity import ensure_independent, metadata


class ReviewerRecoveryTests(unittest.TestCase):
    def fixture(self):
        task = {'execution': {'mode': 'remote'}, 'route': {},
                'providers': {'worker': {'model': 'worker'}, 'reviewer': {'model': 'old'}},
                'patch': 'saved', 'checks': [{'passed': True}], 'pending_review': {'messages': ['saved']}}
        engine = SimpleNamespace(_request_routed=Mock(side_effect=ProviderError('identity', code='review_identity_unknown')),
                                 _request=Mock(return_value={'content': 'review'}), store=Mock(), event=Mock())
        def routed(runtime, messages, tools, role, override=None, purpose=None, **kwargs):
            if override is not None: return engine._request(runtime,messages,tools,role,override,purpose,**kwargs)
            raise ProviderError('identity', code='review_identity_unknown')
        engine._request_routed.side_effect = routed
        task['route'] = {'base_url': 'gateway'}
        return engine, SimpleNamespace(task=task, guard=Mock())

    def test_recovery_preserves_work_and_reuses_verified_selection(self):
        engine, runtime = self.fixture()
        before = copy.deepcopy(runtime.task)
        with patch.object(recovery, 'candidates', return_value=[{'id': 'next'}]), patch.object(recovery, 'config', return_value={'model': 'next'}):
            recovery.request(engine, runtime, ['review context'], [], 'reviewer')
            recovery.request(engine, runtime, ['review context'], [], 'reviewer')
        self.assertEqual(engine._request_routed.call_count, 3)
        self.assertEqual(engine._request.call_count, 2)
        for key in ('patch', 'checks', 'pending_review'):
            self.assertEqual(runtime.task[key], before[key])
        self.assertEqual(runtime.task['reviewer_identity_recovery']['selected'], 'next')

    def test_exhausted_continue_does_not_replay_failed_routes(self):
        engine, runtime = self.fixture()
        engine._request.side_effect = ProviderError('same', code='review_identity_conflict')
        with patch.object(recovery, 'candidates', return_value=[{'id': 'next'}]), patch.object(recovery, 'config', return_value={'model': 'next'}):
            for _ in range(2):
                with self.assertRaises(ProviderError) as caught:
                    recovery.request(engine, runtime, [], [], 'reviewer')
                self.assertEqual(caught.exception.code, 'reviewer_recovery_required')
        self.assertEqual(engine._request.call_count, 1)
        self.assertEqual(engine._request_routed.call_count, 2)

    def test_manual_and_unknown_history_do_not_spend_on_alternatives(self):
        for unknown in (False, True):
            engine, runtime = self.fixture()
            runtime.task['execution']['mode'] = 'manual'
            if unknown:
                runtime.task['request_metrics'] = [{'role': 'worker', 'dispatched': True, 'model': 'auto/coding'}]
            with self.assertRaises(ProviderError):
                recovery.request(engine, runtime, [], [], 'reviewer')
            engine._request.assert_not_called()

    def test_access_and_outage_errors_are_not_mislabeled_as_identity_failures(self):
        for code in ('http_401', 'http_402'):
            engine, runtime = self.fixture()
            error = ProviderError('Original diagnosis', code=code)
            engine._request.side_effect = error
            with patch.object(recovery, 'candidates', return_value=[{'id': 'next'}, {'id': 'another'}]), patch.object(
                    recovery, 'config', return_value={'model': 'next'}), self.assertRaises(ProviderError) as caught:
                recovery.request(engine, runtime, [], [], 'reviewer')
            self.assertIs(caught.exception, error)
            engine._request.assert_called_once()
            self.assertEqual(runtime.task['checks'], [{'passed': True}])

    def test_saved_selection_dispatches_once_without_repeating_identity_failure(self):
        engine,runtime=self.fixture()
        runtime.task['reviewer_identity_recovery']={'attempted':['old','next'], 'next_action':{'model':'next','status':'selected'}}
        with patch.object(recovery,'candidates',return_value=[{'id':'next'}]), patch.object(recovery,'config',return_value={'model':'next'}):
            recovery.request(engine,runtime,[],[],'reviewer')
        engine._request.assert_called_once()
        self.assertEqual(runtime.task['reviewer_identity_recovery']['next_action']['status'],'completed')

    def test_recovery_requires_reported_identity_and_rejects_same_author(self):
        task = {'served_identity_version': 1, 'reviewer_identity_recovery': {'attempted': ['old']},
                'request_metrics': [{'role': 'worker', 'dispatched': True, **metadata('worker', 'actual/worker')}]}
        for served in (None, 'actual/worker'):
            with self.assertRaises(ProviderError):
                ensure_independent(task, {'role': 'reviewer', **metadata('next', served)})
        ensure_independent(task, {'role': 'reviewer', **metadata('next', 'actual/reviewer')})

    def test_unavailable_identity_replacement_continues_to_independent_reviewer(self):
        engine,runtime=self.fixture()
        engine._request.side_effect=[ProviderError('outage',code='http_503'),{'content':'approved'}]
        with patch.object(recovery,'candidates',return_value=[{'id':'next'},{'id':'another'}]), patch.object(recovery,'config',side_effect=lambda e,t,m:{'model':m}):
            result=recovery.request(engine,runtime,[],[],'reviewer')
        self.assertEqual(result['content'],'approved')
        self.assertEqual(engine._request.call_count,2)
        self.assertEqual(runtime.task['providers']['reviewer']['model'],'another')
        self.assertEqual(runtime.task['checks'],[{'passed':True}])
        self.assertNotIn('next',runtime.task['reviewer_identity_recovery']['attempted'])
