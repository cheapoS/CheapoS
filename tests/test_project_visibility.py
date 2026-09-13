import copy
import shutil
from pathlib import Path
from unittest.mock import Mock
from test_engine import LocalCase
from cheapos.engine import Engine, Runtime
from cheapos.workspace import git


class ProjectVisibilityTests(LocalCase):
    def test_hidden_history_stays_hidden_and_reopen_preserves_tasks(self):
        task=self.fixture();task['demo']=False;self.engine.store.save(task)
        before=copy.deepcopy(task);head=git(task['source'],'rev-parse','HEAD')
        self.engine.open_project({'repository':task['source']})
        self.engine.hide_project({'repository':task['source']})
        self.assertEqual(self.engine.projects(),[])
        self.assertEqual(len(self.engine.projects(include_hidden=True)),1)
        self.engine.shutdown();self.engine=Engine(self.engine.store.root)
        self.assertEqual(self.engine.projects(),[])
        self.engine.open_project({'repository':task['source']})
        self.assertEqual(len(self.engine.projects()),1)
        self.assertEqual(self.engine.store.list(),[before])
        self.assertEqual(git(task['source'],'rev-parse','HEAD'),head)
        self.assertEqual(git(task['source'],'status','--porcelain'),'')

    def test_same_basename_paths_and_missing_project_are_distinct(self):
        task=self.fixture()
        roots=[self.root/'a'/'project',self.root/'b'/'project']
        for root in roots:
            shutil.copytree(task['source'],root)
            self.engine.open_project({'repository':str(root)})
        self.engine.hide_project({'repository':str(roots[0])})
        self.assertEqual([p['path'] for p in self.engine.projects()],[str(roots[1].resolve())])
        shutil.rmtree(roots[0])
        with self.assertRaises(ValueError):self.engine.open_project({'repository':str(roots[0])})
        self.assertIn(str(roots[0].resolve()),self.engine.hidden_project_paths())
        with self.assertRaises(ValueError):self.engine.hide_project({'repository':'/not/a/known/project'})

    def test_running_task_and_pending_commit_block_hide(self):
        task=self.fixture();task['demo']=False;self.engine.store.save(task)
        runtime=Runtime(task);runtime.thread=Mock();runtime.thread.is_alive.return_value=True
        self.engine.runtimes[task['id']]=runtime
        with self.assertRaisesRegex(ValueError,'Pause'):self.engine.hide_project({'repository':task['source']})
        runtime.thread.is_alive.return_value=False
        task['commit_pending']={'saved':True};self.engine.store.save(task)
        with self.assertRaisesRegex(ValueError,'commit'):self.engine.hide_project({'repository':task['source']})
        self.assertFalse(self.engine.hidden_project_paths())
