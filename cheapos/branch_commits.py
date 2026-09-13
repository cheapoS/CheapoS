"""Journaled controller-only commits. Caller freezes worker writes under its lock.

persist(operation) must durably save a COPY before returning. Save the returned
operation as history and publish its milestone keyed by operation ID. This module
never records operator acceptance. Hooks/signing remain disabled under the existing
manual commit policy; source filters/sparse repositories are refused by T29.
"""
import copy
import tempfile
import threading
import unicodedata
import uuid
from pathlib import Path
from . import branch_evidence as evidence
from . import branch_workspace as workspace
from .workspace import Workspace, git

_LOCKS = {}
_LOCK_GUARD = threading.Lock()


def repository_lock(mapping):
    """Shared by feature commits and integration, including linked source paths."""
    key = tuple(mapping['common_identity'])
    with _LOCK_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def context(run, item):
    return {'run_id': run['id'], 'plan_revision': run['plan_revision'],
            'plan_digest': run['plan_digest'], 'item_id': item['id'],
            'item_revision': item.get('revision', 1), 'feature_parent': run['expected_feature_tip']}


def _validate(task, run, item, parent, recorded_parent=None):
    mapping = run['workspace_mapping']
    if mapping['run_id'] != run['id'] or str(Path(task['workspace']).resolve()) != mapping['workspace'] or workspace._identity(mapping['workspace']) != mapping['workspace_identity']:
        raise ValueError('Registered workspace identity changed')
    if run.get('current_item_id') != item['id'] or run['expected_feature_tip'] != (recorded_parent or parent):
        raise ValueError('Commit no longer belongs to the active run item')
    planned = next((value for value in run.get('plan', {}).get('items', []) if value.get('id') == item['id']), None)
    fields = ('id', 'title', 'instructions', 'dependencies', 'acceptance_criteria', 'required_checks', 'revision_of')
    if planned is None or any(planned.get(key) != item.get(key) for key in fields):
        raise ValueError('Active item changed from the captured plan')
    workspace.validate_owned(mapping, parent)
    return mapping


def _message(item):
    title = item.get('title')
    if not isinstance(title, str) or not title.strip() or len(title) > 120 or any(unicodedata.category(c).startswith('C') for c in title):
        raise ValueError('Commit title must be bounded plain text without controls')
    return 'Complete ' + title.strip()


def _preserve_exclusions(source, parent, tree, mapping):
    changed = workspace.source_git(source, 'diff-tree', '--no-commit-id', '--name-only', '-r', '-z', parent, tree, binary=True).split(b'\0')
    excluded = [unicodedata.normalize('NFC', name).casefold() for name in mapping['skipped']]
    for raw in changed:
        if not raw:
            continue
        name = unicodedata.normalize('NFC', raw.decode()).casefold()
        if any(name == other or name.startswith(other + '/') or other.startswith(name + '/') for other in excluded):
            raise ValueError('Candidate overlaps an excluded source entry')


def prepare(task, run, item, receipt, authorize):
    """Create immutable commit objects only; no ref moves until intent is saved."""
    mapping = run['workspace_mapping']
    with repository_lock(mapping):
        authorize(task, run)
        parent = run['expected_feature_tip']
        _validate(task, run, item, parent)
        checked = evidence.revalidate(receipt, task, context(run, item), item['required_checks'], item['acceptance_criteria'])
        candidate = checked['candidate']
        if candidate['private_baseline'] != mapping['workspace_head']:
            raise ValueError('Private baseline mapping changed')
        operation = {'id': uuid.uuid4().hex, 'run_id': run['id'], 'item_id': item['id'],
                     'context': context(run, item), 'receipt': receipt, 'candidate_id': candidate['id'],
                     'old_tip': parent, 'private_old': candidate['private_baseline'],
                     'mapping': copy.deepcopy(mapping), 'stage': 'prepared',
                     'outcome': checked['outcome'], 'message': _message(item)}
        if checked['outcome'] == 'satisfied_without_change':
            operation.update(new_tip=parent, private_new=candidate['private_baseline'], tree=workspace.source_git(mapping['source'], 'rev-parse', parent + '^{tree}'), private_tree=git(task['workspace'], 'write-tree').strip())
            return operation
        source = mapping['source']
        workspace.source_git(source, 'var', 'GIT_AUTHOR_IDENT')
        workspace.source_git(source, 'var', 'GIT_COMMITTER_IDENT')
        with tempfile.TemporaryDirectory(prefix='cheapos-branch-commit-') as temp:
            index = Path(temp) / 'index'
            workspace.source_git(source, 'read-tree', parent, index=index)
            workspace.source_git(source, 'apply', '--cached', '--whitespace=nowarn', '-', input=candidate['patch'], index=index)
            tree = workspace.source_git(source, 'write-tree', index=index)
        _preserve_exclusions(source, parent, tree, mapping)
        if tree == workspace.source_git(source, 'rev-parse', parent + '^{tree}'):
            raise ValueError('Changed candidate did not produce a source change')
        operation['tree'] = tree
        operation['new_tip'] = workspace.source_git(source, 'commit-tree', tree, '-p', parent, input=operation['message'] + '\n')
        operation['private_tree'] = git(task['workspace'], 'write-tree').strip()
        operation['private_new'] = git(task['workspace'], '-c', 'user.name=cheapoS', '-c', 'user.email=local@cheapos.invalid', 'commit-tree', operation['private_tree'], '-p', operation['private_old'], '-m', operation['message']).strip()
        return operation


def _save(operation, stage, persist):
    operation['stage'] = stage
    persist(copy.deepcopy(operation))


def _contents(task, operation):
    # Stage eligible files before comparing; never reset/discard worker content.
    Workspace(task['workspace']).patch()
    if git(task['workspace'], 'write-tree').strip() != operation['private_tree']:
        raise ValueError('Private candidate changed during the recorded commit')
    current = git(task['workspace'], 'rev-parse', 'HEAD').strip()
    if current not in {operation['private_old'], operation['private_new']}:
        raise ValueError('Private baseline changed during the recorded commit')
    return current


def finish(task, run, item, operation, persist, authorize):
    """Recover only this exact transaction, even after ref movement/save failure."""
    operation = copy.deepcopy(operation)
    mapping = operation['mapping']
    with repository_lock(mapping):
        if operation['run_id'] != run['id'] or operation['item_id'] != item['id'] or operation['context'] != context(run, item) or mapping != run['workspace_mapping']:
            raise ValueError('Recorded operation no longer matches the run contract')
        source = mapping['source']
        actual = workspace._tip(source, mapping['feature_ref'])
        if actual not in {operation['old_tip'], operation['new_tip']}:
            raise ValueError('Feature branch changed outside the recorded operation')
        _validate(task, run, item, actual, operation['old_tip'])
        _contents(task, operation)
        if actual == operation['old_tip']:
            authorize(task, run)
            evidence.revalidate(operation['receipt'], task, context(run, item), item['required_checks'], item['acceptance_criteria'])
            # This durable write is REQUIRED before the irreversible ref update.
            _save(operation, 'intent', persist)
            _validate(task, run, item, operation['old_tip'])
            _contents(task, operation)
            authorize(task, run)
            evidence.revalidate(operation['receipt'], task, context(run, item), item['required_checks'], item['acceptance_criteria'])
            if operation['outcome'] != 'satisfied_without_change':
                transaction = ('start\noption no-deref\nverify ' + mapping['ownership_ref'] + ' ' + mapping['ownership_oid'] + '\nupdate ' + mapping['feature_ref'] + ' ' + operation['new_tip'] + ' ' + operation['old_tip'] + '\nprepare\ncommit\n')
                workspace.source_git(source, 'update-ref', '-m', 'cheapoS: ' + operation['message'], '--stdin', input=transaction)
        _save(operation, 'source_committed', persist)
        current = _contents(task, operation)
        if current != operation['private_new']:
            git(task['workspace'], 'update-ref', 'HEAD', operation['private_new'], operation['private_old'])
        _save(operation, 'private_advanced', persist)
        # Caller advances mapping + item outcome and publishes one event in the
        # same durable task write, using this operation ID as the deduplication key.
        _save(operation, 'completed', persist)
        return operation
