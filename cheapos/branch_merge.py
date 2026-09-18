"""Explicitly approved local fast-forward integration, never a model tool.

Caller binds readiness/preview/operator approval in validate_approval(operation)
and durably saves every operation received by persist. External Git processes do
not share our lock: drift checks refuse recovery instead of resetting their work.
Hooks, signing, editors and automatic stashing are disabled under existing policy.
"""
import copy
import hashlib
import uuid
from pathlib import Path
from . import branch_workspace as workspace
from .branch_commits import repository_lock


def _manifest(source, old, new):
    return hashlib.sha256(workspace.source_git(source, 'diff-tree', '-r', '--raw', '--no-abbrev',
                         '--no-renames', '-z', old, new, binary=True)).hexdigest()


def _destination(mapping, target):
    source = mapping['source']
    records = workspace.source_git(source, 'worktree', 'list', '--porcelain', '-z', binary=True).split(b'\0')
    selected, found = None, None
    for record in records:
        if record.startswith(b'worktree '):
            selected = str(Path(record[9:].decode()).resolve())
        elif record == ('branch ' + target).encode():
            if not selected or found is not None:
                raise ValueError('Target is checked out in multiple worktrees; choose one destination before integration')
            found = selected
    return found


def destination_identity(mapping, destination):
    """Bind the registered checkout to this repository, including its Git directory."""
    if destination is None:
        return None
    identity = workspace.inspect_source(destination)
    if identity['source'] != destination or identity['common_identity'] != mapping['common_identity']:
        raise ValueError('Target worktree no longer belongs to the selected repository')
    identity['git_identity'] = workspace._identity(
        workspace.source_git(destination, 'rev-parse', '--absolute-git-dir'))
    return identity


def _clean(source, target):
    if workspace.source_git(source, 'symbolic-ref', '--quiet', 'HEAD') != target:
        raise ValueError('Destination checkout branch changed')
    markers = ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply', 'sequencer')
    args = [arg for marker in markers for arg in ('--git-path', marker)]
    for raw in workspace.source_git(source, 'rev-parse', *args).splitlines():
        path = Path(raw)
        if (path if path.is_absolute() else Path(source) / path).exists():
            raise ValueError('Finish the existing Git operation before integration')
    if workspace.source_git(source, 'status', '--porcelain=v1', '--untracked-files=all', '--ignore-submodules=none'):
        raise ValueError('Target checkout has uncommitted changes; saved feature branch is intact')


def _validate(operation, recovering=False):
    mapping = operation['mapping']
    source = mapping['source']
    workspace.validate_owned(mapping, operation['feature_tip'])
    workspace._local_ref(source, operation['target_ref'])
    actual = workspace._tip(source, operation['target_ref'])
    allowed = {operation['target_old'], operation['feature_tip']} if recovering else {operation['target_old']}
    if actual not in allowed:
        raise ValueError('Target changed after the approved preview')
    destination = _destination(mapping, operation['target_ref'])
    if destination != operation['destination']:
        raise ValueError('Target worktree destination changed after preview')
    identity = destination_identity(mapping, destination)
    if 'destination_identity' in operation:
        if identity != operation['destination_identity']:
            raise ValueError('Target worktree identity changed after preview')
    elif destination not in (None, source):
        # Older operations only authorized the selected source checkout.
        raise ValueError('Inspect a fresh preview before integrating into another worktree')
    if workspace.source_git(source, 'rev-parse', operation['feature_tip'] + '^{tree}') != operation['tree']:
        raise ValueError('Feature tree changed')
    if (_manifest(source, operation['target_old'], operation['feature_tip']) != operation['manifest_digest']
            or _manifest(source, mapping['base_sha'], operation['feature_tip']) != operation['cumulative_manifest_digest']):
        raise ValueError('Approved change manifest changed')
    if destination:
        _clean(destination, operation['target_ref'])
        if actual == operation['feature_tip']:
            workspace.source_git(destination, 'diff-index', '--cached', '--quiet', operation['feature_tip'], '--')
    return actual


def prepare(mapping, expected_tip, target_ref):
    """Read-only inspection; caller attaches its final readiness approval token."""
    mapping = copy.deepcopy(mapping)
    with repository_lock(mapping):
        workspace.validate_owned(mapping, expected_tip)
        source = mapping['source']
        workspace._local_ref(source, target_ref)
        if target_ref != mapping['target_ref'] or target_ref == mapping['feature_ref']:
            raise ValueError('Integration target differs from the run target')
        old = workspace._tip(source, target_ref)
        if not old:
            raise ValueError('Integration target does not exist')
        try:
            workspace.source_git(source, 'merge-base', '--is-ancestor', old, expected_tip)
        except ValueError:
            raise ValueError('Target diverged; only fast-forward integration is supported') from None
        operation = {'id': uuid.uuid4().hex, 'mapping': mapping, 'feature_tip': expected_tip,
                     'target_ref': target_ref, 'target_old': old,
                     'tree': workspace.source_git(source, 'rev-parse', expected_tip + '^{tree}'),
                     'manifest_digest': _manifest(source, old, expected_tip),
                     'cumulative_manifest_digest': _manifest(source, mapping['base_sha'], expected_tip),
                     'destination': _destination(mapping, target_ref), 'stage': 'prepared'}
        operation['destination_identity'] = destination_identity(mapping, operation['destination'])
        _validate(operation)
        return operation


def _save(operation, stage, persist):
    operation['stage'] = stage
    persist(copy.deepcopy(operation))


def integrate(operation, persist, validate_approval, *, progress=None):
    """Apply/recover exactly the journaled fast-forward, preserving all commits."""
    operation = copy.deepcopy(operation)
    mapping = operation['mapping']
    with repository_lock(mapping):
        if operation['stage'] not in {'prepared', 'intent', 'target_integrated', 'completed'}:
            raise ValueError('Unknown integration operation stage')
        current = _validate(operation, recovering=operation['stage'] != 'prepared')
        validate_approval(copy.deepcopy(operation))
        if operation['stage'] == 'prepared':
            _save(operation, 'intent', persist)
        if current != operation['feature_tip']:
            if progress: progress('integrating')
            # Recheck after durable save, immediately before the Git mutation.
            _validate(operation)
            validate_approval(copy.deepcopy(operation))
            source = mapping['source']
            if operation['destination']:
                destination = operation['destination']
                workspace.source_git(destination, '-c', 'merge.autoStash=false', '-c', 'core.editor=true',
                                     'merge', '--ff-only', '--no-edit', '--no-stat', operation['feature_tip'])
                if workspace.source_git(destination, 'rev-parse', 'ORIG_HEAD') != operation['target_old']:
                    raise ValueError('Target moved during integration; inspect the retained operation')
            else:
                transaction = ('start\noption no-deref\nverify ' + mapping['ownership_ref'] + ' ' + mapping['ownership_oid']
                               + '\nverify ' + mapping['feature_ref'] + ' ' + operation['feature_tip']
                               + '\nupdate ' + operation['target_ref'] + ' ' + operation['feature_tip'] + ' ' + operation['target_old']
                               + '\nprepare\ncommit\n')
                workspace.source_git(source, 'update-ref', '--stdin', input=transaction)
        if progress: progress('confirming')
        if _validate(operation, recovering=True) != operation['feature_tip']:
            raise ValueError('Integration did not reach the approved target; inspect the retained operation')
        _save(operation, 'target_integrated', persist)
        _save(operation, 'completed', persist)
        return operation
