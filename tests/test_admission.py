"""Deterministic capacity and resource barriers; no repositories or providers."""
import threading
import time
import unittest
from types import SimpleNamespace
from cheapos.admission import Admission


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.engine = SimpleNamespace(lock=threading.RLock(), runtimes={}, event=lambda *args: None,
                                      store=SimpleNamespace(publish=lambda task: None))
        self.admission = Admission(self.engine)
        from unittest.mock import patch
        from pathlib import Path
        resolver=patch('cheapos.admission.repository_identity', side_effect=lambda path: str(Path(path).resolve()).replace('/linked-a','/a'))
        resolver.start();self.addCleanup(resolver.stop)

    def runtime(self, branch=False):
        return SimpleNamespace(task={'branch_run': {}} if branch else {}, stop=threading.Event(),
                               started=time.monotonic(), thread=SimpleNamespace(is_alive=lambda: True))

    def test_one_per_mode_and_pending_reservation(self):
        self.engine.runtimes['A'] = self.runtime(True)
        self.admission.require('interactive', 'B')
        with self.assertRaisesRegex(ValueError, 'slot is occupied'): self.admission.require('unattended', 'C')
        with self.assertRaisesRegex(ValueError, 'already running'): self.admission.require('interactive', 'A')
        self.engine.runtimes['B'] = self.runtime()
        self.assertEqual(len(self.admission.snapshot()['active']), 2)
        del self.engine.runtimes['A']
        self.admission.pending['plan'] = 'unattended'
        with self.assertRaises(ValueError): self.admission.require('unattended')
        self.admission.require_idle('A')

    def test_resource_cancel_does_not_release_other_owner(self):
        runtime = self.runtime()
        entered = threading.Event()
        self.engine.event = lambda *args: entered.set()
        errors = []
        def wait():
            try:
                with self.admission.resource('checks', runtime): self.fail('Cancelled waiter entered')
            except InterruptedError: errors.append('cancelled')
        with self.admission.resource('checks', self.runtime()):
            thread = threading.Thread(target=wait)
            runtime.stop.set()
            thread.start()
            self.assertTrue(entered.wait(1))
            thread.join(1)
            self.assertFalse(thread.is_alive())
            self.assertTrue(self.admission.resources['checks'].locked())
        self.assertEqual(errors, ['cancelled'])
        self.assertNotIn('resource_wait', runtime.task)
        self.assertFalse(self.admission.resources['checks'].locked())

    def test_repository_lock_scope_and_admission_during_integration(self):
        self.assertIs(self.admission.repository('/tmp/a'), self.admission.repository('/tmp/a/.'))
        self.assertIs(self.admission.repository('/tmp/a'), self.admission.repository('/tmp/linked-a'))
        self.assertIsNot(self.admission.repository('/tmp/a'), self.admission.repository('/tmp/b'))
        with self.admission.integration('A', '/tmp/a'):
            with self.assertRaisesRegex(ValueError, 'repository operation'): self.admission.require('interactive', 'A')
            self.admission.require('unattended', 'B')
        self.admission.require('interactive', 'A')

    def test_contended_real_ledger_restarts_without_renewing_usage_and_releases_on_error(self):
        from cheapos.branch_budget import Ledger
        runtime=self.runtime(True)
        runtime.task['branch_run']={'limits':{'working_seconds':100},'consumption':{'working_seconds':7},'plan':{}}
        clock=[0]
        ledger=Ledger(runtime,lambda:None,clock=lambda:clock[0])
        runtime.branch_ledger=ledger
        ledger.begin(start_watchdog=False)
        self.addCleanup(ledger.end)
        clock[0]=2
        class Contended:
            def __init__(self): self.calls=0;self.released=False
            def acquire(self, **kwargs):
                self.calls+=1
                if self.calls==1:return False
                clock[0]=52
                return True
            def release(self): self.released=True
        lock=Contended();self.admission.resources['checks']=lock
        with self.admission.resource('checks',runtime):
            self.assertTrue(ledger.active)
            self.assertEqual(ledger.base,9)
        self.assertTrue(lock.released)
        self.assertNotIn('resource_wait',runtime.task)
        lock=Contended();self.admission.resources['checks']=lock
        from unittest.mock import patch
        with patch.object(ledger,'begin',side_effect=ValueError('bookkeeping failed')):
            with self.assertRaisesRegex(ValueError,'bookkeeping failed'):
                with self.admission.resource('checks',runtime):pass
        self.assertTrue(lock.released)
