"""Installation storage policy and task-owned cleanup. Never sweep Git worktrees.

Merge receipts authorize reclamation of identical task files, not deletion of
later edits. Trash expiry is separately opted into by this installation's owner.
"""
import copy
import hashlib
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .storage import write_json
from .workspace import git
from .branch_workspace import source_git

DEFAULTS = {'reclaim_merged': True, 'trash_days': None}


def reclaimed(task):
    return task.get('workspace_cleanup', {}).get('state') == 'reclaimed'


def task_directory(store, task_id):
    if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', task_id):
        raise ValueError('Invalid saved task identity')
    path = store.root / 'tasks' / task_id
    # resolve() alone would silently accept symlinked parent directories.
    if any(p.is_symlink() for p in (path, path.parent, store.root)) or path.resolve() != path:
        raise ValueError('Task storage identity changed; files retained')
    return path


def owned_workspace(store, task, *, quarantine=False):
    directory = task_directory(store, task['id'])
    expected = directory / 'workspace'
    mapping = (task.get('branch_run') or {}).get('workspace_mapping') or {}
    paths = [p for p in (task.get('workspace'), mapping.get('workspace')) if p]
    if any(Path(p) != expected for p in paths):
        raise ValueError('Workspace is outside this task’s owned directory; files retained')
    if not paths and (expected.exists() or (directory / 'workspace-reclaim').exists()):
        raise ValueError('Workspace ownership was not recorded; files retained')
    path = directory / 'workspace-reclaim' if quarantine else expected
    if path.is_symlink() or path.resolve() != path:
        raise ValueError('Workspace is a link or its location changed; files retained')
    owner = task.get('workspace_owner')
    if path.exists() and owner and [path.stat().st_dev, path.stat().st_ino] != owner:
        raise ValueError('Workspace identity changed; files retained')
    identity = mapping.get('workspace_identity')
    if path.exists() and identity and [path.stat().st_dev, path.stat().st_ino] != identity[-2:]:
        raise ValueError('Saved branch workspace identity changed; files retained')
    return path


def register(store, task):
    """Record ownership at creation; legacy records still require exact layout."""
    path = owned_workspace(store, task)
    if path.is_dir():
        task['workspace_owner'] = [path.stat().st_dev, path.stat().st_ino]


def remove_task_files(store, task):
    """Permanent Trash deletion: only this recorded task, including legacy links."""
    directory = task_directory(store, task['id'])
    path = owned_workspace(store, task)
    owned_workspace(store, task, quarantine=True)
    if (path / '.git').is_symlink():
        raise ValueError('Workspace Git directory is a link; files retained')
    if (path / '.git').is_file():
        source = task.get('source') or (task.get('branch_run', {}).get('workspace_mapping') or {}).get('source')
        if not source:
            raise ValueError('Linked workspace source is unavailable; files retained')
        records = source_git(source, 'worktree', 'list', '--porcelain', '-z').split('\0')
        if 'worktree ' + str(path) not in records:
            raise ValueError('Linked workspace ownership differs; files retained')
        # Explicit Trash deletion may discard its own uncommitted work only.
        git(source, 'worktree', 'remove', '--force', str(path))
    if directory.exists():
        shutil.rmtree(directory)


def merge_identity(task):
    p = task.get('pull_request') or {}
    if p:
        if (p.get('head') and p.get('merged_head') == p['head']
                and p.get('ci', {}).get('state') == 'merged'
                and p['ci'].get('head', p['head']) == p['head']):
            return {'source': p['source'], 'commit': p['head'], 'publication': p['id']}
        return None  # Open/closed PRs are never local-merge cleanup candidates.
    run = task.get('branch_run') or {}
    receipt = run.get('merge_receipt') or {}
    if (run.get('status') == 'merged' and receipt.get('stage') == 'completed'
            and receipt.get('feature_tip') == run.get('expected_feature_tip')):
        return {'source': run['workspace_mapping']['source'], 'commit': receipt['feature_tip'], 'publication': receipt['id']}
    return None


def file_bytes(path):
    """Logical bytes, without following symlinks or reading file contents."""
    total = 0
    if path.is_symlink():
        return path.lstat().st_size
    if not path.exists():
        return 0
    for directory, dirs, files in os.walk(path, followlinks=False):
        for name in files + [d for d in dirs if (Path(directory) / d).is_symlink()]:
            try:
                total += (Path(directory) / name).lstat().st_size
            except FileNotFoundError:
                continue
    return total


def _walk_error(error):
    raise error


def unchanged(task, path, merged):
    """Compare real bytes/modes with the published snapshot, including new files.

    Do not trust stale task.patch, index flags, or Git's ignored-file filtering.
    Unknown ignored files (including caches) conservatively retain the copy.
    """
    if not (path / '.git').is_dir() or (path / '.git').is_symlink():
        raise ValueError('Automatic cleanup requires an independent task copy')
    if Path(git(path, 'rev-parse', '--show-toplevel').strip()).resolve() != path:
        raise ValueError('Workspace repository identity changed')
    skipped = set(task.get('snapshot', {}).get('skipped', []))
    mapping = task.get('branch_run', {}).get('workspace_mapping') or {}
    skipped.update(mapping.get('skipped', []))
    expected = {}
    for entry in source_git(merged['source'], 'ls-tree', '-rz', merged['commit'], binary=True).split(b'\0'):
        if entry:
            header, name = entry.split(b'\t', 1)
            mode, kind, oid = header.decode().split()
            name = name.decode('utf-8')
            if name not in skipped:
                expected[name] = (mode, kind, oid)
    algorithm = git(path, 'rev-parse', '--show-object-format').strip()
    actual = {}
    for directory, dirs, files in os.walk(path, followlinks=False, onerror=_walk_error):
        if Path(directory) == path:
            dirs[:] = [d for d in dirs if d != '.git']
        if any((Path(directory) / d).is_symlink() for d in dirs):
            raise ValueError('Workspace contains linked files; retained for inspection')
        for name in files:
            file = Path(directory) / name
            if not file.is_file() or file.is_symlink():
                raise ValueError('Workspace contains linked or special files; retained for inspection')
            data = file.read_bytes()
            oid = hashlib.new(algorithm, b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            actual[file.relative_to(path).as_posix()] = ('100755' if file.stat().st_mode & 0o111 else '100644', 'blob', oid)
    if actual != expected:
        raise ValueError('Unpublished edits or extra files remain in the task copy')
    # A distinct staged version is saved work too, even if disk matches the PR.
    baseline = {}
    for entry in git(path, 'ls-tree', '-rz', 'HEAD', binary=True).split(b'\0'):
        if entry:
            header, name = entry.split(b'\t', 1)
            baseline[name.decode()] = tuple(header.decode().split())
    staged = {}
    for entry in git(path, 'ls-files', '--stage', '-z', binary=True).split(b'\0'):
        if entry:
            header, name = entry.split(b'\t', 1)
            mode, oid, stage = header.decode().split()
            value = (mode, 'blob', oid)
            if stage != '0':
                raise ValueError('Unresolved index entries remain in the task copy')
            staged[name.decode()] = value
    if any(staged.get(name) not in (baseline.get(name), actual.get(name)) for name in baseline.keys() | actual.keys() | staged.keys()):
        raise ValueError('Unpublished staged edits remain in the task copy')
    refs = git(path, 'for-each-ref', '--format=%(refname)').splitlines()
    if len(refs) != 1 or not refs[0].startswith('refs/heads/'):
        raise ValueError('Additional Git branches, tags or stashes remain in the task copy')
    if mapping.get('workspace_head') and git(path, 'rev-parse', 'HEAD').strip() != mapping['workspace_head']:
        raise ValueError('Private branch head changed after publication; files retained')


def cleanup_inventory(path):
    """Local proof for restart-safe deletion, including Git metadata."""
    result = {}
    for directory, dirs, files in os.walk(path, followlinks=False, onerror=_walk_error):
        for name in dirs + files:
            file = Path(directory) / name
            if file.is_symlink():
                raise ValueError('Linked files cannot be automatically reclaimed')
            if file.is_dir():
                continue
            if not file.is_file():
                raise ValueError('Special files cannot be automatically reclaimed')
            digest = hashlib.sha256()
            with file.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            result[file.relative_to(path).as_posix()] = [file.stat().st_mode, digest.hexdigest()]
    return result


class Maintenance:
    def __init__(self, engine):
        self.engine = engine
        self.file = engine.store.root / 'storage-settings.json'
        self.lock = threading.RLock()
        self.settings_lock = threading.RLock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.last_run = None

    def settings(self):
        try:
            value = json.loads(self.file.read_text())
        except FileNotFoundError:
            return dict(DEFAULTS)
        self.validate(value)  # Invalid settings disable maintenance, never reset consent.
        return value

    @staticmethod
    def validate(value):
        if not isinstance(value, dict) or set(value) != set(DEFAULTS) or type(value['reclaim_merged']) is not bool:
            raise ValueError('Invalid installation storage settings')
        days = value['trash_days']
        if days is not None and (type(days) is not int or not 1 <= days <= 3650):
            raise ValueError('Trash retention must be Never or 1–3,650 days')

    def configure(self, values):
        self.validate(values)
        with self.settings_lock:
            write_json(self.file, values)
        self.wake.set()
        return {'settings': values, 'message': 'Storage settings saved for this installation.'}

    def start(self):
        if self.thread is not None:
            return
        self.thread = threading.Thread(target=self._loop, name='storage-maintenance', daemon=True)
        self.thread.start()

    def shutdown(self):
        self.stop.set(); self.wake.set()
        if self.thread:
            self.thread.join(timeout=2)

    def _loop(self):
        while not self.stop.is_set():
            try:
                self.sweep()
            except Exception:
                self.last_run = {'error': 'Storage maintenance could not finish. Open Storage to inspect the remaining tasks.'}
            self.wake.wait(300)
            self.wake.clear()

    def _ids(self):
        with self.engine.store.lock:
            return list(self.engine.store.tasks)

    def _record(self, task_id):
        with self.engine.store.lock:
            task = self.engine.store.tasks[task_id]
            run = task.get('branch_run') or {}
            return copy.deepcopy({**{k: task[k] for k in ('id', 'title', 'source', 'workspace', 'workspace_owner', 'status', 'snapshot', 'workspace_cleanup', 'pull_request', 'commit_pending', 'integration_preparation') if k in task},
                'branch_run': {k: run[k] for k in ('status', 'workspace_mapping', 'expected_feature_tip', 'merge_receipt', 'merge_operation') if k in run}})

    def _busy(self, task):
        engine = self.engine
        runtime = engine.runtimes.get(task['id'])
        preview = engine.previews.runs.get(task['id'])
        return (task['id'] in engine.admission.operations or task['id'] in engine.admission.pending
                or (runtime and runtime.thread and runtime.thread.is_alive())
                or (preview and preview['thread'].is_alive()) or task.get('commit_pending')
                or task.get('branch_run', {}).get('merge_operation')
                or task['id'] in getattr(engine, '_integration_preparing', set())
                or task.get('integration_preparation', {}).get('status') in {'running', 'accepted'}
                or task.get('status') in {'running', 'reviewing', 'waiting_approval', 'waiting_retry', 'stopping'})

    def inspect(self, task, *, measure=False):
        metadata = self.engine.store.metadata(task['id'])
        row = {'id': task['id'], 'title': metadata['custom_title'] or task.get('title') or task['id'],
               'trashed_at': metadata['trashed_at'], 'state': 'retained', 'reason': '', 'workspace_bytes': 0}
        try:
            path = owned_workspace(self.engine.store, task)
            pending = task.get('workspace_cleanup', {}).get('state') == 'reclaiming'
            quarantine = owned_workspace(self.engine.store, task, quarantine=True)
            if measure:
                row['workspace_bytes'] = file_bytes(path) + file_bytes(quarantine)
            if self._busy(task):
                row['reason'] = 'Task or preview is active; files retained'
            elif metadata['trashed_at']:
                row['reason'] = 'Restorable Trash; retained until the selected expiry or Empty Trash'
            elif reclaimed(task):
                if path.exists() or quarantine.exists():
                    raise ValueError('Files appeared after cleanup; retained for inspection')
                row.update(state='reclaimed', reason='Task copy reclaimed; history and evidence retained')
            elif pending:
                self._verify_cleanup(task, path, quarantine)
                row.update(state='eligible', reason='Finishing an interrupted cleanup of a confirmed merge')
            elif not path.exists():
                row.update(state='missing', reason='No task copy on disk')
            elif quarantine.exists():
                raise ValueError('Unexpected cleanup directory; files retained')
            elif merged := merge_identity(task):
                unchanged(task, path, merged)
                row.update(state='eligible', reason='Confirmed merge; no unpublished edits remain')
            else:
                row['reason'] = 'Unfinished work, open PR, or no confirmed merge'
        except (ValueError, OSError, KeyError) as error:
            row['reason'] = str(error)
        return row

    def view(self):
        settings = self.settings()
        rows = []
        for task_id in self._ids():
            try:
                rows.append(self.inspect(self._record(task_id), measure=True))
            except KeyError:  # A concurrent Trash expiry already removed this row.
                continue
        total = file_bytes(self.engine.store.root / 'tasks')
        return {'settings': settings, 'tasks': rows, 'task_bytes': total,
                'workspace_bytes': sum(r['workspace_bytes'] for r in rows),
                'eligible_bytes': sum(r['workspace_bytes'] for r in rows if r['state'] == 'eligible'),
                'eligible_count': sum(r['state'] == 'eligible' for r in rows), 'last_run': self.last_run}

    def _proof_file(self, task):
        return task_directory(self.engine.store, task['id']) / 'workspace-cleanup.json'

    def _verify_cleanup(self, task, path, quarantine):
        receipt = task['workspace_cleanup']
        if receipt['merge'] != merge_identity(task) or not task.get('workspace_owner'):
            raise ValueError('Cleanup authority changed; files retained')
        proof_file = self._proof_file(task)
        if proof_file.is_symlink():
            raise ValueError('Cleanup evidence is a link; files retained')
        raw = proof_file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != receipt['proof']:
            raise ValueError('Cleanup evidence changed; files retained')
        if path.exists() and quarantine.exists():
            raise ValueError('Both cleanup locations exist; files retained')
        current = path if path.exists() else quarantine
        proof = json.loads(raw)
        # Deletion may have stopped part way through. Only matching surviving
        # files may be removed; a new or changed file cancels reclamation.
        if any(proof.get(name) != value for name, value in cleanup_inventory(current).items()):
            raise ValueError('Files changed during cleanup; retained for inspection')

    def _save_cleanup(self, task):
        # GitHub status and chat metadata may change while files are checked.
        # Save only our receipt into the latest task; never restore an old copy.
        with self.engine.lock:
            current = self.engine.store.get(task['id'])
            if merge_identity(current) != task['workspace_cleanup']['merge']:
                raise ValueError('The publication changed during cleanup; files retained')
            current['workspace_owner'] = task['workspace_owner']
            current['workspace_cleanup'] = copy.deepcopy(task['workspace_cleanup'])
            self.engine.store.save(current)

    def reclaim(self, task_id):
        engine = self.engine
        with self.lock:
            with engine.lock:
                task = self._record(task_id)
                if self._busy(task) or engine.store.metadata(task_id)['trashed_at']:
                    return False
                if not merge_identity(task) or reclaimed(task):
                    return False
                engine.admission.operations[task_id] = threading.get_ident()
            try:
                # No global lock during file/Git I/O. Admission prevents new
                # app work; an atomic rename isolates the terminal copy.
                task = engine.store.get(task_id)
                path = owned_workspace(engine.store, task)
                quarantine = owned_workspace(engine.store, task, quarantine=True)
                if task.get('workspace_cleanup', {}).get('state') != 'reclaiming':
                    if quarantine.exists():
                        raise ValueError('Unexpected cleanup directory; files retained')
                    if not path.exists():
                        return False
                    merged = merge_identity(task)
                    unchanged(task, path, merged)
                    register(engine.store, task)
                    amount = file_bytes(path)
                    write_json(self._proof_file(task), cleanup_inventory(path))
                    # A writer could change files between the first comparison
                    # and inventory capture. Recheck against the publication.
                    unchanged(task, path, merged)
                    task['workspace_cleanup'] = {'state': 'reclaiming', 'merge': merged, 'bytes': amount,
                        'proof': hashlib.sha256(self._proof_file(task).read_bytes()).hexdigest()}
                    self._save_cleanup(task)  # Durable intent before moving files.
                self._verify_cleanup(task, path, quarantine)
                if path.exists():
                    path.rename(quarantine)
                self._verify_cleanup(task, path, quarantine)
                if quarantine.exists():
                    shutil.rmtree(quarantine)
                task['workspace_cleanup'].update(state='reclaimed', at=datetime.now(timezone.utc).isoformat())
                self._save_cleanup(task)
                self._proof_file(task).unlink(missing_ok=True)
                return True
            finally:
                with engine.lock:
                    engine.admission.operations.pop(task_id, None)

    def delete_trashed(self, task_id):
        with self.lock, self.engine.lock:
            task = self._record(task_id)
            if not self.engine.store.metadata(task_id)['trashed_at'] or self._busy(task):
                return False
            self.engine.admission.operations[task_id] = threading.get_ident()
        try:
            self.engine.store.delete_task(task_id)
            self.engine.runtimes.pop(task_id, None)
            self.engine.command_permissions.pop(task_id, None)
            return True
        finally:
            with self.engine.lock:
                self.engine.admission.operations.pop(task_id, None)

    def sweep(self, *, empty_trash=False, now=None):
        with self.lock:
            settings = self.settings()
            stamp = time.time() if now is None else now
            result = {'reclaimed': 0, 'deleted': 0, 'retained': 0, 'errors': [], 'status': 'ok'}
            for task_id in self._ids():
                if self.stop.is_set(): break
                try:
                    settings = self.settings()  # Honor changes before each next task.
                    task = self._record(task_id)
                    trashed = self.engine.store.metadata(task_id)['trashed_at']
                    expiry = datetime.fromisoformat(trashed).timestamp() + settings['trash_days'] * 86400 if trashed and settings['trash_days'] is not None else None
                    if trashed and (empty_trash or (expiry is not None and stamp >= expiry)):
                        key = 'deleted' if self.delete_trashed(task_id) else 'retained'
                        result[key] += 1
                    elif not empty_trash and not trashed and settings['reclaim_merged'] and not reclaimed(task):
                        if self.reclaim(task_id): result['reclaimed'] += 1
                except (ValueError, OSError, KeyError) as error:
                    result['errors'].append({'id': task_id, 'message': str(error)})
            self.last_run = {**result, 'at': datetime.now(timezone.utc).isoformat()}
            return self.last_run
