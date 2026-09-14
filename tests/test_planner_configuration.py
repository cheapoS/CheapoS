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
        self.provider = dict(base_url='https://provider.example/v1', model='fixture', input_rate=0, output_rate=0)

    def test_fallback_credentials_preserve_role_and_endpoint(self):
        e=self.engine
        e.configure({'worker':self.provider, 'reviewer':dict(self.provider, api_key='reviewer-fixture')})
        task={'providers':copy.deepcopy(e.config)}
        cfg=e._resolve_provider_config(task, 'planner')
        self.assertEqual(cfg['credential_role'], 'reviewer')
        self.assertEqual(e.provider_key('planner',cfg),'reviewer-fixture')
        e.config['planner']=validate_provider(dict(self.provider,base_url='https://other.example/v1'),'planner')
        self.assertEqual(e._resolve_provider_config(task,'planner'),cfg)
        self.assertEqual(e.provider_key('planner',dict(cfg,base_url='https://other.example/v1')),'')
        explicit=validate_provider(self.provider,'planner')
        e.secrets[('planner',explicit['base_url'])]='planner-fixture'
        task['providers']['planner']=explicit
        self.assertEqual(e.provider_key('planner',e._resolve_provider_config(task,'planner')),'planner-fixture')
        self.assertNotIn('fixture-key',json.dumps(task))

    def test_environment_and_shared_gateway_credentials(self):
        cfg=validate_provider(self.provider,'reviewer')
        with patch.dict(os.environ,{cfg['key_env']:'environment-fixture'}):
            self.assertEqual(self.engine.provider_key('planner',cfg),'environment-fixture')
        self.engine.gateway.api_key='shared-fixture'
        cfg=dict(cfg,gateway='omniroute',base_url=self.engine.gateway.settings['base_url'])
        self.assertEqual(self.engine.provider_key('planner',cfg),'shared-fixture')
