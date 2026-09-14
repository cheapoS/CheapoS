"""Small immutable-source and packet tests; no real repository or model."""
import json,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from cheapos import review_context as context,branch_final

class ContextTests(unittest.TestCase):
    def test_context_is_exact_candidate_numbered_bounded_and_safe(self):
        run={'workspace_mapping':{'source':'repo'},'expected_feature_tip':'tip'}
        manifest={'id':'m','feature_tip':'tip','feature_tree':'tree','feature_ref':'refs/heads/job'}
        text=b'def parse():\n    raise CLIError("missing")\n'
        def git(source,*args,**kwargs):
            if args[0]=='rev-parse':return 'tree'
            if args[0]=='ls-tree':return b'100644 blob abc\tparser.py\0'
            if args[:2]==('cat-file','-s'):return str(len(text))
            if args[:2]==('cat-file','blob'):return text
            raise AssertionError(args)
        with patch.object(context.work,'_tip',return_value='tip'),patch.object(context.work,'source_git',side_effect=git):
            value=context.read(run,manifest,{'manifest_id':'m','path':'parser.py','start_line':2,'end_line':2})
            self.assertIn('2:     raise CLIError',value['content']);self.assertTrue(value['truncated']);self.assertFalse(value['complete_file'])
            for args in ({'manifest_id':'stale','path':'parser.py'}, {'manifest_id':'m','path':'../key'}, {'manifest_id':'m','path':'.env'}):
                with self.assertRaises(ValueError):context.read(run,manifest,args)
            run['expected_feature_tip']='other'
            with self.assertRaises(ValueError):context.read(run,manifest,{'manifest_id':'m','path':'parser.py'})

    def test_coherent_chunks_preserve_every_character(self):
        text='diff --git a/a b/a\n@@ first\n'+'line\n'*20+'diff --git a/b b/b\n@@ second\n'+'other\n'*10
        parts=context.chunks(text,80)
        self.assertEqual(''.join(parts),text);self.assertTrue(all(len(p)<=80 for p in parts))

    def test_context_read_is_not_decision_or_extra_coverage(self):
        manifest={'id':'m','requirements':[]};run={};runtime=SimpleNamespace(task={'branch_run':run},guard=lambda:None)
        replies=[{'tool_calls':[{'id':'read','name':'read_final_context','args':{'manifest_id':'m','path':'parser.py','start_line':1,'end_line':2}}]},
                 {'tool_calls':[{'id':'decision','name':'final_review_decision','args':{'decision':'APPROVE','manifest_id':'m','chunk_ids':['diff:1'],'criteria_ids':[],'feedback':'Inspected surrounding raise.'}}]}]
        engine=SimpleNamespace(request=Mock(side_effect=replies),parse_call=lambda c:(c['name'],c['args']),event=Mock(),store=SimpleNamespace(save=Mock()))
        with patch.object(context,'read',return_value={'manifest_id':'m','candidate':'tip','content':'2: raise CLIError()', 'path':'parser.py'}):
            result=branch_final._review(engine,runtime,manifest,{},['diff:1'],[])
        self.assertEqual(result['chunk_ids'],['diff:1']);self.assertEqual(engine.request.call_count,2)
        self.assertEqual(result['context_references'][0]['candidate'],'tip')
