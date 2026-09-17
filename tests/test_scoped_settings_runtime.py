"""Small in-memory scope/runtime contracts; no model calls or Git fixtures."""
import copy
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from cheapos.engine import Engine
from cheapos.model_pool import automatic
from cheapos import task_settings


class ScopedRuntimeTests(unittest.TestCase):
    def test_only_model_does_not_enter_automatic_handoffs(self):
        task={'execution':{'mode':'remote'},'route':{'ready':True},'providers':{},
              'settings_snapshot':{'values':{'roles':{'worker':{'strategy':'only','model':'chosen'},'reviewer':{'strategy':'automatic'}}}}}
        self.assertFalse(automatic(task,'worker'))
        self.assertTrue(automatic(task,'reviewer'))
        task['operator_reviewer_model']='second'
        self.assertFalse(automatic(task,'reviewer'))

    def test_apply_snapshot_preserves_usage_and_pins_after_remote_setup(self):
        from cheapos.routing import execution_from
        provider={'gateway':'omniroute','base_url':'http://127.0.0.1:20128/v1','model':'chosen','connection_id':'gateway'}
        values={'execution':execution_from({'mode':'remote'}),'limits':{'dollars':0},
                'roles':{'worker':{'strategy':'only','model':'chosen'},'reviewer':{'strategy':'automatic'},'planner':{'strategy':'automatic'}}}
        snapshot={'revision':1,'values':values}
        policy={'execution':values['execution'],'providers':{'worker':provider,'reviewer':None,'planner':None},'gateway_connections':[]}
        engine=SimpleNamespace(settings_policy=Mock(return_value=policy),gateway=SimpleNamespace(settings={'base_url':provider['base_url']}))
        task={'conversational':True,'usage':{'cost':2},'messages':[{'role':'user','content':'retain'}]}
        Engine.settings_apply_snapshot(engine,task,snapshot)
        self.assertEqual(task['providers']['worker'],provider)
        self.assertEqual(task['gateway_connections'],[])
        self.assertEqual(task['usage'],{'cost':2})
        self.assertTrue(task['route']['ready'])
        snapshot['values']['limits']['dollars']=4
        self.assertEqual(task['settings_snapshot']['values']['limits']['dollars'],0)

    def test_restart_continuation_keeps_one_saved_operation(self):
        task={'id':'saved','settings_operations':{'same':{'stage':'dispatching','result':{'pending':True}}}}
        store=Mock();store.list.return_value=[task];store.get.side_effect=lambda _:copy.deepcopy(task)
        def save(value):task.clear();task.update(copy.deepcopy(value))
        store.save.side_effect=save
        engine=SimpleNamespace(store=store,lock=threading.RLock(),runtimes={},start=Mock())
        task_settings.restore(engine)
        engine.start.assert_called_once_with('saved',{})
        self.assertEqual(task['settings_operations']['same']['stage'],'continuing')
        task_settings.restore(engine)
        engine.start.assert_called_once()
