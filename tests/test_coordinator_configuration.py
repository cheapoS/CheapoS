"""Optional assistance selection is local, pinned, and network-free on save."""
import copy
import unittest
from unittest.mock import patch
from cheapos.routing import coordinator_assistance_config, execution_from, RoutingPause
from cheapos.coordinator_dispatch import reassessment_availability
from cheapos.coordinator_recovery import episode_key, identity


class CoordinatorConfigurationTests(unittest.TestCase):
    def test_paused_opt_in_is_only_an_unused_interactive_consultation(self):
        task={'id':'task', 'prompt':'Add trash controls', 'requests':['Add trash controls'],
              'status':'paused','error_code':'progress_limit','active_role':'worker',
              'execution':{'mode':'delegate','local_model':'local:1','coordinator_assistance':False},
              'limits':{'worker_turns':40,'run_minutes':15},'conversational':True,'worker_turns':12,'request_worker_turns':12,
              'run_metrics':[{'elapsed_seconds':80,'operator_wait_seconds':20}]}
        before=copy.deepcopy(task)
        self.assertEqual(reassessment_availability(task),{'available':True,'model':'local:1'})
        self.assertEqual(task,before)
        # A historical stop is not a current cap after the operator raises it.
        raised={**task,'limits':{**task['limits'],'worker_turns':200},
                'request_worker_turns':71,'limit_hit':{'key':'worker_turns','used':40,'allowed':40,'remaining':0}}
        self.assertTrue(reassessment_availability(raised)['available'])
        self.assertEqual(raised['limit_hit']['allowed'],40)
        task['execution']['coordinator_assistance']=True
        legacy={'key':episode_key(task),'identity':identity(task),'state':'failed',
                'diagnostic':'Coordinator must return one JSON object','packet':{'evidence':[]}}
        legacy_task={**task,'coordinator_recovery':[legacy]}
        self.assertTrue(reassessment_availability(legacy_task)['format_repair'])
        self.assertFalse(reassessment_availability({**legacy_task,'patch':'changed'})['available'])
        legacy['format_repair']={'state':'prepared'}
        self.assertFalse(reassessment_availability(legacy_task)['available'])
        exclusions=[{'status':'running'}, {'demo':True}, {'branch_run':{'id':'run'}},
                    {'pending_approval':{'id':'command'}}, {'pending_review':{'id':'review'}},
                    {'pending_checkpoint':{'summary':'saved'}}, {'pending_verification':True},
                    {'commit_pending':True}, {'limit_hit':{'key':'dollars'}},
                    {'error_code':'environment_setup'}, {'active_role':'reviewer'},
                    {'environment_setup':{'status':'missing'}}, {'reconciliation':{'conflicts':['file.py']}},
                    {'request_worker_turns':40}, {'recovery_work_seconds':900},
                    {'coordinator_recovery':[{'key':episode_key(task),'state':'failed'}]},
                    {'execution':{'mode':'remote','coordinator_assistance':False}}]
        for change in exclusions:
            with self.subTest(change=change):
                self.assertFalse(reassessment_availability({**task,**change})['available'])
        with patch('cheapos.startup.local_json') as metadata:
            reassessment_availability(task)
            metadata.assert_not_called()

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
