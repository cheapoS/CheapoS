"""Optional assistance selection is local, pinned, and network-free on save."""
import copy
import unittest
from unittest.mock import patch
from cheapos.routing import coordinator_assistance_config, execution_from, RoutingPause


class CoordinatorConfigurationTests(unittest.TestCase):
    def test_disabled_and_missing_model_do_not_change_remote_work(self):
        task={'execution':{'mode':'remote'},'providers':{'worker':{'model':'remote','base_url':'https://example.com/v1'}}}
        before=copy.deepcopy(task)
        self.assertIsNone(coordinator_assistance_config(task,verify=True))
        self.assertEqual(task,before)
        task['execution']['coordinator_assistance']=True
        self.assertIsNone(coordinator_assistance_config(task))
        self.assertEqual(execution_from({})['coordinator_assistance'],False)

    def test_explicit_local_model_and_local_fallback_are_task_bound(self):
        task={'execution':{'mode':'remote','coordinator_assistance':True,'coordinator_model':'selected:1','local_model':'old:1'}}
        cfg=coordinator_assistance_config(task)
        self.assertEqual(cfg['model'],'selected:1')
        self.assertEqual(cfg['base_url'],'http://127.0.0.1:11434/v1')
        self.assertEqual(cfg['input_rate'],0)
        task['execution']['coordinator_model']=''
        self.assertEqual(coordinator_assistance_config(task)['model'],'old:1')
        task['execution']['local_model']=''
        task['providers']={'coordinator':dict(cfg,model='captured:1')}
        self.assertEqual(coordinator_assistance_config(task)['model'],'captured:1')

    def test_trigger_metadata_rejects_cloud_missing_and_offline_without_inference(self):
        task={'execution':{'coordinator_assistance':True,'coordinator_model':'local:1'}}
        for response in ({'remote_host':'cloud','capabilities':['completion','tools']},{'capabilities':['completion']},{}):
            with self.subTest(response=response),patch('cheapos.startup.local_json',return_value=response),self.assertRaises(RoutingPause):
                coordinator_assistance_config(task,verify=True)
        with patch('cheapos.startup.local_json',side_effect=OSError('offline')),self.assertRaises(RoutingPause):
            coordinator_assistance_config(task,verify=True)
        with patch('cheapos.startup.local_json',return_value={'capabilities':['completion','tools']}) as metadata:
            self.assertEqual(coordinator_assistance_config(task,verify=True)['model'],'local:1')
            self.assertEqual(metadata.call_args.args[0],'http://127.0.0.1:11434/api/show')
