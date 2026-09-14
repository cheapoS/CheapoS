import copy
import json
import unittest
import threading
from unittest.mock import patch

from cheapos.providers import ProviderError, validate_provider
from cheapos.startup import GREETING, catalog_candidates, local_candidates
from test_engine import LocalCase


def candidate(name='local-coder', gateway='openai', local=True):
    config=validate_provider({'base_url':'http://127.0.0.1:11434/v1' if gateway=='openai' else 'http://127.0.0.1:20128/v1', 'model':name, 'gateway':gateway, 'input_rate':0, 'output_rate':0},'worker')
    return {'config':config,'local':local,'transport':'Local Ollama' if gateway=='openai' else 'OmniRoute'}


class StartupTests(LocalCase):
    def setUp(self):
        super().setUp()
        self.locals=patch('cheapos.startup.local_candidates',return_value=[]).start()
        self.omni=patch.object(self.engine.startup,'_omni',return_value=[]).start()
        self.addCleanup(patch.stopall)
        self.calls=[]
        test=self
        class Provider:
            def greet(self,messages,emit,stopped):
                test.calls.append(copy.deepcopy(messages))
                emit('answer','Hi! Open a project to begin.')
                return {'content':'Hi! Open a project to begin.'},{'prompt_tokens':25,'completion_tokens':8,'cost':0}
        self.engine.provider_factory=lambda *args:Provider()

    def run_startup(self, automatic=False):
        self.engine.startup.start(automatic=automatic)
        if self.engine.startup.thread:self.engine.startup.thread.join(5)
        self.assertFalse(self.engine.startup.busy())
        return self.engine.startup.snapshot()

    def test_fresh_local_startup_greets_without_a_project_and_sets_both_free_roles(self):
        self.locals.return_value=[candidate()]
        state=self.run_startup(automatic=True)
        self.assertEqual(state['status'],'ready')
        self.assertEqual(state['content'],'Hi! Open a project to begin.')
        self.assertEqual(self.calls,[GREETING])
        self.assertEqual(self.engine.store.list(),[])
        self.assertEqual(self.engine.config['worker']['model'],'local-coder')
        self.assertEqual(self.engine.config['reviewer']['model'],'local-coder')
        self.assertEqual(state['usage']['worker']['tokens'],33)
        self.assertEqual(state['usage']['cost'],0)
        self.assertEqual(state['usage']['uncertain_requests'],0)
        self.assertNotIn('messages',json.loads((self.root/'state/startup-last.json').read_text()))

    def test_reading_boot_status_never_repeats_inference(self):
        self.locals.return_value=[candidate()]
        self.run_startup()
        for _ in range(10):self.engine.startup.snapshot()
        self.assertEqual(len(self.calls),1)

    def test_free_cloud_requires_opt_in_on_a_fresh_install(self):
        self.omni.return_value=[candidate('openrouter/coder:free','omniroute',False)]
        state=self.run_startup()
        self.assertEqual(state['status'],'unavailable')
        self.assertEqual(self.calls,[])
        self.engine.startup.configure({'allow_cloud':True})
        self.assertEqual(self.run_startup()['status'],'ready')
        self.assertEqual(self.engine.config['worker']['gateway'],'omniroute')

    def test_saved_omniroute_choice_has_priority_over_local_and_keeps_reviewer(self):
        chosen=candidate('openrouter/saved:free','omniroute',False)
        self.engine.config={'worker':chosen['config'],'reviewer':candidate('reviewer')['config']}
        self.locals.return_value=[candidate()]
        self.omni.return_value=[chosen]
        result=self.run_startup()
        self.assertEqual(result['model']['id'],'openrouter/saved:free')
        self.assertEqual(self.engine.config['reviewer']['model'],'reviewer')

    def test_auto_selection_does_not_rewrite_saved_task_models(self):
        task=self.fixture(paid=True)
        before=copy.deepcopy(task['providers'])
        self.locals.return_value=[candidate()]
        self.run_startup()
        self.assertEqual(self.engine.store.get(task['id'])['providers'],before)

    def test_paid_and_combo_saved_choices_are_never_used_for_a_greeting(self):
        for name,price in [('paid',1),('auto/free',0)]:
            self.engine.config['worker']={**candidate(name)['config'],'input_rate':price}
            self.locals.return_value=[candidate()]
            self.assertEqual(self.run_startup(automatic=True)['status'],'configured')
            self.assertEqual(self.engine.config['worker']['model'],name)
        self.assertEqual(self.calls,[])

    def test_explicit_free_connect_can_replace_a_saved_paid_worker_without_calling_it(self):
        self.engine.config['worker']={**candidate('paid')['config'],'input_rate':1}
        self.locals.return_value=[candidate('free-local')]
        self.assertEqual(self.run_startup()['model']['id'],'free-local')
        self.assertEqual(self.engine.config['worker']['model'],'free-local')
        self.assertEqual(len(self.calls),1)

    def test_failed_or_incomplete_greeting_never_claims_ready_or_executes_tools(self):
        self.locals.return_value=[candidate()]
        class BadProvider:
            def greet(self,*args):
                return {'content':'Hi','tool_calls':[{'function':{'name':'write_file'}}]},{}
        self.engine.provider_factory=lambda *args:BadProvider()
        state=self.run_startup()
        self.assertEqual(state['status'],'unavailable')
        self.assertIsNone(self.engine.config['worker'])
        self.assertEqual(state['usage']['uncertain_requests'],1)
        self.assertEqual(self.engine.store.list(),[])

    def test_failover_is_bounded_and_never_retries_the_same_candidate(self):
        self.engine.startup.configure({'allow_cloud':True})
        self.locals.return_value=[candidate('a'),candidate('a'),candidate('b')]
        self.omni.return_value=[candidate('c','omniroute',False),candidate('d','omniroute',False)]
        called=[]
        class FailedProvider:
            def greet(self,*args):
                called.append(True)
                raise ProviderError('Unavailable')
        self.engine.provider_factory=lambda *args:FailedProvider()
        state=self.run_startup()
        self.assertEqual(len(called),3)
        self.assertEqual(len(state['attempts']),3)
        self.assertEqual(state['usage']['uncertain_requests'],3)

    def test_reported_charge_disables_automatic_startup_and_stops_failover(self):
        self.locals.return_value=[candidate('a'),candidate('b')]
        class PaidProvider:
            def greet(self,*args):return {'content':'Hi'},{'prompt_tokens':1,'completion_tokens':1,'cost':.01}
        self.engine.provider_factory=lambda *args:PaidProvider()
        state=self.run_startup()
        self.assertEqual(state['status'],'unavailable')
        self.assertFalse(state['settings']['enabled'])
        self.assertEqual(len(state['attempts']),1)
        self.assertAlmostEqual(state['usage']['cost'],.01)
        self.assertFalse(json.loads((self.root/'state/startup.json').read_text())['enabled'])

    def test_disabled_startup_and_preference_saving_make_no_requests(self):
        self.locals.return_value=[candidate()]
        self.engine.startup.configure({'enabled':False,'allow_cloud':True})
        self.assertEqual(self.run_startup(automatic=True)['status'],'disabled')
        self.assertEqual(self.calls,[])
        self.assertEqual(self.engine.config,{'worker':None,'reviewer':None})

    def test_reported_charge_with_missing_tokens_also_stops_fallback(self):
        self.locals.return_value=[candidate('a'),candidate('b')]
        class PaidProvider:
            def greet(self,*args):return {'content':'Hi'},{'cost':.01}
        self.engine.provider_factory=lambda *args:PaidProvider()
        state=self.run_startup()
        self.assertFalse(state['settings']['enabled'])
        self.assertEqual(len(state['attempts']),1)
        self.assertAlmostEqual(state['usage']['cost'],.01)

    def test_stop_and_concurrent_start_cannot_duplicate_dispatch_or_commit_a_model(self):
        entered,release=threading.Event(),threading.Event()
        count=[]
        class WaitingProvider:
            def greet(self,messages,emit,stopped):
                count.append(1);entered.set();release.wait(5)
                if stopped():raise InterruptedError()
                return {'content':'Hi'},{'prompt_tokens':1,'completion_tokens':1}
        self.engine.provider_factory=lambda *args:WaitingProvider()
        self.locals.return_value=[candidate()]
        task=self.fixture()
        self.engine.startup.start()
        try:
            self.assertTrue(entered.wait(2))
            self.engine.startup.start()
            with self.assertRaises(ValueError):self.engine.start(task['id'])
            with self.assertRaises(ValueError):self.engine.configure({role:candidate()['config'] for role in ['worker','reviewer']})
            self.engine.startup.stop()
        finally:release.set()
        self.engine.startup.thread.join(5)
        self.assertEqual(count,[1])
        self.assertEqual(self.engine.startup.snapshot()['status'],'stopped')
        self.assertIsNone(self.engine.config['worker'])

    def test_catalog_selection_requires_free_prices_and_advertised_tools(self):
        entries=[{'id':'free-tools','free':True,'tool_calling':True}, {'id':'chat-only','free':True,'tool_calling':False}, {'id':'unknown','free':False,'tool_calling':True}, {'id':'unknown-tools','free':True,'tool_calling':None}]
        self.assertEqual([c['config']['model'] for c in catalog_candidates(entries,'http://127.0.0.1:20128/v1','omniroute')],['free-tools'])


class LocalDiscoveryTests(LocalCase):
    def test_retry_refreshes_a_previously_offline_gateway(self):
        gateway=self.engine.gateway
        gateway._set_state('offline','Offline')
        model={'id':'openrouter/coder:free','free':True,'tool_calling':True}
        def connect():gateway._set_state('ready','Connected',[model])
        with patch.object(gateway,'startup',side_effect=connect) as start:
            candidates=self.engine.startup._omni()
        start.assert_called_once()
        self.assertEqual(candidates[0]['config']['model'],'openrouter/coder:free')

    def test_only_installed_tool_models_are_selected_and_loaded_model_is_first(self):
        seen=[]
        def respond(url,body=None):
            seen.append((url,body))
            if url.endswith('/tags'):return {'models':[{'name':'small','size':1},{'name':'loaded','size':10},{'name':'chat-only','size':1}]}
            if url.endswith('/ps'):return {'models':[{'name':'loaded'}]}
            return {'capabilities':['completion']+([] if body['model']=='chat-only' else ['tools'])}
        with patch('cheapos.startup.local_json',side_effect=respond):
            models=local_candidates()
        self.assertEqual([m['config']['model'] for m in models],['loaded','small'])
        self.assertTrue(all('/api/' in url and not url.endswith('/pull') for url,body in seen))


class PreferredLocalDiscoveryTests(unittest.TestCase):
    def test_saved_local_choice_is_inspected_even_with_six_smaller_models(self):
        def respond(url, body=None):
            if url.endswith('/tags'):
                return {'models':[{'name':'small-'+str(i),'size':1} for i in range(7)]+[{'name':'gemma4:31b','size':100}]}
            if url.endswith('/ps'): return {'models':[]}
            return {'capabilities':['completion','tools']}
        with patch('cheapos.startup.local_json',side_effect=respond):
            candidates=local_candidates(preferred=['gemma4:31b'])
        self.assertEqual(candidates[0]['config']['model'],'gemma4:31b')
        self.assertEqual(len(candidates),6)
