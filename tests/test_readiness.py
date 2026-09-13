import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos.readiness import ReadinessManager, describe, prerequisites


class ReadinessTests(unittest.TestCase):
    def describe(self, status='offline', installed=True, node=True, execution=None, startup=None, **gateway):
        return describe({'status':status, **gateway},
                        {'node':{'installed':node},'omniroute':{'installed':installed}},
                        [{'config':{'model':'fixture-local'}}], execution or {}, startup or {})

    def test_distinct_recovery_contract(self):
        cases = [({'installed':False}, 'gateway_absent','install_gateway'),
                 ({'installed':False,'node':False}, 'gateway_absent','install_node'),
                 ({}, 'gateway_stopped','start_gateway'),
                 ({'status':'starting'}, 'starting','wait'),
                 ({'status':'ready','free_count':2}, 'gateway_ready','open_project'),
                 ({'status':'ready'}, 'no_eligible_model','configure_provider'),
                 ({'status':'unavailable','diagnostic_code':'unidentified_service'}, 'foreign_service','choose_gateway_endpoint'),
                 ({'status':'auth_required'}, 'client_key_rejected','enter_client_key'),
                 ({'status':'unavailable'}, 'offline','inspect_gateway'),
                 ({'execution':{'mode':'local','local_model':'fixture-local'}}, 'local_only_ready','open_project'),
                 ({'execution':{'mode':'local','local_model':'missing'}}, 'local_unavailable','check_local_models')]
        for arguments, status, action in cases:
            with self.subTest(arguments=arguments):
                result=self.describe(**arguments)
                self.assertEqual((result['schema_version'],result['status'],result['next_step']),(1,status,action))

    def test_greeting_does_not_claim_completed_work_or_leak_config(self):
        result=self.describe('ready', free_count=2, owned=False, settings={'api_key':'SECRET'},
                             message='SECRET', startup={'status':'ready','verified_at':'now','usage':{'tokens':3}})
        self.assertTrue(result['levels']['greeting'])
        self.assertTrue(result['levels']['usage_reporting'])
        for level in ('coding','checks','review'): self.assertFalse(result['levels'][level])
        self.assertNotIn('SECRET',json.dumps(result))
        self.assertFalse(result['gateway']['owned'])
        self.assertFalse(any(result['gateway']['optional_apis'].values()))

    def test_installed_version_is_not_running_service_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'bin').mkdir(); executable=root/'bin/cli.js'; executable.touch()
            for version, expected in [('3.8.49','validated_baseline'),('3.9.0','unverified'),('bad','unverified')]:
                (root/'package.json').write_text(json.dumps({'name':'omniroute','version':version}))
                with patch('cheapos.readiness.find_executable',return_value=str(executable)), patch('cheapos.readiness.shutil.which',return_value=None):
                    result=prerequisites()
                self.assertEqual(result['omniroute']['compatibility'],expected)
                self.assertFalse(result['node']['installed'])

    def test_inspection_is_metadata_only_and_refreshes_stopped_connection(self):
        engine=SimpleNamespace(gateway=Mock(), config={}, preferences=Mock(return_value={'execution':{}}), startup=Mock())
        engine.gateway.snapshot.return_value={'status':'offline'}
        engine.startup.snapshot.return_value={}
        manager=ReadinessManager(engine)
        with patch('cheapos.readiness.prerequisites',return_value={'node':{'installed':True},'omniroute':{'installed':True}}), patch('cheapos.readiness.local_candidates',return_value=[]) as local:
            self.assertEqual(manager.inspect()['status'],'gateway_stopped')
            manager.inspect()
        self.assertEqual(local.call_count,1)
        self.assertEqual(engine.gateway.method_calls,[unittest.mock.call.snapshot(),unittest.mock.call.refresh(start=False)]*2)
        engine.startup.start.assert_not_called()
        manager.shutdown()
