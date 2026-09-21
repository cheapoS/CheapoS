"""Controller-owned fetch and fast-forward for the captured PR workflow.

Never reset, stash, rebase, create merge commits or switch the operator's branch.
Active task copies keep their original base and verification evidence.
"""
import subprocess
import uuid

from . import branch_workspace as work, branch_merge, github
from .branch_commits import repository_lock


def synchronize(source, remote, ref=None, *, expected_destination=None, merged_commit=None):
    result = {'remote': remote, 'state': 'unavailable', 'retryable': True,
              'message': 'Remote sync is unavailable. Local work is preserved; new work uses the current local branch.'}
    temporary = None
    tip = None
    try:
        mapping = work.inspect_source(source)
        source = mapping['source']
        with repository_lock(mapping):
            destination = github.destination(source, remote)
            if expected_destination and destination != expected_destination:
                return {**result, 'state': 'destination_changed', 'retryable': False,
                        'message': 'The Git remote changed. Local branches were not updated from a different repository.'}
            ref = ref or work.source_git(source, 'symbolic-ref', '--quiet', 'HEAD')
            work._local_ref(source, ref)
            old = work._tip(source, ref)
            if not old:
                raise ValueError('Local branch is missing')
            result['branch'] = ref.removeprefix('refs/heads/')
            # Fetch only the selected branch from the same repository used for PRs.
            # No FETCH_HEAD, tags, source index or active task workspace is changed.
            temporary = 'refs/cheapos/sync/' + uuid.uuid4().hex
            work.source_git(source, '-c', 'maintenance.auto=false', 'fetch', '--no-tags',
                            '--no-recurse-submodules', '--no-write-fetch-head', '--',
                            destination[1], ref + ':' + temporary)
            tip = work._tip(source, temporary)
            if not tip:
                raise ValueError('Remote branch is missing')
            if merged_commit and work.source_git(source, 'merge-base', merged_commit, tip,
                                                allowed_returncodes=(0, 1)) != merged_commit:
                return {**result, 'state': 'merge_not_fetched',
                        'message': 'The remote branch does not yet contain the confirmed PR merge. Local work is preserved; sync will retry.'}
            result.update(local_head=old, remote_head=tip)
            # Keep ordinary git status truthful as well. A split fetch/push
            # remote must not receive tracking data from a different repository.
            try:
                same_fetch_repo = github.destination(source, remote, push=False)[0].lower() == destination[0].lower()
            except ValueError:
                same_fetch_repo = False
            if same_fetch_repo and github.destination(source, remote) == destination:
                tracking = 'refs/remotes/' + remote + '/' + result['branch']
                tracked = work._tip(source, tracking) or ''
                work.source_git(source, 'update-ref', '-m', 'cheapoS: fetch remote branch', tracking, tip, tracked)
            if tip == old:
                return {**result, 'state': 'current', 'retryable': False,
                        'message': 'Local ' + result['branch'] + ' is up to date with ' + remote + '.'}
            ancestor = work.source_git(source, 'merge-base', old, tip, allowed_returncodes=(0, 1))
            if ancestor == tip:
                return {**result, 'state': 'ahead', 'retryable': False,
                        'message': 'Local ' + result['branch'] + ' already includes the remote changes and has additional local commits.'}
            if ancestor != old:
                return {**result, 'state': 'diverged', 'retryable': True,
                        'message': 'Local and remote ' + result['branch'] + ' have different commits. Both histories are preserved; new work uses the local branch until they are reconciled.'}
            checkout = branch_merge._destination(mapping, ref)
            identity = branch_merge.destination_identity(mapping, checkout)
            if checkout:
                branch_merge._check_destination(checkout, ref, old, tip)
            if (work.inspect_source(source) != mapping or work._tip(source, ref) != old
                    or branch_merge._destination(mapping, ref) != checkout
                    or branch_merge.destination_identity(mapping, checkout) != identity
                    or github.destination(source, remote) != destination):
                raise ValueError('Destination changed during sync')
            if checkout:
                # Git repeats dirty/index checks atomically with its fast-forward;
                # ignored files and unrelated staged/unstaged drafts are protected.
                branch_merge._check_destination(checkout, ref, old, tip)
                work.source_git(checkout, '-c', 'merge.autostash=false', '-c', 'submodule.recurse=false',
                                'merge', '--ff-only', '--no-edit', '--no-stat', '--no-overwrite-ignore', tip)
            else:
                work.source_git(source, 'update-ref', '-m', 'cheapoS: sync merged remote work', ref, tip, old)
            return {**result, 'state': 'updated', 'retryable': False, 'local_head': tip,
                    'message': 'Updated local ' + result['branch'] + ' from ' + remote + '. New tasks will include these commits.'}
    except (ValueError, OSError, subprocess.SubprocessError):
        # Do not expose remote stderr (URLs/credentials) or turn an optional sync
        # into a provider/task failure. Retrying after a lost response is idempotent.
        if tip:
            result.update(state='deferred', message='Local branch sync is pending: the checkout changed, has overlapping drafts, or has a Git operation in progress. Saved work is intact; new work uses the current local branch.')
        return result
    finally:
        if temporary:
            try:
                work.source_git(source, 'update-ref', '-d', temporary, *([tip] if tip else []))
            except (ValueError, OSError, subprocess.SubprocessError):
                pass


def before_task(source, snapshot, ref=None):
    """Only a captured PR-mode policy authorizes automatic remote reads/sync."""
    from .git_workflow import enabled, policy
    task = {'settings_snapshot': snapshot or {}}
    if not enabled(task):
        return None
    return synchronize(source, policy(task)['remote'], ref)


def project_sync(engine, values):
    """Explicit project refresh uses saved settings, never caller-supplied Git refs."""
    if set(values) != {'repository'} or not isinstance(values['repository'], str) or not values['repository'].strip():
        raise ValueError('Choose a registered project to sync')
    source = engine.settings_project(values['repository'])
    with engine.admission.repository(source):
        result = before_task(source, engine.settings_store.view(source))
    if result is None:
        return {'state': 'disabled', 'retryable': False,
                'message': 'This project uses local merges. Choose the GitHub pull request workflow in Project settings → Git to enable remote sync.'}
    return result
