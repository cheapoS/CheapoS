"""GitHub transport using the operator's existing CLI login, without a shell."""
import json
import os
import re
import subprocess
from urllib.parse import urlencode, quote

from .branch_workspace import source_git


def destination(source, remote, *, push=True):
    urls = source_git(source, 'remote', 'get-url', *(['--push'] if push else []), '--all', remote).splitlines()
    if len(urls) != 1:
        raise ValueError('Choose a Git remote with one GitHub push destination')
    match = re.fullmatch(r'(?:git@github\.com:|https://github\.com/|ssh://git@github\.com/)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?', urls[0])
    if not match:
        raise ValueError('Pull request workflow needs a github.com SSH or HTTPS remote without embedded credentials')
    repo = match[1]
    return repo, ('https://github.com/' + repo + '.git' if urls[0].startswith('https://') else 'git@github.com:' + repo + '.git')


def repository(source, remote):
    return destination(source, remote)[0]


def api(repo, endpoint, data=None):
    env = {**os.environ, 'GH_PROMPT_DISABLED': '1', 'GH_PAGER': 'cat', 'GH_HOST': 'github.com'}
    argv = ['gh', 'api', '--hostname', 'github.com', '--method', 'GET' if data is None else 'POST',
            'repos/' + repo + '/' + endpoint]
    if data is not None:
        argv += ['--input', '-']
    try:
        result = subprocess.run(argv, input=None if data is None else json.dumps(data),
                                text=True, capture_output=True, timeout=45, env=env)
    except FileNotFoundError:
        raise ValueError('Install GitHub CLI and sign in with gh auth login to publish pull requests') from None
    except subprocess.TimeoutExpired:
        raise ValueError('GitHub did not respond yet. Your saved publication can be retried safely.') from None
    if result.returncode:
        # CLI stderr can contain repository/configuration details or credentials.
        raise ValueError('GitHub could not complete this request. Check gh auth status for github.com and repository access; saved work is intact.')
    return json.loads(result.stdout)


def find_pull(repo, head, base):
    values = api(repo, 'pulls?' + urlencode({'state': 'all', 'head': repo.split('/')[0] + ':' + head, 'base': base, 'per_page': 100}))
    if not isinstance(values, list):
        raise ValueError('GitHub returned an invalid pull request listing')
    matches = [p for p in values if p.get('head', {}).get('ref') == head and p.get('base', {}).get('ref') == base
               and (p.get('head', {}).get('repo') or {}).get('full_name', '').lower() == repo.lower()]
    if len(matches) > 1:
        raise ValueError('Multiple pull requests reference this task branch; inspect them on GitHub')
    return matches[0] if matches else None


def checks(repo, number, expected_head):
    """Report the current PR head only. Never translate missing checks to success."""
    pull = api(repo, f'pulls/{int(number)}')
    head = pull.get('head', {}).get('sha')
    if head != expected_head:
        return {'state': 'changed', 'message': 'The GitHub branch changed outside this task.', 'head': head}
    branch = api(repo, 'branches/' + quote(pull['base']['ref'], safe=''))
    runs = api(repo, f'commits/{head}/check-runs?per_page=100')
    statuses = api(repo, f'commits/{head}/status?per_page=100')
    rows = [{'name': r['name'], 'state': r.get('conclusion') or r.get('status'), 'url': r.get('html_url')}
            for r in runs.get('check_runs', [])]
    rows += [{'name': r['context'], 'state': r['state'], 'url': r.get('target_url')} for r in statuses.get('statuses', [])]
    if pull.get('merged'):
        state, message = 'merged', 'Merged on GitHub.'
    elif pull.get('state') == 'closed':
        state, message = 'closed', 'Pull request closed on GitHub; saved work is retained.'
    elif not rows:
        state, message = 'pending', 'No CI results reported yet. GitHub controls required checks and merge rules.'
    elif any(r['state'] in {'failure', 'error', 'timed_out', 'action_required', 'cancelled', 'startup_failure'} for r in rows):
        state, message = 'failed', 'GitHub checks need attention. Review the failing check output before merging.'
    elif any(r['state'] not in {'success', 'neutral', 'skipped'} for r in rows) or runs.get('total_count', 0) > len(runs.get('check_runs', [])) or statuses.get('total_count', 0) > len(statuses.get('statuses', [])):
        state, message = 'pending', 'GitHub checks are still pending. Open the PR for complete results.'
    else:
        state, message = 'passed', 'Reported checks passed. GitHub still enforces required reviews and branch rules.'
    return {'state': state, 'message': message, 'head': head, 'checks': rows,
            'protected': branch.get('protected'),
            'mergeable': pull.get('mergeable'), 'mergeable_state': pull.get('mergeable_state'),
            'merged_commit': pull.get('merge_commit_sha') if pull.get('merged') else None}
