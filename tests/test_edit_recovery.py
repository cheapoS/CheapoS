"""Small file/state cases: no Git, subprocess, model requests or real waits."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from cheapos.engine import Engine
from cheapos.workspace import Workspace, FileRangeError
from cheapos.edit_recovery import rejected, check_feedback


class EditRecoveryTests(unittest.TestCase):
    def test_bad_range_refresh_blocks_repeat_and_allows_corrected_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'x.txt';path.write_text('one\ntwo\n')
            workspace=Workspace(directory)
            engine=Engine.__new__(Engine);engine.lock=threading.RLock()
            engine.file_tool=Mock(side_effect=lambda task,name,args:getattr(workspace,name)(**args))
            runtime=SimpleNamespace(task={'workspace':directory},edit_versions={},guard=lambda:None)
            version=workspace.read_file('x.txt')['hash']
            args={'path':'x.txt','start_line':900,'end_line':901,'new_text':'replacement'}
            with self.assertRaises(FileRangeError):
                engine.worker_file_tool(runtime,'replace_lines',args,{'x.txt':version})
            current=engine.edit_snapshot(runtime,args)
            result=rejected(runtime.task,args,current,'Invalid range')
            self.assertEqual(current['total_lines'],2)
            self.assertIn('2: two',current['content'])
            self.assertEqual(current['hash'],version)
            self.assertFalse(result['executed'])
            with self.assertRaisesRegex(FileRangeError,'not executed again'):
                engine.worker_file_tool(runtime,'replace_lines',{**args,'path':'./x.txt'},{'x.txt':version})
            self.assertEqual(engine.file_tool.call_count,1)
            result=rejected(runtime.task,args,current,'Repeated')
            self.assertEqual(result['attempts'],2)
            engine.worker_file_tool(runtime,'replace_lines',{**args,'start_line':2,'end_line':2},{'x.txt':version})
            self.assertEqual(path.read_text(),'one\nreplacement')

    def test_changed_version_resets_failure_streak(self):
        task={};args={'path':'x','start_line':9,'end_line':9,'new_text':'x'}
        rejected(task,args,{'hash':'old'},'bad')
        self.assertEqual(rejected(task,args,{'hash':'new'},'bad')['attempts'],1)

    def test_empty_file_append_remains_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'x').write_text('');ws=Workspace(directory)
            ws.replace_lines('x',1,0,'hello',ws.read_file('x')['hash'])
            self.assertEqual((Path(directory)/'x').read_text(),'hello')

    def test_failure_feedback_keeps_diagnostics_and_original_evidence(self):
        output='✔ unrelated passing test (1ms)\n✖ chat submission\nTypeError: onsubmit is not a function\n  at tests/ui.js:23\nassert.ok(source.includes(marker))\n'
        original={'passed':False,'exit_code':1,'run_id':'abc','output':output}
        result=check_feedback(original)
        self.assertNotIn('unrelated passing',result['output'])
        for line in ('TypeError:', 'tests/ui.js:23', 'assert.ok'):
            self.assertIn(line,result['output'])
        self.assertEqual(original['output'],output)
        self.assertFalse(result['passed'])
        self.assertEqual(result['exit_code'],1)
        self.assertEqual(result['run_id'],'abc')

    def test_repeated_error_queues_handoff_only_for_automatic_placement(self):
        from unittest.mock import patch
        for enabled in (True,False):
            engine=Engine.__new__(Engine)
            engine.edit_snapshot=Mock(return_value={'hash':'same','total_lines':2,'content':'1: one'})
            engine.defer_route=Mock();engine.event=Mock()
            runtime=SimpleNamespace(task={})
            args={'path':'x','start_line':90,'end_line':90,'new_text':'x'}
            with patch('cheapos.engine.automatic',return_value=enabled):
                first=engine.recover_edit_range(runtime,args,FileRangeError('bad'))
                self.assertFalse(first.get('handoff_queued'))
                second=engine.recover_edit_range(runtime,args,FileRangeError('bad'))
            self.assertEqual(bool(second.get('handoff_queued')),enabled)
            self.assertEqual(engine.defer_route.call_count,int(enabled))
            self.assertIn('current_file',second)

    def test_worker_receives_focused_failure_without_changing_saved_check(self):
        engine=Engine.__new__(Engine)
        saved={'passed':False,'exit_code':1,'output':'✔ passed\n✖ failed assertion\n','run_id':'check'}
        engine.checks=Mock(return_value=saved)
        runtime=SimpleNamespace(task={})
        result=engine.worker_checks(runtime,{'command':'exact command'})
        engine.checks.assert_called_once_with(runtime,'exact command')
        self.assertEqual(result['output'],'✖ failed assertion\n')
        self.assertEqual(saved['output'],'✔ passed\n✖ failed assertion\n')
