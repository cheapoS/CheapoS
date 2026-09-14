"""Bounded task admission and cancelable shared laptop resources."""
import threading
import time
from contextlib import contextmanager


def repository_identity(source):
    from pathlib import Path
    from .branch_workspace import source_git
    common = Path(source_git(source, 'rev-parse', '--git-common-dir'))
    if not common.is_absolute(): common = Path(source) / common
    common = common.resolve(strict=True)
    stat = common.stat()
    return str(common), stat.st_dev, stat.st_ino


class Admission:
    def __init__(self, engine):
        self.engine = engine
        self.pending = {}
        self.resources = {name: threading.Lock() for name in ('local_inference', 'checks')}
        self.repositories = {}
        self.operations = {}

    def snapshot(self):
        with self.engine.lock:
            active = [{'task_id': key, 'mode': 'unattended' if 'branch_run' in runtime.task else 'interactive'}
                      for key, runtime in self.engine.runtimes.items()
                      if runtime.thread and runtime.thread.is_alive()]
            active += [{'task_id': key, 'mode': mode} for key, mode in self.pending.items()
                       if key not in {item['task_id'] for item in active}]
            result = {'maximum': 2, 'per_mode': {'interactive': 1, 'unattended': 1}, 'active': active,
                      'resources': {'local_inference': 1, 'checks': 1}}
            for mode in ('interactive', 'unattended'):
                occupied = any(item['mode'] == mode for item in active)
                result[mode] = {'allowed': not occupied, 'reason': ('The ' + mode + ' slot is occupied. Pause that task or wait for it to finish.') if occupied else None}
            return result

    def require(self, mode, task_id=None):
        if task_id in self.operations:
            raise ValueError("This task is completing a repository operation")
        snapshot = self.snapshot()
        if task_id and any(item['task_id'] == task_id for item in snapshot['active']):
            raise ValueError('This task is already running')
        if not snapshot[mode]['allowed']:
            raise ValueError(snapshot[mode]['reason'])

    def require_mutable(self, task_id):
        if task_id in self.operations and self.operations[task_id] != threading.get_ident():
            raise ValueError("This task is completing a repository operation")

    def require_idle(self, task_id):
        self.require_mutable(task_id)
        runtime = self.engine.runtimes.get(task_id)
        if runtime and runtime.thread and runtime.thread.is_alive():
            raise ValueError('Pause this task before changing its saved work')

    def repository(self, source):
        # Repository identity is still revalidated by the existing merge contract.
        identity = repository_identity(source)
        with self.engine.lock:
            return self.repositories.setdefault(identity, threading.RLock())

    @contextmanager
    def integration(self, task_id, source):
        with self.repository(source):
            with self.engine.lock:
                self.require_idle(task_id)
                self.operations[task_id] = threading.get_ident()
            try:
                yield
            finally:
                with self.engine.lock:
                    self.operations.pop(task_id, None)

    @contextmanager
    def resource(self, name, runtime, timeout=None):
        lock = self.resources[name]
        acquired = False
        waiting = False
        ledger = getattr(runtime, 'branch_ledger', None)
        was_active = bool(ledger and ledger.active)
        started = time.monotonic()
        try:
            acquired = lock.acquire(blocking=False)
            if not acquired:
                waiting = True
                runtime.task['resource_wait'] = {'resource': name, 'reason': 'Waiting for the other task to release ' + name.replace('_', ' ')}
                self.engine.event(runtime.task, 'resource_wait', runtime.task['resource_wait']['reason'])
                if was_active: ledger.suspend()
                try:
                    while not acquired:
                        if runtime.stop.is_set(): raise InterruptedError('Task stopped while waiting for ' + name)
                        if timeout is not None and time.monotonic() - started >= timeout:
                            raise TimeoutError("Local inference slot stayed busy; optional consultation skipped")
                        acquired = lock.acquire(timeout=.1)
                finally:
                    runtime.started += time.monotonic() - started
                    runtime.task.pop('resource_wait', None)
                    self.engine.store.publish(runtime.task)
                    if was_active and not runtime.stop.is_set(): ledger.begin()
            if runtime.stop.is_set(): raise InterruptedError('Task stopped')
            yield
        finally:
            try:
                if waiting and 'resource_wait' in runtime.task:
                    runtime.task.pop('resource_wait', None)
                    self.engine.store.publish(runtime.task)
            finally:
                if acquired: lock.release()
