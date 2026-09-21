"""Storage policies and receipts: no models, network, sleeps or agent workflows."""
import copy
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos.admission import Admission
from cheapos.storage import Store, write_json
from cheapos.storage_maintenance import Maintenance, merge_identity, owned_workspace
from cheapos import branch_completion


class StoragePolicyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.store = Store(self.root)
        self.engine = SimpleNamespace(store=self.store, lock=threading.RLock(), runtimes={},
                                      command_permissions={}, previews=SimpleNamespace(runs={}))
        self.engine.admission = Admission(self.engine)
        self.manager = Maintenance(self.engine)

    def task(self, task_id='task', trashed=True):
        task = {'id': task_id, 'title': 'Saved chat', 'status': 'completed', 'created_at':'2026-01-01T00:00:00Z'}
        self.store.save(task)
        if trashed:
            self.store.set_trashed(task_id, True)
            meta = self.store.metadata(task_id); meta['trashed_at'] = '2026-01-01T00:00:00+00:00'
            write_json(self.root / 'tasks' / task_id / 'metadata.json', meta)
        return task

    def test_expiry_is_opt_in_and_does_not_delete_restored_or_busy_tasks(self):
        self.task(); self.task('restored'); self.task('busy')
        self.store.set_trashed('restored', False)
        now = datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp()
        self.assertEqual(self.manager.sweep(now=now)['deleted'], 0)
        self.manager.configure({'reclaim_merged': True, 'trash_days':30})
        self.engine.admission.pending['busy'] = 'interactive'
        result = self.manager.sweep(now=now)
        self.assertEqual(result['deleted'], 1)
        self.assertIn('restored', self.store.tasks); self.assertIn('busy', self.store.tasks)
        self.assertFalse((self.root / 'tasks' / 'task').exists())
        self.engine.admission.pending.clear()
        self.assertEqual(self.manager.sweep(now=now)['deleted'], 1)

    def test_invalid_settings_and_corrupt_file_never_fall_back_to_delete(self):
        for values in ({}, {'reclaim_merged':1,'trash_days':30}, {'reclaim_merged':True,'trash_days':0},
                       {'reclaim_merged':True,'trash_days':True}, {'reclaim_merged':True,'trash_days':1,'force':True}):
            with self.assertRaises(ValueError): self.manager.configure(values)
        self.task(); self.manager.file.write_text('{broken')
        with self.assertRaises(ValueError): self.manager.sweep(empty_trash=True)
        self.assertIn('task', self.store.tasks)

    def test_path_mismatch_or_unknown_ownership_retains_task_and_files(self):
        task = self.task()
        outside = self.root / 'operator-project'; outside.mkdir()
        (outside / 'draft.txt').write_text('keep me')
        task['workspace'] = str(outside); self.store.save(task)
        result = self.manager.sweep(empty_trash=True)
        self.assertEqual(result['deleted'],0); self.assertTrue(result['errors'])
        self.assertIn('task', self.store.tasks)
        self.assertEqual((outside / 'draft.txt').read_text(),'keep me')
        task.pop('workspace')
        workspace = self.root / 'tasks/task/workspace'; workspace.mkdir()
        with self.assertRaisesRegex(ValueError,'not recorded'): owned_workspace(self.store, task)
        task['workspace'] = str(workspace); task['workspace_owner'] = [-1,-1]
        with self.assertRaisesRegex(ValueError,'identity changed'): owned_workspace(self.store, task)

    def test_background_pass_runs_without_an_operator_action(self):
        self.manager.sweep = Mock(side_effect=self.manager.shutdown)
        self.manager._loop()
        self.manager.sweep.assert_called_once_with()

    def test_merge_receipts_require_exact_published_head_and_no_open_pr(self):
        task = {'branch_run': {'status':'merged', 'expected_feature_tip':'tip',
            'merge_receipt':{'stage':'completed','feature_tip':'tip','id':'merge'},
            'workspace_mapping':{'source':'repo'}}}
        self.assertEqual(merge_identity(task)['commit'],'tip')
        task['pull_request']={'head':'tip','source':'repo','id':'pr','ci':{'state':'open'}}
        self.assertIsNone(merge_identity(task))
        task['pull_request'].update(merged_head='other',ci={'state':'merged','head':'tip'})
        self.assertIsNone(merge_identity(task))
        task['pull_request']['merged_head']='tip'
        self.assertEqual(merge_identity(task)['publication'],'pr')

    def test_reclaimed_review_uses_saved_evidence_without_accessing_copy(self):
        manifest = {'id':'packet','diff':'saved complete diff','files':[],'commits':[],
                    'target_ref':'main','base_sha':'base','feature_tip':'tip','target_tip':'base'}
        task = {'id':'task', 'workspace_cleanup': {'state':'reclaimed'},
                'branch_run': {'status':'merged','readiness': {'manifest':manifest}}}
        controller = SimpleNamespace(engine=SimpleNamespace(lock=threading.RLock(),
            gateway=SimpleNamespace(pool=Mock())), validate_authority=Mock(side_effect=AssertionError('No revalidation of deleted copy')))
        with patch.object(branch_completion,'_task',return_value=task), patch('cheapos.model_pool.observe_completions'):
            preview = branch_completion.preview(controller,'task')
            page = branch_completion.diff(controller,'task',{'offset':6,'limit':8})
        self.assertEqual(preview['diff'],manifest['diff'])
        self.assertEqual(page['diff'],'complete')
        self.assertIsNone(page['blocker']); self.assertFalse(preview['merge_available'])
        controller.validate_authority.assert_not_called()
