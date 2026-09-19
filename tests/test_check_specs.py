"""Directory contracts with small filesystem/in-memory cases; no model or Git runs."""
import copy
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cheapos import check_specs, branch_evidence, test_policy
from cheapos.branch_planner import _parse, TOOLS
from cheapos.branch_runs import validate_plan
from cheapos.verification import reusable_check


class CheckDirectoryTests(unittest.TestCase):
    def test_normalizes_legacy_and_component_checks_without_merging_directories(self):
        argv=[sys.executable, '-B', '-m', 'unittest', 'tests/test_one.py']
        specs=check_specs.specifications([shlex.join(argv), {'command':argv,'directory':'./component/'}])
        self.assertEqual([s['directory'] for s in specs],['.','component'])
        self.assertEqual(specs[0]['command'][-1],'tests.test_one')
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            check_specs.specifications([{'command':'node test.js','directory':'component'}, {'command':'node test.js','directory':'./component/'}])
        for value in ({'command':'node test.js','cwd':'component'},{'directory':'component'},{'command':[]}):
            with self.subTest(value=value),self.assertRaises(ValueError):check_specs.specifications([value])

    def test_directory_rejects_traversal_symlinks_files_and_git(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();inside=root/'workspace';inside.mkdir();(inside/'component').mkdir()
            (inside/'escape').symlink_to(root,target_is_directory=True)
            (inside/'file').write_text('data')
            task={'workspace':str(inside)}
            for value in ('../','/tmp','C:\\fakepath','x/../component','.git','x/.git','line\nbreak','escape','file'):
                with self.subTest(value=value),self.assertRaises((ValueError,OSError)):
                    check_specs.cwd(task,value,allow_missing=True)
            self.assertEqual(check_specs.cwd(task,'./component/'),inside/'component')
            self.assertEqual(check_specs.cwd(task,'new/component',allow_missing=True),inside/'new/component')
            with self.assertRaises(OSError):check_specs.cwd(task,'new/component')

    def test_selection_requires_directory_when_planned_command_is_ambiguous(self):
        task={'check_command':['node','test.js'],'branch_run':{'current_item_id':'one','items':[{'id':'one','required_checks':[{'command':'node test.js','directory':'app'}]}]}}
        self.assertEqual(check_specs.selected_directory(task,['node','test.js']),'app')
        task['branch_run']['items'][0]['required_checks'].append({'command':'node test.js','directory':'other'})
        with self.assertRaisesRegex(ValueError,'multiple directories'):check_specs.selected_directory(task,['node','test.js'])
        self.assertEqual(check_specs.selected_directory(task,['node','test.js'],'other'),'other')
        self.assertEqual(check_specs.selected_directory(task,['node','extra.js']),'.')

    def test_reuse_never_crosses_directories_even_with_equal_claimed_identity(self):
        command=['node','test.js']
        record={'command':command,'directory':'app','passed':True,'exit_code':0,'input_identity':'same','verification_identity':'same'}
        task={'checks':[record],'check_directory':'app'}
        with patch('cheapos.verification.evidence_identity',return_value='same'):
            self.assertIs(reusable_check(task,command),record)
            self.assertIsNone(reusable_check(task,command,'other'))
            self.assertIsNone(reusable_check(task,command,'.'))
        current={'id':'candidate','checks':[{'command':command,'directory':'app','verification_identity':'same'}]}
        self.assertEqual(branch_evidence.bind_check(current,command,record,'app')['directory'],'app')
        for directory in ('.','other'):
            with self.assertRaises(ValueError):branch_evidence.bind_check(current,command,record,directory)

    def test_full_suite_consent_is_directory_bound(self):
        check={'command':'python3 -m unittest discover','directory':'app'}
        task={'branch_run':{'plan':{'final_checks':[check]},'test_policy_version':1}}
        test_policy.approve(task,True)
        test_policy.guard(task,check)
        test_policy.guard({**task,'check_directory':'app'},check['command'])
        for directory in ('.','other'):
            with self.assertRaisesRegex(ValueError,'not explicitly approved'):
                test_policy.guard({**task,'check_directory':directory},check['command'])

    def test_planner_preserves_structured_checks_in_default_final_list(self):
        import json
        limits={'dollars':0,'working_seconds':90}
        check={'command':shlex.join([sys.executable,'-B','test.py']),'directory':'component'}
        plan={'items':[{'id':'one','title':'Improve component','instructions':'Keep edits scoped','acceptance_criteria':['Verified'],'required_checks':[check]}],'limits':limits}
        call={'tool_calls':[{'function':{'name':'propose_branch_plan','arguments':json.dumps({'status':'plan','plan':plan,'clarification':''})}}]}
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'component').mkdir()
            parsed=_parse(call,limits,folder)
        self.assertEqual(parsed['items'][0]['required_checks'],[check])
        self.assertEqual(parsed['final_checks'],[check])
        self.assertEqual(validate_plan(parsed),parsed)
        schema=TOOLS[0]['function']['parameters']['properties']['plan']['properties']['final_checks']['items']
        self.assertTrue(any(s['type']=='object' for s in schema['anyOf']))
