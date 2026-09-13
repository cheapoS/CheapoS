import copy
from pathlib import Path
from unittest.mock import Mock
from test_engine import LocalCase
from cheapos.engine import Engine, Runtime
from cheapos.workspace import Workspace, git


class TrashTests(LocalCase):
    def test_restore_preserves_all_execution_data_and_prior_archive(self):
        task=self.fixture()
        Workspace(task['workspace']).write_file('saved.txt','Keep this work\n')
        self.engine.refresh_changes(task)
        task['status']='paused'
        self.engine.store.save(task)
        before=copy.deepcopy(self.engine.store.get(task['id']))
        source=git(task['source'],'status','--porcelain')
        self.engine.update_task_metadata(task['id'],{'custom_title':'Saved work','pinned':True,'archived':True})
        self.engine.command_permissions[task['id']]={(task['workspace'],('python3','-m','unittest'))}
        first=self.engine.trash_task(task['id'])
        self.assertEqual(first['trashed_at'],self.engine.trash_task(task['id'])['trashed_at'])
        self.assertEqual(self.engine.store.visible('archived'),[])
        self.assertEqual(self.engine.store.visible('trash')[0]['saved_change_count'],1)
        self.assertEqual(self.engine.session_permissions(task['id'])['commands'],[])
        self.engine.shutdown()
        self.engine=Engine(self.engine.store.root)
        with self.assertRaisesRegex(ValueError,'Restore'):
            self.engine.start(task['id'])
        restored=self.engine.restore_task(task['id'])
        self.assertTrue(restored['archived_at'])
        self.assertTrue(restored['pinned'])
        self.assertEqual(restored['title'],'Saved work')
        self.assertEqual(self.engine.restore_task(task['id']),restored)
        self.assertEqual(self.engine.store.get(task['id']),before)
        self.assertEqual(git(task['source'],'status','--porcelain'),source)
        self.assertTrue(Path(task['workspace'],'saved.txt').exists())

    def test_all_execution_mutations_are_rejected_while_trashed(self):
        task=self.fixture();key=task['id'];self.engine.trash_task(key)
        actions=[lambda:self.engine.start(key),lambda:self.engine.steer(key,'Change it'),
                 lambda:self.engine.approve_check(key,True),lambda:self.engine.prepare_commit(key),
                 lambda:self.engine.apply_commit(key,{}),lambda:self.engine.reconcile_project(key,{}),
                 lambda:self.engine.rollback_checkpoint(key,1),lambda:self.engine.update_limits(key,{'limits':{}}),
                 lambda:self.engine.boost_headroom(key),lambda:self.engine.commit_decision(key,{}),
                 lambda:self.engine.update_task_metadata(key,{'archived':False})]
        for action in actions:
            with self.assertRaisesRegex(ValueError,'Restore'):action()

    def test_runtime_and_incomplete_commit_block_trash(self):
        task=self.fixture();key=task['id'];runtime=Runtime(task)
        runtime.thread=Mock();runtime.thread.is_alive.return_value=True
        self.engine.runtimes[key]=runtime
        with self.assertRaisesRegex(ValueError,'Pause'):self.engine.trash_task(key)
        runtime.thread.is_alive.return_value=False
        task['commit_pending']={'commit':'incomplete'};self.engine.store.save(task)
        with self.assertRaisesRegex(ValueError,'commit'):self.engine.trash_task(key)
        self.assertIsNone(self.engine.store.metadata(key)['trashed_at'])
