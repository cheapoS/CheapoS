import json
import unittest
from cheapos.context_compaction import compact, size, LIMIT

class ContextCompactionTests(unittest.TestCase):
    def test_large_nested_context_leaves_headroom_and_retains_findings(self):
        task={'patch':'new patch','workspace_generation':3,'events':[{'kind':'tool','title':'replace text','detail':{'arguments':{'path':'app.js'},'result':{'changed':True}}}]}
        summary={'latest_message':'Hide the whole row; no toggle required','original_task':'Hide sample',
                 'recovery_continuation':{'next_step':'Checks passed; submit checkpoint after identity validation'},
                 'last_check':{'passed':True,'verification_identity':'revision-a'},
                 'current_files':[{'content':'"\\😀'*20000}]*8,'recent_activity':['old'*30000]*12}
        base=[{'role':'system','content':'Do not fabricate checks.'},{'role':'user','content':json.dumps(summary)}]
        previous=[{'role':'assistant','content':'The handler hides the wrong element. I corrected app.js. Next submit checkpoint.', 'tool_calls':[{'id':'old'}]}]
        result=compact(task,base,previous)
        self.assertLessEqual(size(result),LIMIT)
        self.assertLess(size(result)+12000,60000)
        retained=json.loads(result[1]['content'])
        self.assertEqual(retained['latest_message'],summary['latest_message'])
        self.assertIn('Next submit checkpoint',str(retained['working_memory']))
        self.assertEqual(retained['working_memory']['workspace_generation'],3)
        self.assertEqual(retained['last_check']['verification_identity'],'revision-a')
        self.assertNotIn('tool_calls',str(result))
        self.assertEqual(base[0],result[0])

    def test_revision_changes_do_not_relabel_historical_checks_as_current(self):
        base=[{'role':'system','content':'Review'}, {'role':'user','content':json.dumps({'last_check':{'verification_identity':'old'},'recovery_continuation':{'next_step':'Validate current identity'}})}]
        first=compact({'patch':'a'},base,[])
        second=compact({'patch':'b'},base,[])
        a,b=[json.loads(v[1]['content']) for v in (first,second)]
        self.assertNotEqual(a['working_memory']['patch_digest'],b['working_memory']['patch_digest'])
        self.assertEqual(b['last_check']['verification_identity'],'old')

    def test_recovery_direction_reaches_next_request_without_accumulating(self):
        from cheapos.engine import Engine
        task={'loop_guidance':'Checks passed; submit checkpoint', 'messages':[{'role':'tool','tool_call_id':'read','content':'same file'}]}
        Engine.deliver_loop_guidance(task)
        self.assertIn('submit checkpoint',task['messages'][-1]['content'])
        task['messages'].append({'role':'assistant','content':'I will check again'})
        Engine.deliver_loop_guidance(task)
        self.assertEqual(sum(m.get('role')=='user' for m in task['messages']),1)
        self.assertEqual(task['messages'][-1]['content'],'I will check again')
        task['messages']=[{'role':'system','content':'Rebuilt context'}]
        Engine.deliver_loop_guidance(task)
        self.assertIn('submit checkpoint',task['messages'][-1]['content'])
        task['loop_guidance']=None
        before=list(task['messages']);Engine.deliver_loop_guidance(task)
        self.assertEqual(task['messages'],before)

    def test_constraints_working_state_and_complete_tail_survive_both_budgets(self):
        from cheapos.context_evidence import read
        from cheapos.working_state import update
        for limit in (LIMIT, 18000):
            task={'prompt':'Keep accessibility','requests':['Keep accessibility','Use a confirmation dialog'],'events':[]}
            update(task,{'next_action':'Wire dialog keyboard handling','decisions':['Keep existing handler']})
            previous=[{'role':'user','content':'Historical detail: endpoint /restart'},
                      {'role':'assistant','tool_calls':[{'id':'read','function':{'arguments':'{}'}}]},
                      {'role':'tool','tool_call_id':'read','content':'Found handler'}]
            base=[{'role':'system','content':'policy'},{'role':'user','content':'{}'}]
            result=compact(task,base,previous,limit)
            self.assertIn('Keep accessibility',result[1]['content'])
            self.assertIn('Use a confirmation dialog',result[1]['content'])
            self.assertEqual(result[-2:],previous[-2:])
            ref=json.loads(result[1]['content'])['context_reference']
            self.assertIn('/restart',read(task,ref,search='/restart')['content'])
            self.assertLessEqual(size(result),limit)

    def test_capacity_does_not_erase_constraints(self):
        from cheapos.providers import BudgetError
        from cheapos.context_evidence import read, preview
        task={'prompt':'x'*20000,'events':[]}
        with self.assertRaises(BudgetError):compact(task,[{'role':'system','content':'policy'},{'role':'user','content':'{}'}],[],2000)
        saved=preview(task,{'output':'a'*18000,'error':'important failure'})
        self.assertEqual(saved['error'],'important failure')
        self.assertIn('important failure',read(task,saved['context_reference'],search='important failure')['content'])
        with self.assertRaises(ValueError):read({},saved['context_reference'])
    def test_long_session_restart_preserves_work_and_rejects_concurrent_compaction(self):
        from unittest.mock import patch
        from cheapos.working_state import update
        from cheapos.context_evidence import retain, read
        from cheapos.worker_conversation import continue_session
        from cheapos.providers import BudgetError
        task={'prompt':'Keep endpoint /restart','requests':['Keep endpoint /restart','Add keyboard support'],'events':[],'messages':[]}
        update(task,{'steps':[{'id':'key','text':'Wire keyboard handler','status':'working'}],'next_action':'Wire keyboard handler'})
        task['messages']=[{'role':'assistant','content':'Earlier observation '+str(n)+'x'*10000} for n in range(20)]
        task['messages'] += [{'role':'assistant','tool_calls':[{'id':'saved','function':{'name':'replace_text','arguments':'{}'}}]}, {'role':'tool','tool_call_id':'saved','content':'Keyboard handler saved; checking remains'}]
        base=[{'role':'system','content':'policy'},{'role':'user','content':'{}'}]
        before=size(task['messages']);task['messages']=compact(task,base,task['messages'],18000)
        self.assertLess(size(task['messages']),before//2)
        ref=task['context_checkpoints'][-1]['reference']
        restored=json.loads(json.dumps(task));continue_session(restored,base,'restart')
        self.assertIn('Add keyboard support',str(restored['messages']))
        self.assertIn('Wire keyboard handler',str(restored['messages']))
        self.assertEqual(sum(m.get('tool_call_id')=='saved' for m in restored['messages']),1)
        self.assertIn('Earlier observation 0',read(restored,ref,search='Earlier observation 0')['content'])
        def changed(task,value,kind):
            reference=retain(task,value,kind)
            task['messages'].append({'role':'user','content':'New input during compaction'})
            return reference
        count=len(restored['context_checkpoints'])
        with patch('cheapos.context_evidence.retain',side_effect=changed):
            with self.assertRaisesRegex(BudgetError,'changed during compaction'):
                compact(restored,base,restored['messages'],18000)
        self.assertEqual(restored['messages'][-1]['content'],'New input during compaction')
        self.assertEqual(len(restored['context_checkpoints']),count)
