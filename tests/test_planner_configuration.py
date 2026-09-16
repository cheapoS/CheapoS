"""Planner configuration without sockets or workflow fixtures."""
import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from cheapos.engine import Engine
from cheapos.providers import validate_provider


class PlannerConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = Engine(self.temp.name)
        self.addCleanup(self.engine.gateway.shutdown)
        self.provider = dict(base_url=self.engine.gateway.settings['base_url'], gateway='omniroute', model='fixture', input_rate=0, output_rate=0)

    def test_fallback_credentials_preserve_role_and_endpoint(self):
        e=self.engine
        e.gateway.api_key='shared-fixture'
        e.configure({'worker':self.provider, 'reviewer':self.provider})
        task={'providers':copy.deepcopy(e.config)}
        cfg=e._resolve_provider_config(task, 'planner')
        self.assertEqual(cfg['credential_role'], 'reviewer')
        self.assertEqual(e.provider_key('planner',cfg),'shared-fixture')
        e.config['planner']=validate_provider(dict(self.provider,base_url='https://other.example/v1'),'planner')
        self.assertEqual(e._resolve_provider_config(task,'planner'),cfg)
        self.assertEqual(e.provider_key('planner',dict(cfg,base_url='https://other.example/v1')),'')
        explicit=validate_provider(self.provider,'planner')
        task['providers']['planner']=explicit
        self.assertEqual(e.provider_key('planner',e._resolve_provider_config(task,'planner')),'shared-fixture')
        self.assertNotIn('fixture-key',json.dumps(task))

    def test_environment_and_shared_gateway_credentials(self):
        cfg=validate_provider(self.provider,'reviewer')
        with patch.dict(os.environ,{cfg['key_env']:'environment-fixture'}):
            self.assertEqual(self.engine.provider_key('planner',cfg),'')
        self.engine.gateway.api_key='shared-fixture'
        cfg=dict(cfg,gateway='omniroute',base_url=self.engine.gateway.settings['base_url'])
        self.assertEqual(self.engine.provider_key('planner',cfg),'shared-fixture')

    def test_dedicated_configuration_roundtrip_and_explicit_reset(self):
        e=self.engine
        e.gateway.api_key='secret-fixture'
        e.configure({'worker':self.provider,'reviewer':self.provider,'planner':dict(self.provider,model='strong-planner')})
        e.configure({'worker':dict(self.provider,model='changed')})
        restored=Engine(self.temp.name)
        self.addCleanup(restored.gateway.shutdown)
        self.assertEqual(restored.config['planner']['model'],'strong-planner')
        self.assertFalse(restored.configuration()['planner']['key_configured'])
        self.assertNotIn('secret-fixture',(e.store.root/'config.json').read_text())
        e.configure({'planner':None})
        self.assertIsNone(e.config['planner'])
        e.save_preferences({'execution':{'local_planner':'installed:1'}})
        self.assertEqual(restored.preferences()['execution']['local_planner'],'installed:1')
        with self.assertRaises(ValueError):e.save_preferences({'execution':{'local_planner':False}})

    def test_legacy_policy_defaults_preserve_digest_but_not_changed_authorization(self):
        from cheapos.branch_controller import policy_for_saved
        old={'execution':{'mode':'manual'},'providers':{'reviewer':self.provider},'gateway_access':{'connection_revision':'old'}}
        current=copy.deepcopy(old)
        current['execution']['local_planner']=''
        current['providers']['planner']=None
        self.assertEqual(policy_for_saved(current,old),old)
        self.assertIn('local_planner',current['execution'])
        for field,value in (('local_planner','strong'),):
            changed=copy.deepcopy(current);changed['execution'][field]=value
            self.assertNotEqual(policy_for_saved(changed,old),old)
        changed=copy.deepcopy(current);changed['providers']['planner']=self.provider
        self.assertNotEqual(policy_for_saved(changed,old),old)
        changed=copy.deepcopy(current);changed['gateway_access']['connection_revision']='new'
        self.assertNotEqual(policy_for_saved(changed,old),old)

    def test_direct_settings_are_rejected_atomically_and_legacy_settings_are_visible(self):
        e=self.engine
        e.configure({'worker':self.provider,'reviewer':self.provider})
        saved=(e.store.root/'config.json').read_text()
        remote=dict(self.provider,base_url='https://openrouter.ai/api/v1',gateway='openai')
        for role in ('worker','reviewer','planner'):
            with self.subTest(role=role), self.assertRaisesRegex(ValueError,'must use the configured OmniRoute'):
                e.configure({role:remote})
            self.assertEqual((e.store.root/'config.json').read_text(),saved)
        e.config['planner']=remote
        result=e.configuration()['planner']
        self.assertIn('direct provider',result['route_error'])
        self.assertFalse(result['key_configured'])
        self.assertEqual(e.config['planner'],remote)
