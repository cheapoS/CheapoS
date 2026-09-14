"""Tiny filesystem-only coverage, without repeated Git/agent fixtures."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from cheapos.engine import Engine
from cheapos.workspace import Workspace


class EditSequenceTests(unittest.TestCase):
    def test_noop_and_alias_do_not_allow_second_mutation_but_next_response_does(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'x.txt').write_bytes(b'one\r\ntwo\r\n')
            (root/'y.txt').write_text('other\n')
            ws=Workspace(directory)
            engine=Engine.__new__(Engine)
            engine.file_tool=lambda task,name,args:getattr(ws,name)(**args)
            runtime=SimpleNamespace(task={'workspace':directory,'compact_edits':True},edit_versions={})
            versions={name:ws.read_file(name)['hash'] for name in ('x.txt','y.txt')}
            mutated=set()
            result=engine.worker_file_tool(runtime,'replace_lines',{'path':'x.txt','start_line':1,'end_line':1,'new_text':'one'},versions,mutated)
            self.assertIn('current_file',result)
            result=engine.worker_file_tool(runtime,'replace_lines',{'path':'./x.txt','start_line':1,'end_line':1,'new_text':'WRONG'},versions,mutated)
            self.assertEqual(result['code'],'same_response_file_mutation')
            self.assertIn('1: one',result['current_file']['content'])
            self.assertEqual((root/'x.txt').read_bytes(),b'one\r\ntwo\r\n')
            engine.worker_file_tool(runtime,'replace_lines',{'path':'y.txt','start_line':1,'end_line':1,'new_text':'independent\n'},versions,mutated)
            engine.worker_file_tool(runtime,'replace_lines',{'path':'x.txt','start_line':2,'end_line':2,'new_text':'next\r\n'},dict(runtime.edit_versions),set())
            self.assertEqual((root/'x.txt').read_bytes(),b'one\r\nnext\r\n')
            self.assertEqual((root/'y.txt').read_text(),'independent\n')
