import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from cheapos.preview import Previews, config


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.task = {'source':str(self.root), 'workspace':str(self.root), 'id':'task'}
        self.engine = SimpleNamespace(store=SimpleNamespace(root=self.root,get=lambda _: self.task),
                                      projects=lambda **_: [{'path':str(self.root)}])
        self.manager = Previews(self.engine)
        self.addCleanup(self.manager.shutdown)

    def test_configuration_round_trip_without_launching(self):
        values={'command':'python3 app.py --port {port}', 'url':'http://127.0.0.1:5174', 'environment':'DATA={profile}', 'checklist':'Cancel → stays visible'}
        saved=self.manager.settings({'repository':str(self.root),'config':values})
        self.assertEqual(self.manager.settings({'repository':str(self.root)}),saved)
        self.assertEqual(self.manager.file.stat().st_mode & 0o777,0o600)
        self.assertFalse(self.manager.runs)

    def test_rejects_external_url_and_escaping_directory(self):
        for value in ({'url':'https://example.com:443'}, {'url':'http://localhost'}, {'directory':'../repo'}, {'environment':'bad-name=x'}, []):
            with self.assertRaises(ValueError):config(value)

    def test_launch_checks_exact_reviewed_revision_and_clean_files(self):
        for outputs,values,message in [(['new'],{'expected_tip':'old'},'reviewed revision'), (['same',' M app.py'],{'expected_tip':'same'},'Commit')]:
            with patch('cheapos.preview.subprocess.check_output',side_effect=outputs),patch('cheapos.preview.threading.Thread') as thread:
                with self.assertRaisesRegex(ValueError,message):
                    self.manager.action('task','preview-start',dict(values,config={'command':'python3 app.py'}))
                thread.assert_not_called()

    def test_status_reports_outdated_without_launching(self):
        self.manager.runs['task']=dict(status='exited',tip='old',branch='feature/task',root='/tmp/copy',url='',logs='output',config={},stop=threading.Event(),process=None,thread=Mock(is_alive=lambda:False,join=lambda **_:None))
        with patch('cheapos.preview.subprocess.check_output',side_effect=['new','']):
            self.assertTrue(self.manager.action('task','preview-status',{})['outdated'])

    def test_launch_is_separate_and_expands_arguments_without_shell(self):
        run=dict(root=str(self.root),tip='abc',config=config({'command':'python3 app.py --data {profile}','environment':'PORT=5174'}),logs='',stop=threading.Event())
        calls=[]
        def execute(run,args,cwd,env):
            calls.append((args,cwd,dict(env)))
            if args[:2]==['git','clone']:(self.root/'workspace').mkdir()
            return True
        self.manager.execute=execute
        self.manager.launch(run,'/original/task')
        self.assertIn('--no-hardlinks',calls[0][0])
        self.assertEqual(calls[1][0],['git','checkout','--detach','abc'])
        self.assertEqual(calls[2][1],self.root/'workspace')
        self.assertEqual(calls[2][0][-1],str(self.root/'profile'))
        self.assertEqual(calls[2][2]['PORT'],'5174')

    def test_stop_signals_only_owned_process_group(self):
        run=dict(process=SimpleNamespace(pid=123),stop=threading.Event(),thread=Mock(is_alive=lambda:True))
        with patch('cheapos.preview.os.killpg') as kill,patch('cheapos.preview.threading.Thread'):
            self.manager.stop(run)
            self.assertEqual(kill.call_args.args[0],123)
        self.assertTrue(run['stop'].is_set())
