"""Task-scoped shipping policy and explicitly approved GitHub publication.

Publishing never writes the destination index/checkout or merges a PR. The
saved intent binds the inspected commit and repository, and is recoverable after
a lost push/create response. Models cannot invoke this module as a tool.
"""
import copy
import hashlib
import re
import tempfile
import time
import uuid
from pathlib import Path

from . import github, commits, branch_final, branch_workspace as work
from .branch_authorization import digest


def validate_settings(value):
    if value.get('workflow', 'local') not in {'local', 'pull_request'}:
        raise ValueError('Choose Local merge or GitHub pull request')
    remote = value.get('remote', 'origin')
    if not isinstance(remote, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', remote):
        raise ValueError('Use a Git remote name such as origin')


def policy(task):
    value = task.get('settings_snapshot', {}).get('values', {}).get('git', {})
    validate_settings(value)
    return {'workflow': value.get('workflow', 'local'), 'remote': value.get('remote', 'origin')}


def enabled(task):
    return policy(task)['workflow'] == 'pull_request'


def _baseline_entries(source, ref):
    entries = work.source_git(source, 'ls-tree', '-rz', ref, binary=True)
    return {entry.split(b'\t', 1)[1].decode('utf-8'): entry.split(b'\t', 1)[0]
            for entry in entries.split(b'\0') if entry}


def _candidate(engine, task):
    """Use existing exact checks and independent review for either work mode."""
    if not enabled(task):
        raise ValueError('This chat uses the local Git workflow')
    if task.get('demo'):
        raise ValueError('Scripted demo work cannot be published')
    run = task.get('branch_run')
    if run:
        engine.branch.validate_authority(task, run)
        branch_final.validate(run.get('readiness') or {}, task)
        manifest = run['readiness']['manifest']
        return {'source': run['workspace_mapping']['source'], 'base': run['target_ref'].removeprefix('refs/heads/'),
                'head': run['expected_feature_tip'], 'tree': manifest['feature_tree'],
                'evidence': run['readiness']['id'], 'patch': manifest['diff'], 'files': [f['path'] for f in manifest['files']]}
    engine.reviewed_patch(task)
    # Takeover can use human review for a local commit. PR mode promises an
    # independent review, so it must be present for the exact patch as well.
    from .engine import current_evidence
    review = (task.get('checkpoints') or [{}])[-1]
    if review.get('decision') != 'APPROVE' or review.get('diff') != task['patch'] or not current_evidence(task, review):
        raise ValueError('Finish independent review before publishing this patch')
    source = task['source']; state = commits.source_state(source)
    target = task.get('git_target') or state
    if state['branch'] != target['branch'] or state['head'] != target['head']:
        raise ValueError('The project branch changed since this chat started. Reconcile and review the updated task before publishing.')
    # Interactive snapshots can include pre-existing, uncommitted source work.
    # Do not publish a different baseline than the one checks/review examined.
    baseline = _baseline_entries(task['workspace'], 'HEAD')
    skipped = set(task.get('snapshot', {}).get('skipped', []))
    expected = {path: entry for path, entry in _baseline_entries(source, state['head']).items() if path not in skipped}
    if baseline != expected:
        raise ValueError('The task baseline includes uncommitted project changes. Reconcile with the committed project and review before publishing.')
    with tempfile.TemporaryDirectory(prefix='cheapos-pr-index-') as tmp:
        index = Path(tmp) / 'index'
        work.source_git(source, 'read-tree', state['head'], index=index)
        work.source_git(source, 'apply', '--cached', '--whitespace=nowarn', '-', input=task['patch'], index=index)
        tree = work.source_git(source, 'write-tree', index=index)
    return {'source': source, 'base': state['branch'].removeprefix('refs/heads/'), 'parent': state['head'], 'tree': tree,
            'evidence': digest({'patch': task['patch'], 'review': review, 'check': task['checks'][-1]}),
            'patch': task['patch'], 'files': [f['path'] for f in task['changes']]}


def preview(engine, task_id):
    with engine.lock:
        engine.require_active_task(task_id)
        engine.admission.require_idle(task_id)
        task = engine.store.get(task_id)
        saved = task.get('pull_request')
        if saved and not saved.get('url'):
            return {**copy.deepcopy(saved), 'retry': not saved.get('url')}
        if saved and saved.get('ci', {}).get('state') in {'merged','closed'}:
            return copy.deepcopy(saved)
        try:
            candidate = _candidate(engine, task)
        except (ValueError, OSError) as error:
            if saved and saved.get('url'):
                return {**copy.deepcopy(saved), 'update_blocker': str(error)}
            raise
        if saved and candidate['tree'] == saved['tree'] and candidate['evidence'] == saved['evidence']:
            return copy.deepcopy(saved)
        if saved and saved.get('ci', {}).get('state') in {'merged','closed','changed'}:
            raise ValueError('This PR was closed or changed outside cheapoS. Start a new task from the updated project for further work.')
        repo, push_url = github.destination(candidate['source'], policy(task)['remote'])
        head_branch = 'cheapos/task-' + hashlib.sha256(task_id.encode()).hexdigest()[:24]
        message = re.sub(r'\s+', ' ', task.get('title') or 'cheapoS changes')[:200]
        operation = {**candidate, 'repo': repo, 'branch': head_branch, 'message': message,
                     'remote': policy(task)['remote'], 'push_url': push_url, 'id': uuid.uuid4().hex, 'created': time.time()}
        if saved:
            if any(saved[k] != operation[k] for k in ('repo','push_url','branch','base')):
                raise ValueError('A pull request update must keep its approved repository and branches')
            operation.update(expected_remote=saved['head'], previous_id=saved['id'], update=True)
        if not hasattr(engine, 'pull_request_previews'):
            engine.pull_request_previews = {}
        engine.pull_request_previews[task_id] = operation
        return copy.deepcopy(operation)


def publish(engine, task_id, values):
    if set(values) != {'approved', 'id'} or values['approved'] is not True:
        raise ValueError('Approve the displayed branch and GitHub destination before publishing')
    source = engine.store.get(task_id)['source']
    with engine.admission.integration(task_id, source):
        engine.require_active_task(task_id)
        task = engine.store.get(task_id)
        if not enabled(task):
            raise ValueError('This chat uses the local Git workflow')
        saved = task.get('pull_request')
        pending = getattr(engine, 'pull_request_previews', {}).get(task_id)
        updating = bool(saved and pending and pending.get('previous_id') == saved['id'] and pending['id'] == values['id'])
        if saved and not updating:
            if saved['id'] != values['id']:
                raise ValueError('This approval belongs to a different pull request')
            operation = copy.deepcopy(saved)
        else:
            operation = copy.deepcopy(getattr(engine, 'pull_request_previews', {}).get(task_id))
            if not operation or operation['id'] != values['id'] or time.time() - operation['created'] > 600:
                raise ValueError('Refresh the pull request preview before approving it')
            current = _candidate(engine, task)
            if any(operation.get(k) != v for k, v in current.items()):
                raise ValueError('The reviewed work changed. Refresh the pull request preview')
            if github.destination(source, operation['remote']) != (operation['repo'], operation['push_url']):
                raise ValueError('The Git remote changed after preview')
            if not operation.get('head'):
                operation['head'] = commits.commit_object({'source': source, 'tree': operation['tree'], 'head': operation.get('expected_remote') or operation['parent'],
                    'git_settings': task.get('settings_snapshot', {}).get('values', {}).get('git')}, operation['message'])
            # Retain the reviewed object locally through interrupted publication.
            work.source_git(source, 'update-ref', 'refs/cheapos/pull-requests/' + operation['id'], operation['head'], '')
            operation['state'] = 'publishing'
            if saved:
                task.setdefault('pull_request_history', []).append(copy.deepcopy(saved))
            task['pull_request'] = copy.deepcopy(operation)
            engine.store.save(task)  # Durable intent before the first remote write.
        if operation.get('url'):
            return operation
        if github.destination(source, operation['remote']) != (operation['repo'], operation['push_url']):
            raise ValueError('The saved publication destination changed; no push was made')
        # Probe authentication before push. A read-only lookup also recovers a
        # successful PR creation whose response was lost before persistence.
        pull = github.find_pull(operation['repo'], operation['branch'], operation['base'])
        if pull and (pull.get('state') == 'closed' or pull.get('merged_at')):
            raise ValueError('The pull request is closed. Saved changes will not reopen or overwrite it.')
        destination = operation['push_url']
        ref = 'refs/heads/' + operation['branch']
        remote = work.source_git(source, 'ls-remote', '--refs', destination, ref)
        remote_head = remote.split()[0] if remote else ''
        expected = operation.get('expected_remote', '')
        if remote_head not in {expected, operation['head']}:
            raise ValueError('The remote task branch changed. It will not be overwritten.')
        if remote_head != operation['head']:
            if expected:
                work.source_git(source, 'merge-base', '--is-ancestor', expected, operation['head'])
            # Empty lease creates only while absent. Updates require both
            # ancestry above and an unchanged known head: never discard commits.
            work.source_git(source, 'push', '--porcelain', '--force-with-lease=' + ref + ':' + expected, destination, operation['head'] + ':' + ref)
        if pull is None:
            pull = github.api(operation['repo'], 'pulls', {
                'title': operation['message'], 'head': operation['branch'], 'base': operation['base'],
                'body': '## Changes\n\n' + operation['message'] + '\n\n## Validation\n\n'
                        'Local checks and independent cheapoS review passed for commit `' + operation['head'] + '`.\n'
                        'Review the diff and GitHub CI results before merging.\n\n'
                        'Created by cheapoS; local destination branch was not modified.'})
        elif pull.get('head', {}).get('sha') != operation['head']:
            pull = github.api(operation['repo'], 'pulls/' + str(int(pull['number'])))
        if pull.get('head', {}).get('sha') != operation['head'] or pull.get('base', {}).get('ref') != operation['base']:
            raise ValueError('GitHub returned a different pull request candidate; inspect the saved branch')
        operation.update(number=pull['number'], url=f"https://github.com/{operation['repo']}/pull/{int(pull['number'])}", state='open')
        task['pull_request'] = operation
        engine.event(task, 'pull_request', 'Pull request updated. GitHub checks and your merge decision come next.' if operation.get('update') else 'Pull request opened. GitHub checks and your merge decision come next.',
                     {'url': operation['url'], 'head': operation['head']})
        engine.store.save(task)
        return operation


def status(engine, task_id):
    engine.require_active_task(task_id)
    task = engine.store.get(task_id)
    operation = task.get('pull_request')
    if not operation or not operation.get('number'):
        raise ValueError('Publish this task’s pull request first')
    result = {**operation, 'ci': github.checks(operation['repo'], operation['number'], operation['head'])}
    # Establish completion against the saved candidate before local sync can
    # advance its source branch. A remote merge never renews execution authority.
    sync = False
    with engine.lock:
        current = engine.store.get(task_id)
        if current.get('pull_request', {}).get('id') == operation['id']:
            before = copy.deepcopy(current)
            current['pull_request'] = copy.deepcopy(result)
            runtime = getattr(engine, 'runtimes', {}).get(task_id)
            busy = bool(runtime and runtime.thread and runtime.thread.is_alive())
            try:
                same = result['ci']['state'] == 'merged' and not busy and _candidate(engine, current)['evidence'] == operation['evidence']
            except (ValueError, OSError):
                same = False
            if result['ci']['state'] == 'merged' and same:
                # GitHub confirms the exact published head was merged. This is
                # a remote receipt, not evidence of a local checkout mutation.
                current.update(status='completed', error=None)
                result['merged_head'] = operation['head']
                current['pull_request']['merged_head'] = operation['head']
                run = current.get('branch_run')
                if run and run.get('expected_feature_tip') == operation['head']:
                    run.update(status='merged', pause_reason=None, merge_receipt={
                        'id': operation['id'], 'kind': 'github', 'feature_tip': operation['head'],
                        'target_ref': run['target_ref'], 'merge_commit': result['ci']['merged_commit'], 'url': operation['url']})
            if current != before:
                engine.store.save(current)
            sync = (result['ci']['state'] == 'merged' and not busy
                    and current['pull_request'].get('merged_head') == operation['head'])
    if sync:
        # Network/Git I/O happens outside the global engine lock. A pending
        # checkout sync must not turn an already merged task into a failed task.
        from .git_sync import synchronize
        try:
            with engine.admission.integration(task_id, operation['source']):
                local = synchronize(operation['source'], operation['remote'], 'refs/heads/' + operation['base'],
                    expected_destination=(operation['repo'], operation['push_url']),
                    merged_commit=result['ci'].get('merged_commit'))
                with engine.lock:
                    current = engine.store.get(task_id)
                    if current.get('pull_request', {}).get('id') == operation['id']:
                        previous = current['pull_request'].get('local_sync')
                        current['pull_request']['local_sync'] = copy.deepcopy(local)
                        if local != previous:
                            engine.event(current, 'git_sync', local['message'], local)
                        engine.store.save(current)
                result['local_sync'] = local
        except ValueError:
            result['local_sync'] = {'state': 'deferred', 'retryable': True,
                'message': 'The PR is merged. Local sync will retry after the current repository operation finishes.'}
    return result
