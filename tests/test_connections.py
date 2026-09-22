"""Small deterministic registry and failover cases; no Git runs or network."""
import copy
import json
import os
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import access_policy
from cheapos.connections import Connections
from cheapos.instructions.runtime import with_tools
from cheapos.omniroute import OmniRouteManager
from cheapos.providers import ProviderError
from cheapos.routing import _select_connections, RoutingPause, PROBE_MARKER


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{'CHEAPOS_GATEWAY_API_KEY':''});self.env.start();self.addCleanup(self.env.stop)
        self.default=OmniRouteManager(self.temp.name)
        self.registry=Connections(self.temp.name,self.default)
        self.other_id=self.registry.add({'name':'Alternate','gateway_type':'cliproxyapi','base_url':'http://127.0.0.1:8317/v1'})
        self.other=self.registry.managers[self.other_id]

    def model(self, identity):
        return {'id':identity,'free':True,'tool_calling':True,'input_rate':0,'output_rate':0}

    def test_selection_and_reload_preserve_separate_settings_and_keys(self):
        self.default.configure({'api_key':'first-fixture'})
        self.other.configure({'api_key':'second-fixture'})
        self.registry.select(self.other_id)
        self.assertEqual(self.registry.resolve({'connection_id':'default'},self.other).api_key,'first-fixture')
        self.assertEqual(self.registry.selected.api_key,'second-fixture')
        restored=Connections(self.temp.name,OmniRouteManager(self.temp.name))
        self.assertEqual(restored.selected_id,self.other_id)
        self.assertEqual(restored.selected.settings['name'],'Alternate')
        self.assertNotIn('fixture',self.registry.path.read_text())
        self.assertEqual(restored.selected.api_key,'')

    def test_disabled_and_new_connections_do_not_expand_saved_authority(self):
        captured=self.registry.capture()
        self.other.configure({'enabled':False})
        self.assertIsNone(self.registry.for_policy(captured[1]))
        with self.assertRaises(ValueError):self.registry.resolve({'connection_id':self.other_id},self.default)
        third=self.registry.add({'name':'Later','gateway_type':'compatible','base_url':'http://127.0.0.1:8320/v1'})
        with self.assertRaisesRegex(ValueError,'not authorized'):
            access_policy.for_config({'gateway_connections':captured},{'gateway':'omniroute','connection_id':third})

    def test_shared_quota_does_not_share_transport_failures(self):
        for manager,prefix in ((self.default,'provider'),(self.other,'alias')):
            manager.configure({'quota_groups':{prefix:'same-account'}})
        pool=self.registry.pool
        rev=self.default.settings['connection_revision'];other_rev=self.other.settings['connection_revision']
        pool.record(self.default.settings['base_url'],'provider/model','worker',connection_revision=rev,
                    error=ProviderError('offline',code='model_connection'))
        self.assertFalse(pool.observation(self.other.settings['base_url'],'alias/model',other_rev)['cooling_down'])
        pool.record(self.default.settings['base_url'],'provider/model','worker',connection_revision=rev,
                    error=ProviderError('quota',code='gateway_cooldown',scope='provider',retry_after=60))
        health=pool.observation(self.other.settings['base_url'],'alias/model',other_rev)
        self.assertTrue(health['cooling_down']);self.assertEqual(health['shared_quota_group'],'same-account')
        self.assertFalse(pool.observation(self.other.settings['base_url'],'unrelated/model',other_rev)['cooling_down'])

    def harness(self):
        captured=self.registry.capture()
        task={'gateway_connections':captured,'route':{'base_url':captured[0]['base_url'],'access_policy':access_policy.connection_policy(captured[0])},
              'providers':{},'events':[],'messages':[{'role':'user','content':'Keep my correction'}]}
        runtime=SimpleNamespace(task=task,failed_models=set(),guard=Mock(),stop=threading.Event())
        engine=SimpleNamespace(gateway=self.default,connections=self.registry,store=Mock(),event=Mock())
        engine.parse_call=lambda call:(call['function']['name'],json.loads(call['function']['arguments']))
        def probe(runtime,messages,tools,role,config_override,purpose):
            manager=self.registry.resolve(config_override,self.default)
            access_policy.guard(task,config_override,manager.settings,manager.models,role)
            return {'tool_calls':[{'function':{'name':'routing_ready','arguments':json.dumps({'marker':PROBE_MARKER})}}]}
        engine.request=Mock(side_effect=probe)
        for manager in (self.default,self.other):
            manager.models=[self.model('vendor/coder')]
            manager.catalog=Mock(side_effect=lambda fresh=False,m=manager:{'status':'ready','models':m.models})
        return engine,runtime

    def test_offline_first_connection_falls_through_without_resetting_session(self):
        engine,runtime=self.harness()
        self.default.catalog=Mock(return_value={'status':'offline','models':[]})
        before=copy.deepcopy(runtime.task['messages'])
        _select_connections(engine,runtime,'worker',False)
        cfg=runtime.task['providers']['worker']
        self.assertEqual(cfg['connection_id'],self.other_id)
        self.assertEqual(cfg['access_binding']['base_url'],self.other.settings['base_url'])
        self.assertEqual(runtime.task['messages'],before)
        self.assertEqual(engine.request.call_count,1)

    def test_exhausted_shared_account_is_skipped_before_probe(self):
        engine,runtime=self.harness()
        for manager in (self.default,self.other):
            manager.configure({'quota_groups':{'vendor':'same-account'}})
        runtime.task['gateway_connections']=self.registry.capture()
        self.registry.pool.record(self.default.settings['base_url'],'vendor/coder','worker',
            connection_revision=self.default.settings['connection_revision'],error=ProviderError('quota',code='gateway_cooldown',scope='account',retry_after=60))
        with self.assertRaises(RoutingPause):_select_connections(engine,runtime,'worker',False)
        engine.request.assert_not_called()

    def test_work_request_fails_over_with_usage_and_original_messages(self):
        from tests.test_transport import TransportTests
        from cheapos.engine import worker_system
        engine,runtime,_=TransportTests().harness()
        engine.connections=self.registry;engine.gateway=self.default
        engine.count_recovery_turn=Mock()
        runtime.failed_models=set();runtime.handoffs=0
        entries=self.registry.capture();policy=access_policy.connection_policy(entries[0])
        cfg={'gateway':'omniroute','gateway_type':'omniroute','connection_id':'default',
             'base_url':self.default.settings['base_url'],'model':'vendor/coder','input_rate':0,'output_rate':0,'access_binding':policy}
        task=runtime.task
        task.update(gateway_connections=entries,execution={'mode':'remote'},route={'base_url':cfg['base_url'],'access_policy':policy},providers={'worker':cfg})
        for manager in (self.default,self.other):
            manager.models=[self.model('vendor/coder')]
            manager.catalog=Mock(side_effect=lambda fresh=False,m=manager:{'status':'ready','models':m.models})
        calls=[]
        class Provider:
            streams_output=False
            def __init__(self,config):self.config=config
            def complete(self,messages,tools,maximum):
                calls.append((self.config['connection_id'],copy.deepcopy(messages)))
                if self.config['connection_id']=='default':raise ProviderError('auth',code='http_401')
                return {'content':'done'},{'prompt_tokens':3,'completion_tokens':2}
            def complete_brief(self,messages,tools,maximum,emit,stopped):
                return {'tool_calls':[{'id':'probe','type':'function','function':{'name':'routing_ready','arguments':json.dumps({'marker':PROBE_MARKER})}}]}, {'prompt_tokens':2,'completion_tokens':1}
        engine.provider_factory=lambda role,config:Provider(config)
        messages=[{'role':'user','content':'Keep these instructions'}]
        result=engine._request_routed(runtime,messages,[],'worker')
        self.assertEqual(result['content'],'done')
        self.assertEqual([identity for identity,_ in calls],['default',self.other_id])
        expected=with_tools([{'role':'system','content':worker_system(task)}]+messages,[])
        for identity,history in calls:
            with self.subTest(connection=identity):
                self.assertEqual(history,expected)
                self.assertEqual(history[1:],messages)
        self.assertEqual(messages,[{'role':'user','content':'Keep these instructions'}])
        self.assertEqual(task['providers']['worker']['connection_id'],self.other_id)
        self.assertGreaterEqual(len(task['request_metrics']),3)
        self.assertEqual(task['request_metrics'][0]['status'],'failed')
        self.assertGreater(task['usage']['worker']['tokens'],0)
        self.assertEqual(runtime.handoffs,0)
