import tempfile
import threading
import unittest
from unittest.mock import Mock

from cheapos import branch_runs
from cheapos.engine import Engine
from cheapos.server import public_task
from cheapos.storage import Store


class BranchStateStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = Engine(self.temp.name, fixture_delay=0)
        self.engine.startup.busy = lambda: False
        self.task = dict(id='known', title='Original', prompt='Original request', requests=['Original request'],
                         source='/fixture', status='ready', created_at='2026', updated_at='2026',
                         demo=False, usage={}, events=[])
        self.run = branch_runs.create_run({'items':[{'id':'one','title':'One','instructions':'Implement one',
            'dependencies':[], 'acceptance_criteria':['Works'], 'required_checks':[]}], 'limits':{'cost':0,'working_seconds':600}}, original_request='Original request')
        self.task['branch_run'] = self.run
        self.engine.store.save(self.task)

    def test_roundtrip_and_summary_do_not_expose_authorization(self):
        self.run['authorization_reference'] = 'private-authority-reference'
        self.engine.store.save(self.task)
        restarted = Store(self.temp.name)
        self.assertEqual(restarted.get('known')['branch_run'], self.run)
        summary = restarted.visible()[0]
        self.assertNotIn('private-authority-reference', str(summary))
        public = public_task(restarted.get('known'), summary=True, store=restarted)
        self.assertEqual(public['branch_run'], summary['branch_run'])
        self.assertEqual(public_task(restarted.get('known'))['branch_run'], self.run)

    def test_concurrent_metadata_and_controller_updates_preserve_both(self):
        barrier = threading.Barrier(2)
        def metadata():
            barrier.wait()
            for i in range(10): self.engine.store.update_metadata('known', {'custom_title':'Renamed'})
        worker = threading.Thread(target=metadata)
        worker.start(); barrier.wait()
        for i in range(10):
            self.engine.update_branch_run('known', lambda task: branch_runs.append_event(task['branch_run'], 'progress'))
        worker.join()
        saved = self.engine.store.get('known')
        self.assertEqual(self.engine.store.present(saved)['title'], 'Renamed')
        self.assertEqual(saved['prompt'], 'Original request')
        self.assertEqual(saved['requests'], ['Original request'])
        self.assertEqual(len(saved['branch_run']['events']), 10)

    def test_unknown_schema_readable_but_manual_start_cannot_dispatch(self):
        self.task['branch_run']['schema_version'] = 999
        self.engine.store.save(self.task)
        self.assertFalse(branch_runs.compatibility(self.engine.store.get('known')['branch_run'])['supported'])
        with self.assertRaises(ValueError): self.engine.start('known')
        self.assertEqual(self.engine.runtimes, {})
        self.assertEqual(self.engine.store.get('known')['branch_run']['schema_version'], 999)

    def test_supported_draft_cannot_bypass_future_authorization(self):
        with self.assertRaisesRegex(ValueError, 'Unattended'): self.engine.start('known')
        self.assertEqual(self.engine.runtimes, {})
