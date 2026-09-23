import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from cheapos import reviewer_recovery as recovery
from cheapos.providers import ProviderError
from cheapos.served_identity import ensure_independent, metadata


class ReviewerRecoveryTests(unittest.TestCase):
    def recorded_success(self, model='next', **extra):
        return {'id': 'request-' + model, 'role': 'reviewer', 'model': model, 'purpose': 'branch_final',
                'status': 'responded', 'dispatched': True, 'synthetic': False,
                'served_model': 'actual/' + model, 'identity_provenance': 'response_model',
                'dispatch_scope': {'base_url': 'gateway', 'connection_revision': 'saved',
                                   'model': model, 'role': 'reviewer'}, **extra}

    def recorded_fixture(self):
        engine, runtime = self.fixture()
        task = runtime.task
        task['served_identity_version'] = 1
        task['providers']['reviewer'].update(base_url='gateway', access_binding={'connection_revision': 'saved'})
        task['reviewer_identity_recovery'] = {'attempted': ['old', 'next'], 'scope': 'manifest:tree'}
        task['branch_run'] = {'current_item_id': None, 'active_final_review': {'manifest_id': 'tree'}}
        task['request_metrics'] = [self.recorded_success()]
        return engine, runtime

    def test_legacy_success_survives_resume_without_erasing_attempt_history(self):
        engine, rt = self.recorded_fixture()
        before = copy.deepcopy(rt.task)
        with patch.object(recovery, 'candidates', return_value=[{'id': 'next'}]), patch.object(
                recovery, 'config', return_value={'model': 'next'}):
            self.assertEqual(recovery.request(engine, rt, ['current evidence'], [], 'reviewer')['content'], 'review')
            rt.task = copy.deepcopy(rt.task)
            recovery.request(engine, rt, ['current evidence'], [], 'reviewer')
        self.assertEqual(engine._request.call_count, 2)
        self.assertEqual(rt.task['reviewer_identity_recovery']['attempted'], ['old', 'next'])
        self.assertEqual(rt.task['reviewer_identity_recovery']['verified_routes']['next'], {'request_id': 'request-next'})
        for key in ('patch', 'checks', 'request_metrics', 'pending_review', 'execution'):
            self.assertEqual(rt.task[key], before[key])

    def test_migration_never_uses_probe_unknown_or_other_connection_as_identity_proof(self):
        variants = [{'purpose': 'probe'}, {'status': 'pending'}, {'status': 'failed'},
            {'error_code': 'review_identity_conflict'}, {'synthetic': True}, {'synthetic': None},
            {'served_model': None}, {'identity_provenance': 'configured_named_routes'},
            {'dispatched': False}, {'dispatch_scope': {}},
            {'dispatch_scope': {'base_url': 'other', 'connection_revision': 'saved', 'model': 'next', 'role': 'reviewer'}},
            {'dispatch_scope': {'base_url': 'gateway', 'connection_revision': 'old', 'model': 'next', 'role': 'reviewer'}}]
        for extra in variants:
            with self.subTest(record=extra):
                _, rt = self.recorded_fixture()
                rt.task['request_metrics'] = [self.recorded_success(**extra)]
                self.assertEqual(recovery.bind_recovery(rt.task)['verified_routes'], {})

    def test_later_failures_survive_successful_probe_and_restart(self):
        for code in ('review_identity_unknown', 'review_identity_conflict', 'http_400', 'invalid_response_json'):
            with self.subTest(code=code):
                engine, rt = self.recorded_fixture()
                rt.task['request_metrics'] += [self.recorded_success(status='failed', error_code=code),
                                               self.recorded_success(purpose='probe')]
                with patch.object(recovery, 'candidates', return_value=[{'id': 'next'}]):
                    for _ in range(2):
                        with self.assertRaises(ProviderError): recovery.request(engine, rt, [], [], 'reviewer')
                        rt.task = copy.deepcopy(rt.task)
                engine._request.assert_not_called()

    def test_new_identity_failure_revokes_restored_success_without_remigration(self):
        engine, rt = self.recorded_fixture()
        engine._request.side_effect = ProviderError('identity', code='review_identity_conflict')
        with patch.object(recovery, 'candidates', return_value=[{'id': 'next'}]), patch.object(
                recovery, 'config', return_value={'model': 'next'}):
            for _ in range(2):
                with self.assertRaises(ProviderError): recovery.request(engine, rt, [], [], 'reviewer')
                rt.task = copy.deepcopy(rt.task)
        engine._request.assert_called_once()
        self.assertEqual(rt.task['reviewer_identity_recovery']['verified_routes'], {})

    def test_verified_route_still_respects_manual_selection_and_cooldown(self):
        for blocked in ('manual', 'cooldown'):
            with self.subTest(blocked=blocked):
                engine, rt = self.recorded_fixture()
                if blocked == 'manual': rt.task['execution']['mode'] = 'manual'
                with patch.object(recovery, 'candidates', return_value=[] if blocked == 'cooldown' else [{'id': 'next'}]):
                    with self.assertRaises(ProviderError): recovery.request(engine, rt, [], [], 'reviewer')
                engine._request.assert_not_called()

    def fixture(self):
        # These cases exercise identity/availability recovery after qualification.
        qualification = patch.object(recovery, 'qualify', return_value=True)
        qualification.start(); self.addCleanup(qualification.stop)
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

    def test_new_candidate_can_use_prior_route_without_erasing_failed_attempt(self):
        engine, runtime = self.fixture()
        task = runtime.task
        task['pending_review']['branch_candidate_id'] = 'first'
        engine._request.side_effect = ProviderError('identity', code='review_identity_unknown')
        with patch.object(recovery, 'candidates', return_value=[{'id': 'next'}]), patch.object(
                recovery, 'config', return_value={'model': 'next'}):
            for _ in range(2):
                with self.assertRaises(ProviderError): recovery.request(engine, runtime, [], [], 'reviewer')
                runtime.task = copy.deepcopy(runtime.task)
            self.assertEqual(engine._request.call_count, 1)
            runtime.task['pending_review']['branch_candidate_id'] = 'second'
            before = copy.deepcopy(runtime.task)
            engine._request.side_effect = None
            engine._request.return_value = {'content': 'approved'}
            self.assertEqual(recovery.request(engine, runtime, ['saved evidence'], [], 'reviewer')['content'], 'approved')
            state = runtime.task['reviewer_identity_recovery']
            self.assertEqual(state['scope'], 'item:second')
            self.assertEqual(state['history']['item:first']['attempted'], ['old', 'next'])
            for key in ('patch', 'checks', 'pending_review', 'execution'):
                self.assertEqual(runtime.task[key], before[key])
            # Returning to the old candidate restores its exclusions, not a new allowance.
            runtime.task['pending_review']['branch_candidate_id'] = 'first'
            with self.assertRaises(ProviderError): recovery.request(engine, runtime, [], [], 'reviewer')
            self.assertEqual(engine._request.call_count, 2)

    def test_legacy_candidate_migration_retains_unknown_and_current_failures(self):
        engine, runtime = self.fixture()
        task = runtime.task
        task['pending_review']['branch_candidate_id'] = 'current'
        task['reviewer_identity_recovery'] = {'attempted': ['next', 'unknown', 'current-failure'],
            'next_action': {'model': 'next', 'status': 'selected'}}
        task['request_metrics'] = [
            {'role': 'reviewer', 'model': 'next', 'review_candidate_id': 'older'},
            {'role': 'reviewer', 'model': 'next', 'purpose': 'probe'},
            {'role': 'reviewer', 'model': 'current-failure', 'review_candidate_id': 'current'}]
        old = copy.deepcopy(task['reviewer_identity_recovery'])
        with patch.object(recovery, 'candidates', return_value=[{'id': 'next'}]), patch.object(
                recovery, 'config', return_value={'model': 'next'}):
            recovery.request(engine, runtime, [], [], 'reviewer')
        state = task['reviewer_identity_recovery']
        self.assertEqual(state['history']['legacy'], old)
        self.assertEqual(state['attempted'], ['unknown', 'current-failure', 'next'])
        self.assertEqual(state['selected'], 'next')
        engine._request.assert_called_once()

    def test_manifest_scope_stays_fixed_across_chunks_and_resume(self):
        _, runtime = self.fixture()
        task = runtime.task
        task['branch_run'] = {'current_item_id': None,
                              'active_final_review': {'manifest_id': 'tree', 'key': 'chunk1'}}
        task['reviewer_identity_recovery'] = {'attempted': ['failed'], 'scope': 'manifest:tree'}
        for key in ('chunk2', 'synthesis'):
            task = copy.deepcopy(task)
            task['branch_run']['active_final_review']['key'] = key
            self.assertIs(recovery.bind_recovery(task), task['reviewer_identity_recovery'])
            self.assertEqual(task['reviewer_identity_recovery']['attempted'], ['failed'])
        task['branch_run']['active_final_review']['manifest_id'] = 'new-tree'
        self.assertEqual(recovery.bind_recovery(task)['attempted'], [])
        self.assertEqual(task['reviewer_identity_recovery']['history']['manifest:tree']['attempted'], ['failed'])

    def test_unknown_legacy_provenance_never_clears_attempts(self):
        _, runtime = self.fixture()
        task = runtime.task
        task['reviewer_identity_recovery'] = {'attempted': ['failed']}
        task['pending_review']['branch_candidate_id'] = 'current'
        task['request_metrics'] = [{'role': 'reviewer', 'model': 'failed'}]
        self.assertEqual(recovery.bind_recovery(task)['attempted'], ['failed'])

    def test_older_identity_error_does_not_seed_current_candidate_exclusion(self):
        engine, runtime = self.fixture()
        task = runtime.task
        task['pending_review']['branch_candidate_id'] = 'current'
        task['request_metrics'] = [{'role': 'reviewer', 'model': 'old',
            'error_code': 'review_identity_unknown', 'review_candidate_id': 'older'}]
        engine._request_routed.side_effect = None
        engine._request_routed.return_value = {'content': 'review'}
        self.assertEqual(recovery.request(engine, runtime, [], [], 'reviewer')['content'], 'review')
        self.assertNotIn('reviewer_identity_recovery', task)
        engine._request_routed.assert_called_once()

    def test_recovery_preserves_work_and_reuses_verified_selection(self):
        engine, runtime = self.fixture()
        before = copy.deepcopy(runtime.task)
        with patch.object(recovery, 'candidates', return_value=[{'id': 'next'}]), patch.object(recovery, 'config', return_value={'model': 'next'}):
            recovery.request(engine, runtime, ['review context'], [], 'reviewer')
            runtime.task = copy.deepcopy(runtime.task)  # Saved selection survives Resume.
            recovery.request(engine, runtime, ['review context'], [], 'reviewer')
        engine.event.assert_called_once()
        self.assertEqual(engine._request_routed.call_count, 3)
        self.assertEqual(engine._request.call_count, 2)
        for key in ('patch', 'checks', 'pending_review'):
            self.assertEqual(runtime.task[key], before[key])
        self.assertEqual(runtime.task['reviewer_identity_recovery']['selected'], 'next')

    def test_replacement_config_uses_its_own_provider_and_preserves_connection(self):
        from cheapos.request_pacer import provider_identity
        engine,runtime=self.fixture()
        current={'model':'openrouter/old:free','provider':'openrouter',
                 'base_url':'http://localhost:1/v1','gateway':'omniroute',
                 'connection_id':'default','input_rate':0,'output_rate':0}
        runtime.task['providers']['reviewer']=current
        for extra in ({'provider':'opencode'}, {}):
            with self.subTest(metadata=extra):
                engine.gateway=SimpleNamespace(settings={},catalog=lambda **kw:{'models':[
                    {'id':'oc/reviewer',**extra}]})
                cfg=recovery.config(engine,runtime.task,'oc/reviewer')
                self.assertEqual(provider_identity(cfg),'opencode')
                self.assertEqual(cfg.get('provider'),extra.get('provider'))
                for key in ('base_url','gateway','connection_id'):
                    self.assertEqual(cfg[key],current[key])
                self.assertEqual(current['provider'],'openrouter')

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

    def test_restored_handoff_keeps_selected_route_but_still_checks_identity(self):
        for selected in ('old',None):
            with self.subTest(selected=selected):
                engine,runtime=self.fixture()
                runtime.task['providers']['reviewer']={'model':'handoff'}
                runtime.task['reviewer_identity_recovery']={'attempted':['old','denied'],
                    'next_action':{'model':'denied','status':'failed','error_code':'http_403'}}
                if selected:runtime.task['reviewer_identity_recovery']['selected']=selected
                runtime.task=copy.deepcopy(runtime.task)
                engine._request.side_effect=[ProviderError('unknown identity',code='review_identity_unknown'),{'content':'approved'}]
                with patch.object(recovery,'candidates',return_value=[{'id':'other'},{'id':'old'},{'id':'handoff'}]), \
                     patch.object(recovery,'config',side_effect=lambda e,t,m:{'model':m}):
                    self.assertEqual(recovery.request(engine,runtime,[],[],'reviewer')['content'],'approved')
                self.assertEqual([c.args[4]['model'] for c in engine._request.call_args_list],['handoff','other'])
                self.assertEqual(runtime.task['reviewer_identity_recovery']['attempted'],['old','denied','handoff','other'])

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

    def test_rejected_replacement_continues_with_same_final_review_evidence(self):
        for code in ('http_400','http_422','invalid_response_json','transport_retry_exhausted'):
            with self.subTest(code=code):
                engine,runtime=self.fixture();before=copy.deepcopy(runtime.task)
                messages=[{'role':'user','content':'Saved candidate, checks and counterevidence'}]
                engine._request.side_effect=[ProviderError('rejected',code=code),{'content':'approved'}]
                with patch.object(recovery,'candidates',return_value=[{'id':'next'},{'id':'another'}]), patch.object(
                        recovery,'config',side_effect=lambda e,t,m:{'model':m}):
                    result=recovery.request(engine,runtime,messages,[], 'reviewer',purpose='branch_final')
                self.assertEqual(result['content'],'approved')
                self.assertEqual(runtime.task['providers']['reviewer']['model'],'another')
                self.assertIn('next',runtime.task['reviewer_identity_recovery']['attempted'])
                for request in engine._request.call_args_list:
                    self.assertIs(request.args[1],messages);self.assertEqual(request.args[5],'branch_final')
                for key in ('patch','checks','pending_review'):
                    self.assertEqual(runtime.task[key],before[key])

    def test_shared_request_rejection_cannot_sweep_reviewer_pool(self):
        for scope in ('request','connection','account'):
            engine,runtime=self.fixture();error=ProviderError('private',code='http_400',scope=scope)
            engine._request.side_effect=error
            with patch.object(recovery,'candidates',return_value=[{'id':'next'},{'id':'another'}]), patch.object(
                    recovery,'config',return_value={'model':'next'}),self.assertRaises(ProviderError) as caught:
                recovery.request(engine,runtime,[],[],'reviewer')
            self.assertIs(caught.exception,error);engine._request.assert_called_once()

    def test_provider_cooldown_skips_remaining_sibling_reviewer(self):
        engine,runtime=self.fixture();cooling=set();pool=Mock()
        pool.observation.side_effect=lambda endpoint,model,revision: (
            {'cooling_down':True,'retry_at':12345678900,'cooldown_scope':'provider'}
            if model.split('/')[0] in cooling else {})
        pool.record.side_effect=lambda endpoint,model,role,**kwargs:cooling.add(model.split('/')[0])
        engine.connection_for=lambda cfg:SimpleNamespace(pool=pool)
        engine._request.side_effect=[ProviderError('backoff',code='gateway_cooldown',scope='provider',retry_after=60),{'content':'approved'}]
        with patch.object(recovery,'candidates',return_value=[{'id':'first/a'},{'id':'first/b'},{'id':'second/c'}]), patch.object(
                recovery,'config',side_effect=lambda e,t,m:{'model':m,'base_url':'gateway'}):
            result=recovery.request(engine,runtime,[],[],'reviewer')
        self.assertEqual(result['content'],'approved')
        self.assertEqual([call.args[4]['model'] for call in engine._request.call_args_list],['first/a','second/c'])
        self.assertNotIn('first/b',runtime.task['reviewer_identity_recovery']['attempted'])
