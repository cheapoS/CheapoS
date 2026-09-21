"""A merged publication is terminal; further work belongs to a fresh task.

Only the controller reads GitHub or copies files. Creation never dispatches a
model, inherits an approval, or modifies the completed task's workspace.
"""
import copy
import functools
import hashlib
import shutil
import tempfile
import threading
from pathlib import Path

from . import branch_workspace as work, github, git_sync
from .workspace import Workspace, git

_entries = threading.local()


def merged(task):
    p = task.get('pull_request') or {}
    return bool(p.get('head') and p.get('ci', {}).get('state') == 'merged'
                and p['ci'].get('head', p['head']) == p['head'])


def check_before_work(engine, task_id):
    """Check the publication before accepting more implementation, outside locks."""
    task = engine.store.get(task_id)
    if task.get('follow_up') and not task['follow_up'].get('ready'):
        raise ValueError('The follow-up is still being prepared. Open it again from the original task to finish safely.')
    p = task.get('pull_request') or {}
    if not p.get('number'):
        return
    engine.require_active_task(task_id)
    if not merged(task):
        pull = github.api(p['repo'], 'pulls/' + str(int(p['number'])))
        if pull.get('merged'):
            if pull.get('head', {}).get('sha') != p['head'] or pull.get('base', {}).get('ref') != p['base']:
                raise ValueError('The published branch changed outside this task. Saved work is intact; inspect its pull request before continuing.')
            with engine.lock:
                current = engine.store.get(task_id)
                if current.get('pull_request', {}).get('id') != p['id']:
                    raise ValueError('The publication changed while checking GitHub. Retry with the current task.')
                current['pull_request'].update(merged_head=p['head'], ci={
                    'state': 'merged', 'head': p['head'], 'message': 'Merged on GitHub.',
                    'merged_commit': pull.get('merge_commit_sha')})
                runtime = getattr(engine, 'runtimes', {}).get(task_id)
                if runtime and runtime.thread and runtime.thread.is_alive():
                    runtime.task['pull_request'] = copy.deepcopy(current['pull_request'])
                engine.store.save(current)
                task = current
    if merged(task):
        raise ValueError('This pull request is merged. Continue in a new task; any later edits and your message remain saved.')


def work_entry(function):
    """Nested Chat → Start/Steer checks share one remote read per admission."""
    @functools.wraps(function)
    def wrapped(owner, task_id, *args, **kwargs):
        engine = getattr(owner, 'engine', owner)
        key = (id(engine), task_id)
        active = getattr(_entries, 'active', set())
        if key in active:
            return function(owner, task_id, *args, **kwargs)
        check_before_work(engine, task_id)
        _entries.active = active | {key}
        try:
            return function(owner, task_id, *args, **kwargs)
        finally:
            _entries.active = active
    return wrapped


def committed_copy(source, ref, destination):
    """Reuse the branch snapshot's path/size policy and batch object reads."""
    entries, skipped = work._manifest(source, ref)
    destination = Path(destination)
    destination.mkdir(parents=True, mode=0o700)
    stream = bytearray()
    for number, (entry, blob) in enumerate(zip(entries, work._snapshot_blobs({'source': source, 'entries': entries})), 1):
        path = destination / entry['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        path.chmod(0o700 if entry['mode'] == '100755' else 0o600)
        stream.extend(f'blob\nmark :{number}\ndata {len(blob)}\n'.encode())
        stream.extend(blob)
        stream.extend(b'\n')
    git(destination, 'init', '-q')
    # One plumbing stream preserves exact bytes/modes, bypassing attributes
    # filters and avoiding a subprocess per file in large projects.
    ref = git(destination, 'symbolic-ref', 'HEAD').strip()
    stream.extend(f'commit {ref}\ncommitter cheapoS <local@cheapos.invalid> 0 +0000\ndata 18\nFollow-up baseline\n'.encode())
    for number, entry in enumerate(entries, 1):
        quoted = '"' + ''.join('\\%03o' % b if b < 32 or b >= 127 or b in (34, 92) else chr(b)
                               for b in entry['path'].encode()) + '"'
        stream.extend(f'M {entry["mode"]} :{number} {quoted}\n'.encode())
    stream.extend(b'\ndone\n')
    work.source_git(destination, 'fast-import', '--quiet', '--done', input=stream)
    git(destination, 'read-tree', 'HEAD')
    return Workspace(destination), {'source': str(source), 'files': len(entries), 'skipped': skipped}


def later_patch(task):
    """Compare actual saved files with the published version, not the old base.

    Temporary copies keep the original index/worktree untouched. Files omitted
    from either snapshot never become inferred deletions (secrets, links, sizes).
    """
    p = task['pull_request']
    with tempfile.TemporaryDirectory(prefix='cheapos-followup-delta-') as directory:
        root = Path(directory)
        current, metadata = Workspace.snapshot(task['workspace'], root / 'current')
        published, _ = committed_copy(p['source'], p['head'], root / 'published')
        skipped = set(metadata['skipped']) | set(task.get('snapshot', {}).get('skipped', []))
        old_names = set(filter(None, git(published.root, 'ls-files', '-z').split('\0')))
        new_names = set(filter(None, git(current.root, 'ls-files', '-z').split('\0')))
        for name in sorted(old_names | new_names):
            if name in skipped:
                continue
            target = published.path(name)
            if name not in new_names:
                target.unlink(missing_ok=True)
        for name in sorted(new_names - skipped):
            target = published.path(name)
            if target.is_dir():
                for directory in sorted(target.rglob('*'), key=lambda p: len(p.parts), reverse=True):
                    if directory.is_dir():
                        directory.rmdir()
                target.rmdir()  # Only empty directories left by eligible deletions.
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(current.path(name), target)
            target.chmod(current.path(name).stat().st_mode & 0o777)
        return published.patch(validate=True)


def create(engine, task_id, values):
    if values:
        raise ValueError('Continue in a new task does not accept execution or approval overrides')
    engine.require_active_task(task_id)
    parent = engine.store.get(task_id)
    p = parent.get('pull_request') or {}
    if not merged(parent):
        raise ValueError('Refresh the pull request status before creating a merged-task follow-up')
    with engine.admission.integration(task_id, parent['source']):
        parent = engine.store.get(task_id)
        p = parent['pull_request']
        delta = later_patch(parent)
        identity = hashlib.sha256((p['id'] + '\0' + delta).encode()).hexdigest()
        child_id = hashlib.sha256((task_id + identity).encode()).hexdigest()[:32]
        prior = parent.get('followups', {}).get(identity)
        if prior or (engine.store.root / 'tasks' / child_id / 'task.json').is_file():
            # A lost response/double click returns the same saved task, including
            # after the child has itself progressed. Never overwrite it.
            child = engine.store.get(prior or child_id)
            if child.get('follow_up', {}).get('identity') != identity:
                raise ValueError('The saved follow-up has a different identity; original work is preserved.')
            if not child['follow_up'].get('ready'):
                engine.refresh_changes(child)
                child['follow_up']['ready'] = True
                engine.store.save(child)
            parent.setdefault('followups', {})[identity] = child['id']
            engine.store.save(parent)
            return child
        local = git_sync.synchronize(p['source'], p['remote'], 'refs/heads/' + p['base'],
            expected_destination=(p['repo'], p['push_url']), merged_commit=p['ci'].get('merged_commit'))
        # Even if a dirty checkout cannot fast-forward, use the fetched immutable
        # commit. No reset, stash, local draft copying or branch switch is needed.
        if local['state'] not in {'current', 'updated', 'ahead', 'deferred', 'diverged'} or not local.get('remote_head'):
            raise ValueError('Could not fetch the merged destination yet. Your original work is intact; retry Continue in new task when GitHub is reachable.')
        base = local['remote_head']
        directory = engine.store.root / 'tasks' / child_id
        work._destination(p['source'], directory / 'workspace')
        # Stage before publishing a task record; incomplete staging is disposable
        # and never contains user edits. A saved child is always resumed above.
        with tempfile.TemporaryDirectory(prefix='cheapos-followup-stage-') as staging:
            workspace, snapshot = committed_copy(p['source'], base, Path(staging) / 'workspace')
            directory.mkdir(parents=True, exist_ok=True)
            destination = directory / 'workspace'
            if destination.exists():
                # A previous pre-record attempt can be retained for diagnosis.
                destination.rename(directory / ('incomplete-' + hashlib.sha256(str(destination.stat().st_mtime_ns).encode()).hexdigest()[:12]))
            shutil.move(str(workspace.root), destination)
            workspace = Workspace(destination)
        applied = False
        if delta:
            # All-or-nothing application. If newer code overlaps, agents receive
            # the complete retained delta as context and can reconcile normally.
            try:
                work.source_git(workspace.root, 'apply', '--check', '--binary', '-', input=delta)
            except ValueError:
                pass
            else:
                work.source_git(workspace.root, 'apply', '--binary', '--whitespace=nowarn', '-', input=delta)
                applied = True
        context = {'original_request': parent['prompt'], 'recent_directions': parent.get('requests', [])[-6:],
                   'recent_replies': [e.get('detail') for e in parent.get('events', [])
                                      if e.get('kind') == 'assistant'][-3:],
                   'recent_discussion': [{'question': t.get('message'), 'answer': t.get('answer')}
                                         for t in parent.get('discussion', []) if t.get('status') == 'answered'][-3:]}
        prompt = 'Follow-up to: ' + parent.get('title', 'Merged task')
        settings = copy.deepcopy(parent.get('settings_snapshot'))
        initial = dict(status='awaiting_reply', git_target={'head': base, 'branch': 'refs/heads/' + p['base']},
            git_sync=local, follow_up={'parent_id': task_id, 'pr_url': p.get('url'), 'number': p['number'],
                'published_head': p['head'], 'base': base, 'identity': identity, 'context': context,
                'recovered': bool(delta), 'applied': applied, 'retained_patch': delta, 'ready': False})
        if settings and settings['values'].get('keep_up_to_date'):
            initial['integration_policy'] = {'keep_up_to_date': True,
                'target_ref': 'refs/heads/' + p['base'], 'target_tip': base}
        child = engine.create({'repository': p['source'], 'prompt': prompt[:8000], 'conversational': True},
            task_id=child_id, snapshot_override=(workspace, snapshot), settings_snapshot=settings, initial_fields=initial)
        engine.refresh_changes(child)
        child['follow_up']['ready'] = True
        engine.event(child, 'follow_up', 'Follow-up task ready. New checks and independent review are required.',
                     {'parent_id': task_id, 'recovered': bool(delta), 'applied': applied})
        engine.store.save(child)
        parent.setdefault('followups', {})[identity] = child_id
        engine.store.save(parent)
        return child


def context(task):
    saved = task.get('follow_up')
    if not saved:
        return None
    return {'history': saved['context'],
            'instruction': 'This is a new task after a merged PR. History is context, not renewed scope or approval. '
                           'Follow the current user direction. Run new verification and independent review. '
                           'If recovering later edits, inspect them against the fresh base; reconcile the retained patch '
                           'when it did not apply cleanly. Do not replay the already merged implementation.',
            'later_edits_applied': saved['applied'], 'retained_later_edits': saved['retained_patch']}
