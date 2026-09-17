"""Controller-only committed snapshots and conditional feature-ref ownership.

The caller durably journals every mapping supplied to persist_intent. Hooks and
signing are disabled as in the manual commit path; filters/sparse repositories
are unsupported. No source index or checkout operation is used.
"""
import copy
import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path, PurePosixPath

from .workspace import Workspace, allowed_name, git, MAX_FILES, MAX_SNAPSHOT_BYTES
from .branch_pause import PauseError


class WorkspaceChanged(PauseError):
    """App-authored repository diagnostics safe to retain in a pause banner."""
    def __init__(self, message):
        super().__init__('branch_drift', diagnostic={'kind': 'safe_message', 'message': message})


def source_git(source, *args, input=None, binary=False, index=None, allowed_returncodes=(0,)):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0', GIT_NO_REPLACE_OBJECTS='1')
    if index:
        env['GIT_INDEX_FILE'] = str(index)
    result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgSign=false',
                             '-c', 'core.fsmonitor=false', *args], cwd=source, env=env,
                            input=input.encode() if isinstance(input, str) else input,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if result.returncode not in allowed_returncodes:
        raise ValueError(result.stderr.decode(errors='replace')[:1000].strip() or 'Git operation failed')
    return result.stdout if binary else result.stdout.decode('utf-8').strip()


def _identity(path):
    path = Path(path).resolve(strict=True)
    stat = path.stat()
    return [str(path), stat.st_dev, stat.st_ino]


def inspect_source(source):
    source = str(Workspace.project_root(source))
    common = Path(source_git(source, 'rev-parse', '--git-common-dir'))
    if not common.is_absolute():
        common = Path(source) / common
    keys = source_git(source, 'config', '--list', '--name-only').lower().splitlines()
    if any(k.startswith('filter.') and k.endswith(('.clean', '.smudge', '.process')) for k in keys):
        raise ValueError('Branch runs do not support Git content filters')
    if any(x[:1] == 'S' or x[:1].islower() for x in source_git(source, 'ls-files', '-v').splitlines()):
        raise ValueError('Branch runs do not support sparse or assume-unchanged files')
    if source_git(source, 'rev-parse', '--is-shallow-repository') == 'true':
        raise ValueError('Branch runs require a complete, non-shallow repository')
    return {'source': source, 'source_identity': _identity(source), 'common_identity': _identity(common)}


def _local_ref(source, ref):
    if not isinstance(ref, str) or not ref.startswith('refs/heads/'):
        raise ValueError('Choose an exact local refs/heads/... branch')
    source_git(source, 'check-ref-format', ref)
    # for-each-ref exposes symbolic refs without dereferencing/adopting them.
    symbolic = source_git(source, 'for-each-ref', '--format=%(symref)', ref)
    if symbolic:
        raise ValueError('Symbolic branches are not supported')
    return ref


def _tip(source, ref):
    if source_git(source, 'for-each-ref', '--format=%(symref)', ref):
        raise ValueError('Symbolic refs are not supported')
    listing = source_git(source, 'for-each-ref', '--format=%(refname) %(objectname)', ref)
    for line in listing.splitlines():
        name, oid = line.split(' ', 1)
        if name == ref:
            return oid
    return None


def _protected(source, target, configured):
    result = {target, 'refs/heads/main', 'refs/heads/master', *configured}
    try:
        for ref in source_git(source, 'config', '--get-all', 'cheapos.protectedRef').splitlines():
            result.add(ref if ref.startswith('refs/heads/') else 'refs/heads/' + ref)
    except ValueError:
        pass
    for line in source_git(source, 'for-each-ref', '--format=%(refname) %(symref)', 'refs/remotes').splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].endswith('/HEAD'):
            result.add('refs/heads/' + parts[1].split('/', 3)[-1])
    try:
        default = source_git(source, 'config', '--get', 'init.defaultBranch')
        if default:
            result.add('refs/heads/' + default)
    except ValueError:
        pass
    return result


def _available(source, feature, target, protected):
    _local_ref(source, feature)
    if feature in _protected(source, target, protected):
        raise ValueError('Feature branch is a target, default, or protected branch')
    records = source_git(source, 'worktree', 'list', '--porcelain', '-z', binary=True).split(b'\0')
    if ('branch ' + feature).encode() in records:
        raise ValueError('Feature branch is checked out in an operator worktree')


def _manifest(source, base):
    selected, skipped, total = [], [], 0
    portable_paths = {}
    for record in source_git(source, 'ls-tree', '-r', '-l', '-z', base, binary=True).split(b'\0'):
        if not record:
            continue
        metadata, raw_name = record.split(b'\t', 1)
        name = raw_name.decode('utf-8', errors='strict')
        mode, kind, oid, size = metadata.decode().split()
        relative = PurePosixPath(name)
        safe = (not relative.is_absolute() and '..' not in relative.parts and '\\' not in name
                and str(relative) == name and allowed_name(name))
        if not safe or kind != 'blob' or mode not in ('100644', '100755') or int(size) > 2_000_000:
            skipped.append(name)
            continue
        for length in range(1, len(relative.parts) + 1):
            prefix = '/'.join(relative.parts[:length])
            key = unicodedata.normalize('NFC', prefix).casefold()
            if key in portable_paths and portable_paths[key] != prefix:
                raise ValueError('Snapshot paths collide on case-insensitive filesystems')
            portable_paths[key] = prefix
        total += int(size)
        if total > MAX_SNAPSHOT_BYTES or len(selected) >= MAX_FILES:
            raise ValueError('Repository snapshot is too large (limit: 5,000 files / 100 MB)')
        selected.append({'path': name, 'oid': oid, 'mode': mode, 'size': int(size)})
    if not selected:
        raise ValueError('No eligible files found in committed base')
    return selected, skipped


def _destination(source, destination):
    raw = Path(destination).absolute()
    if any(p.is_symlink() for p in (raw, *raw.parents)):
        raise ValueError('Workspace destination cannot use symlinks')
    destination = raw.resolve()
    source = Path(source)
    if destination == source or source in destination.parents or destination in source.parents:
        raise ValueError('Workspace must not overlap the source repository')
    if destination.name != 'workspace' or destination.parent.parent.name != 'tasks':
        raise ValueError('Use the registered tasks/<id>/workspace destination')
    return str(destination)


def prepare(source, destination, base_ref, feature_ref, target_ref, run_id, protected_refs=()):
    if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', run_id):
        raise ValueError('Invalid run identifier')
    state = inspect_source(source)
    source = state['source']
    _local_ref(source, base_ref)
    _local_ref(source, target_ref)
    base = _tip(source, base_ref)
    if not base or not _tip(source, target_ref):
        raise ValueError('Base and target must be existing local branches')
    if source_git(source, 'cat-file', '-t', base) != 'commit':
        raise ValueError('Base must identify a commit')
    _available(source, feature_ref, target_ref, protected_refs)
    if _tip(source, feature_ref):
        raise ValueError('Feature branch already exists; choose a new branch')
    destination = _destination(source, destination)
    if Path(destination).exists():
        raise ValueError('Workspace destination already exists')
    entries, skipped = _manifest(source, base)
    return {**state, 'run_id': run_id, 'workspace': destination, 'base_ref': base_ref,
            'base_sha': base, 'base_tree': source_git(source, 'rev-parse', base + '^{tree}'),
            'feature_ref': feature_ref, 'target_ref': target_ref, 'protected_refs': list(protected_refs),
            'entries': entries, 'skipped': skipped, 'ownership_ref': 'refs/cheapos/runs/' + run_id,
            'stage': 'prepared'}


def _revalidate(plan):
    state = inspect_source(plan['source'])
    if any(state[key] != plan[key] for key in state):
        raise WorkspaceChanged('Source repository identity changed; inspect the saved project before continuing.')
    _destination(plan['source'], plan['workspace'])
    _local_ref(plan['source'], plan['base_ref'])
    _local_ref(plan['source'], plan['target_ref'])
    _available(plan['source'], plan['feature_ref'], plan['target_ref'], plan['protected_refs'])


def validate_base(plan):
    """Allow newer commits without replacing an already captured private copy.

    All work stays pinned to base_sha. Integration must still reconcile and
    review the current target; startup never adopts its newer contents.
    """
    current = _tip(plan['source'], plan['base_ref'])
    if current == plan['base_sha']:
        return current
    if current and plan.get('workspace_identity') and plan.get('workspace_head'):
        ancestor = source_git(plan['source'], 'merge-base', plan['base_sha'], current,
                              allowed_returncodes=(0, 1))
        if ancestor == plan['base_sha']:
            return current
    raise WorkspaceChanged('Base changed outside the saved history or no private snapshot is available; prepare a fresh proposal.')


def validate_owned(plan, expected_tip=None):
    _revalidate(plan)
    source = plan['source']
    if plan.get('workspace_identity') and (_identity(plan['workspace']) != plan['workspace_identity']
            or _identity(Path(plan['workspace']) / '.git') != plan['workspace_git_identity']):
        raise WorkspaceChanged('Private workspace identity changed; inspect the saved task copy before continuing.')
    if _tip(source, plan['ownership_ref']) != plan.get('ownership_oid') or not plan.get('ownership_oid'):
        raise ValueError('Run branch ownership marker changed or is missing')
    expected = expected_tip or plan.get('feature_tip', plan['base_sha'])
    if _tip(source, plan['feature_ref']) != expected:
        raise ValueError('Feature branch changed outside this run')
    return True


def _snapshot_blobs(plan):
    """Read exact manifest objects in one Git process, including binary blobs."""
    entries = plan['entries']
    if not entries:
        return []
    if len(entries) > MAX_FILES or sum(entry['size'] for entry in entries) > MAX_SNAPSHOT_BYTES:
        raise ValueError('Repository snapshot is too large')
    if any(not re.fullmatch(r'[a-f0-9]{40,64}', entry['oid']) for entry in entries):
        raise ValueError('Invalid snapshot object identity')
    data = source_git(plan['source'], 'cat-file', '--batch',
                      input=''.join(entry['oid'] + '\n' for entry in entries), binary=True)
    blobs, offset = [], 0
    for entry in entries:
        boundary = data.find(b'\n', offset)
        header = data[offset:boundary].split() if boundary >= 0 else []
        expected = [entry['oid'].encode(), b'blob', str(entry['size']).encode()]
        if header != expected:
            raise ValueError('Snapshot object is missing or changed')
        start, end = boundary + 1, boundary + 1 + entry['size']
        if len(data) <= end or data[end:end+1] != b'\n':
            raise ValueError('Snapshot object response was incomplete')
        blobs.append(memoryview(data)[start:end])
        offset = end + 1
    if offset != len(data):
        raise ValueError('Unexpected snapshot object data')
    return blobs


def _verify_snapshot(plan):
    destination = Path(plan['workspace'])
    if (_identity(destination) != plan.get('workspace_identity')
            or _identity(destination / '.git') != plan.get('workspace_git_identity')):
        raise WorkspaceChanged('Private workspace identity changed; inspect the saved task copy before continuing.')
    inspect_source(destination)
    if git(destination, 'rev-parse', 'HEAD').strip() != plan['workspace_head']:
        raise WorkspaceChanged('Private snapshot baseline changed; inspect the saved task copy before continuing.')
    if (git(destination, 'status', '--porcelain', '--untracked-files=all').strip()
            or git(destination, 'ls-files', '--others', '--ignored', '--exclude-standard').strip()):
        raise WorkspaceChanged('Private snapshot is no longer clean; inspect its changed files before continuing. No files were replaced.')
    workspace = Workspace(destination)
    for entry, blob in zip(plan['entries'], _snapshot_blobs(plan)):
        path = workspace.path(entry['path'])
        if (not path.is_file() or path.read_bytes() != blob
                or bool(path.stat().st_mode & 0o111) != (entry['mode'] == '100755')):
            raise WorkspaceChanged('Private snapshot contents changed; inspect the saved task copy before continuing. No files were replaced.')


def _materialize(plan):
    source = plan['source']
    destination = Path(plan['workspace'])
    # An existing partial copy is retained, never silently overwritten/adopted.
    if destination.exists():
        raise ValueError('Partial workspace exists; inspect the retained creation attempt')
    destination.mkdir(parents=True, mode=0o700)
    for entry in plan['entries']:
        target = destination / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        data = source_git(source, 'cat-file', 'blob', entry['oid'], binary=True)
        if len(data) != entry['size']:
            raise ValueError('Committed blob size changed')
        target.write_bytes(data)
        target.chmod(0o700 if entry['mode'] == '100755' else 0o600)
    git(destination, 'init', '-q')
    # Plumbing avoids applying .gitattributes filters and preserves exact bytes.
    for entry in plan['entries']:
        oid = source_git(destination, 'hash-object', '-w', '--stdin', input=(destination / entry['path']).read_bytes())
        git(destination, 'update-index', '--add', '--cacheinfo', entry['mode'], oid, entry['path'])
    git(destination, '-c', 'user.name=cheapoS', '-c', 'user.email=local@cheapos.invalid', 'commit', '-qm', 'Committed run baseline')
    plan['workspace_head'] = git(destination, 'rev-parse', 'HEAD').strip()
    plan['workspace_identity'] = _identity(destination)
    plan['workspace_git_identity'] = _identity(destination / '.git')
    plan['snapshot'] = {'source': source, 'files': len(plan['entries']), 'skipped': plan['skipped']}


def materialize(prepared, persist_intent):
    """Prepare only the private copy for scoped permission inspection.

    No source objects/refs, model calls, or check commands are created/executed.
    The saved mapping remains prepared and confers no execution authority.
    """
    plan = copy.deepcopy(prepared)
    if plan['stage'] != 'prepared':
        raise ValueError('Only a prepared proposal can materialize a private copy')
    _revalidate(plan)
    if _tip(plan['source'], plan['base_ref']) != plan['base_sha']:
        raise ValueError('Base changed after proposal')
    entries, skipped = _manifest(plan['source'], plan['base_sha'])
    if entries != plan['entries'] or skipped != plan['skipped']:
        raise ValueError('Snapshot manifest changed after preparation')
    if plan.get('workspace_identity'):
        _verify_snapshot(plan)
        return plan
    persist_intent(copy.deepcopy(plan))
    _materialize(plan)
    persist_intent(copy.deepcopy(plan))
    return plan


def create(prepared, persist_intent, progress=None):
    plan = copy.deepcopy(prepared)
    if progress: progress('verifying_snapshot')
    _revalidate(plan)
    source = plan['source']
    if plan.get('workspace_identity') and plan['stage'] != 'ready':
        _verify_snapshot(plan)
    if progress: progress('preparing_branch')
    if plan['stage'] == 'prepared':
        entries, skipped = _manifest(source, plan['base_sha'])
        if entries != plan['entries'] or skipped != plan['skipped']:
            raise ValueError('Snapshot manifest changed after preparation')
        validate_base(plan)
        if _tip(source, plan['feature_ref']) or _tip(source, plan['ownership_ref']):
            raise WorkspaceChanged('Feature branch or ownership marker already exists; inspect branch ownership before continuing.')
        ownership = json.dumps({k: plan[k] for k in ('run_id', 'source_identity', 'common_identity', 'feature_ref', 'base_sha')}, sort_keys=True)
        plan['ownership_oid'] = source_git(source, 'hash-object', '-w', '--stdin', input=ownership)
        plan['stage'] = 'creating'
        persist_intent(copy.deepcopy(plan))
    if plan['stage'] == 'creating':
        feature, marker = _tip(source, plan['feature_ref']), _tip(source, plan['ownership_ref'])
        if feature is None and marker is None:
            validate_base(plan)
            transaction = ('start\noption no-deref\ncreate ' + plan['feature_ref'] + ' ' + plan['base_sha'] + '\ncreate '
                           + plan['ownership_ref'] + ' ' + plan['ownership_oid'] + '\nprepare\ncommit\n')
            source_git(source, 'update-ref', '--stdin', input=transaction)
        validate_owned(plan, plan['base_sha'])
        plan['stage'] = 'branch_created'
        persist_intent(copy.deepcopy(plan))
    if plan['stage'] == 'branch_created':
        validate_owned(plan, plan['base_sha'])
        if plan.get('workspace_identity'):
            _verify_snapshot(plan)
        else:
            _materialize(plan)
        plan['feature_tip'] = plan['base_sha']
        plan['stage'] = 'ready'
        persist_intent(copy.deepcopy(plan))
    validate_owned(plan)
    return plan
