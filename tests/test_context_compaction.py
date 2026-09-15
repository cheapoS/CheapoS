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
