"""Observer-only exporter trial. Plan and Start are separate explicit live actions.

Example: python3 -B docs/trials/exporter_live.py plan --root /tmp/exporter-1
  --config-dir /tmp/pinned-profile --live
Then inspect proposal.private.json and use start --reviewed-digest SHA --live.
No automatic corrections, retries, Resume, merge, push, or implementation edits.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

SPEC = 'docs/trials/unattended-run-report.md'
PACK = 'docs/trials/run-report-acceptance'


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def save(path, data):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write('\n')


def fingerprint(repo, names):
    entries = {}
    for name in names:
        path = repo / name
        if not path.exists():
            entries[name] = 'missing'
            continue
        files = sorted(path.rglob('*')) if path.is_dir() else [path]
        for file in files:
            if file.is_file() and '__pycache__' not in file.parts:
                entries[str(file.relative_to(repo))] = hashlib.sha256(file.read_bytes()).hexdigest()
    raw = json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'files': entries}


def runtime_hash(repo):
    return fingerprint(repo, ['cheapos', 'dist', 'scripts'])['sha256']


def accounting(task):
    # Explicit known counters only: never recursively publish arbitrary record keys.
    def counters(value, keys):
        return {k: value[k] for k in keys if isinstance(value.get(k), (int, float))
                and not isinstance(value[k], bool) and math.isfinite(value[k])}
    usage = task.get('usage', {})
    provenance = {}
    for record in task.get('request_metrics', []):
        key = record.get('cost_provenance')
        if key in ('provider_reported', 'estimated', 'uncertain_reservation'):
            provenance[key] = provenance.get(key, 0) + 1
    return {'usage': {**counters(usage, ['cost']), **{role: counters(usage.get(role, {}), ['tokens', 'cost']) for role in ('worker', 'reviewer', 'coordinator')}},
            'retained_cost_provenance_counts': provenance,
            'consumption': counters(task.get('branch_run', {}).get('consumption', {}),
                                   ['requests', 'working_seconds', 'worker_tokens', 'reviewer_tokens', 'output_tokens', 'dollars']),
            'retained_requests': len(task.get('request_metrics', [])),
            'request_history_truncated': bool(task.get('request_metrics_truncated'))}


def expected_checks():
    py = 'python3 -B scripts/dev_tests.py --pattern '
    formatter = py + 'test_run_report.py'
    http = py + 'test_run_report_http.py'
    independent = 'python3 -B scripts/dev_tests.py --directory ' + PACK + ' --pattern '
    f = independent + 'test_formatter_acceptance.py'
    h = independent + 'test_endpoint_acceptance.py'
    ui = ['node --check dist/branch_ui.js', 'node --test tests/test_run_report.js tests/test_branch_ui.js']
    final = [py + 'test_run_report.py --pattern test_run_report_http.py',
             'node --check dist/branch_ui.js', 'node --check dist/app.js',
             'node --test tests/test_branch_ui.js tests/test_conversation.js tests/test_guidance.js tests/test_panels.js tests/test_run_report.js', f, h]
    return [[formatter, f], [formatter, http, h], ui], final


def verify_plan(proposal):
    from cheapos.branch_evidence import commands
    plan = proposal['contract']['plan']
    items = plan['items']
    expected, final = expected_checks()
    if len(items) != 3 or plan.get('measurement') is not True:
        raise ValueError('Require exactly three items in measurement mode')
    for i, item in enumerate(items):
        wanted = [] if i == 0 else [p['id'] for p in items[:i]]
        # Item 3 explicitly depends on both preceding implementation items.
        if item.get('dependencies') != wanted or commands(item.get('required_checks', [])) != [shlex.split(c) for c in expected[i]]:
            raise ValueError('Inspect/correct item dependencies and exact check list before Start')
    if sorted(commands(plan['final_checks'])) != sorted(shlex.split(c) for c in final):
        raise ValueError('Inspect/correct the exact final check list before Start')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['plan', 'start'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--app-repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--config-dir', type=Path)
    parser.add_argument('--access-basis', choices=['operator_authorized_included', 'public_free'], default='operator_authorized_included')
    parser.add_argument('--input', choices=['document', 'prompt', 'combined'], default='document')
    parser.add_argument('--reviewed-digest')
    parser.add_argument('--proposal-file', type=Path, help='Inspected API-corrected proposal; original remains preserved and planning is labeled assisted')
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    if not args.live:
        parser.error('Explicit --live is required; plan permits planning only, start permits execution')
    app = args.app_repo.resolve(strict=True)
    root = args.root.resolve()
    if root == app or app in root.parents:
        parser.error('Keep the trial root outside the app repository')
    sys.path.insert(0, str(app))
    from cheapos.engine import Engine
    from cheapos.branch_authorization import digest
    source = root / 'project'
    if args.phase == 'plan':
        if not args.config_dir:
            parser.error('--config-dir is required for planning')
        # The source must represent committed work; do not snapshot another agent's edits.
        if git(app, 'status', '--porcelain'):
            parser.error('Commit app/source changes before creating the trial')
        root.mkdir(mode=0o700)
        (root / 'state').mkdir(mode=0o700)
        for name in ('config.json', 'preferences.json', 'gateway.json'):
            save(root / 'state' / name, json.loads((args.config_dir / name).read_text()))
        sha = git(app, 'rev-parse', 'HEAD')
        subprocess.run(['git', 'clone', '--quiet', '--no-hardlinks', str(app), str(source)], check=True)
        git(source, 'checkout', '-B', 'main', sha)
        git(source, 'remote', 'remove', 'origin')
        git(source, 'config', 'user.name', 'cheapoS Export Trial')
        git(source, 'config', 'user.email', 'trial@example.invalid')
        text = (source / SPEC).read_text()
        if 'proposed, not yet available or approved' in text:
            parser.error('T42 acceptance commands are still pending')
        manifest = json.loads((source / PACK / 'DIGEST.json').read_text())
        actual = {name: hashlib.sha256((source / PACK / name).read_bytes()).hexdigest() for name in manifest['files']}
        if actual != manifest['files'] or hashlib.sha256(json.dumps(actual, sort_keys=True, separators=(',', ':')).encode()).hexdigest() != manifest['pack_sha256']:
            parser.error('Acceptance manifest does not match its files')
        frozen = {'acceptance_pack_digest': manifest['pack_sha256'], 'app_sha': sha, 'source_sha': sha, 'app_runtime_hash': runtime_hash(app),
                  'acceptance': fingerprint(source, [PACK]), 'spec': fingerprint(source, [SPEC]),
                  'input': args.input, 'access_basis': args.access_basis, 'planning_assisted': False}
        save(root / 'baseline.json', frozen)
    else:
        frozen = json.loads((root / 'baseline.json').read_text())
        if not args.reviewed_digest:
            parser.error('--reviewed-digest is required')
        if frozen['app_runtime_hash'] != runtime_hash(app):
            parser.error('App runtime changed since planning; preserve attempt and prepare a new one')
        if git(source, 'rev-parse', 'main') != frozen['source_sha'] or git(source, 'status', '--porcelain'):
            parser.error('Trial source changed since planning')
        if fingerprint(source, [PACK]) != frozen['acceptance']:
            parser.error('Acceptance pack changed')
    result = {'phase': args.phase, 'app_sha': frozen['app_sha'], 'source_sha': frozen['source_sha'],
              'acceptance_digest': frozen['acceptance']['sha256'], 'acceptance_pack_digest': frozen['acceptance_pack_digest'], 'status': 'not_started',
              'planning_assisted': frozen['planning_assisted'], 'access_basis': frozen['access_basis'], 'interventions_after_start': 0}
    engine = None
    task = None
    started = time.monotonic()
    try:
        # Exclusive phase marker prevents silent retry after uncertain inference/Start.
        fd = os.open(str(root / (args.phase + '.intent')), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        engine = Engine(root / 'state')
        if args.phase == 'plan':
            text = (source / SPEC).read_text()
            request = {'planning_id': 'exporter', 'repository': str(source), 'measurement': True,
                       'limits': {'dollars': 0}, 'base_ref': 'refs/heads/main',
                       'target_ref': 'refs/heads/main', 'feature_ref': 'refs/heads/feature/export-report',
                       'prompt': text if args.input == 'prompt' else 'Implement exactly the three dependent items and exact check lists in the document.' if args.input == 'combined' else '',
                       'document': None if args.input == 'prompt' else SPEC}
            proposal = engine.branch.plan(request)
            save(root / 'proposal.private.json', proposal)
            result.update(task_id=proposal['task_id'], proposal_digest=proposal['digest'], status='proposal')
            task = engine.store.get(proposal['task_id'])
            verify_plan(proposal)
            result['check_contract_matches'] = True
        else:
            saved = json.loads((args.proposal_file or (root / 'proposal.private.json')).read_text())
            if args.proposal_file:
                result['planning_assisted'] = True
                save(root / 'corrected-proposal.private.json', saved)
            if digest(saved['contract']) != args.reviewed_digest or saved['digest'] != args.reviewed_digest:
                raise ValueError('Saved proposal differs from reviewed digest')
            verify_plan(saved)
            task = engine.store.get(saved['task_id'])
            result['planning_accounting'] = accounting(task)
            fresh = engine.branch.proposal(saved['task_id'])
            if fresh['contract'] != saved['contract'] or fresh['digest'] != args.reviewed_digest:
                raise ValueError('Proposal changed; inspect before Start')
            save(root / 'start-proposal.private.json', fresh)
            engine.branch.authorize(saved['task_id'], {'proposal_id': fresh['proposal_id'], 'approved': True})
            runtime = engine.runtimes.get(saved['task_id'])
            while runtime and runtime.thread.is_alive():
                runtime.thread.join(5)
            task = engine.store.get(saved['task_id'])
            result['status'] = task['branch_run']['status']
    except BaseException as error:
        result['error_type'] = type(error).__name__
        save(root / (args.phase + '-error.private.json'), {'type': type(error).__name__, 'detail': str(error)})
    finally:
        if engine:
            active = any(r.thread and r.thread.is_alive() for r in engine.runtimes.values())
            if active and args.phase == 'start':
                result['interventions_after_start'] += 1
            engine.shutdown()
            if task:
                task = engine.store.get(task['id'])
            else:
                records = engine.store.list()
                if len(records) == 1:
                    task = engine.store.get(records[0]['id'])
        result.update(elapsed_seconds=time.monotonic() - started,
                      app_runtime_unchanged=runtime_hash(app) == frozen['app_runtime_hash'],
                      source_main_unchanged=git(source, 'rev-parse', 'main') == frozen['source_sha'],
                      source_clean=not bool(git(source, 'status', '--porcelain')),
                      acceptance_unchanged=fingerprint(source, [PACK]) == frozen['acceptance'])
        if task:
            result['task_id'] = task['id']
            result['configured_models'] = {role: task.get('providers', {}).get(role, {}).get('model') for role in ('worker', 'reviewer')}
            result['run_status'] = task.get('branch_run', {}).get('status')
            result['accounting'] = accounting(task)
            if 'planning_accounting' in result:
                def difference(after, before):
                    return {k: difference(v, before.get(k, {})) if isinstance(v, dict) else v - before.get(k, 0) for k, v in after.items() if isinstance(v, dict) or (isinstance(v, (int, float)) and not isinstance(v, bool))}
                result['execution_accounting_delta'] = difference(result['accounting'], result['planning_accounting'])
            result['candidate_acceptance_unchanged'] = bool(task.get('workspace')) and fingerprint(Path(task['workspace']), [PACK]) == frozen['acceptance']
            receipts = []
            for item in task.get('branch_run', {}).get('items', []):
                receipt = item.get('commit_receipt') or {}
                if receipt.get('stage') == 'completed' and receipt.get('run_id') == task['id'] and receipt.get('item_id') == item['id']:
                    sha = receipt['new_tip']
                    receipts.append({'item_id': item['id'], 'sha': sha, 'object_exists': git(source, 'cat-file', '-t', sha) == 'commit', 'tree': git(source, 'rev-parse', sha + '^{tree}'), 'parent': git(source, 'rev-parse', sha + '^')})
            result['completed_receipts'] = receipts
            result['checks'] = [{'passed': c.get('passed'), 'duration': c.get('duration')} for c in task.get('checks', [])]
        save(root / (args.phase + '-result.json'), result)
        print(json.dumps(result, sort_keys=True))
    return int('error_type' in result or result['status'] not in ('proposal', 'ready_for_merge'))


if __name__ == '__main__':
    raise SystemExit(main())
