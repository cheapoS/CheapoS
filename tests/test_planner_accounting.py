import copy
import unittest
from cheapos.providers import reserve, reconcile

class PlannerAccountingTests(unittest.TestCase):
    def test_old_accounting_preserves_history_and_reconciles(self):
        task={'limits':{'output_tokens':128,'reviewer_tokens':10000,'dollars':3},'usage':{'worker':{'tokens':900,'cost':1},'reviewer':{'tokens':20,'cost':0.2},'cost':1.2,'uncertain_requests':1,'estimated_requests':2},'pause_cause':{'code':'saved'}}
        original=copy.deepcopy(task)
        cfg={'input_rate':0,'output_rate':0}
        reservation=reserve(task,cfg,[],[],'planner')
        reconcile(task,cfg,reservation,{'prompt_tokens':60,'completion_tokens':40,'cost':0})
        self.assertEqual(task['usage']['planner'],{'tokens':100,'cost':0})
        for role in ('worker','reviewer'):self.assertEqual(task['usage'][role],original['usage'][role])
        self.assertEqual(task['usage']['cost'],1.2)
        self.assertEqual(task['usage']['uncertain_requests'],1)
        self.assertEqual(task['pause_cause'],original['pause_cause'])
        reservation=reserve(task,cfg,[],[],'planner')
        reconcile(task,cfg,reservation,{'prompt_tokens':1,'completion_tokens':1,'cost':0})
        self.assertEqual(task['usage']['planner']['tokens'],102)
        task['usage']['planner']={'tokens':'bad','cost':0}
        with self.assertRaises(ValueError):reserve(task,cfg,[],[],'planner')
