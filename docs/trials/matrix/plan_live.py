"""Measure live proposal generation only; never authorize or execute a proposal.

Example (operator-authorized live planning):
  python3 -B docs/trials/matrix/plan_live.py easy 1 --input prompt --live \
    --config-dir /tmp/cheapos-antigravity-trial-config \
    --root /tmp/cheapos-planning-antigravity-20260913

Use --input document to qualify the independent document-only path. Combined
input is available separately. Private state/proposals stay outside the repo;
only the allowlisted result.json is intended as shareable measurement evidence.
The generated proposal still requires human review and the app's Start action.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import sys
import time

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from cheapos.engine import Engine
from cheapos.workspace import git
from cheapos.branch_evidence import commands


def private_json(path, value):
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def numeric(value):
    """Do not copy free-form model/provider text into published accounting."""
    if isinstance(value, dict):
        return {key: cleaned for key, item in value.items()
                if (cleaned := numeric(item)) is not None}
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None


def code_hash():
    content = b''.join(path.name.encode() + b'\0' + path.read_bytes()
                       for path in sorted((REPO / 'cheapos').glob('*.py')))
    return hashlib.sha256(content).hexdigest()


def specification(level):
    # Reuse exactly the execution trial's independently supplied fixtures.
    spec = importlib.util.spec_from_file_location('matrix_fixtures', Path(__file__).with_name('run_live.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    files, items = module.fixture(level)
    final_argv = [sys.executable, '-B', '-m', 'unittest', '-v', 'test_acceptance']
    checks = []
    text = ['# Planning qualification',
            'Implement exactly %s implementation items. Tests and checkpoints belong within each item. '
            'Do not change supplied acceptance tests. Standard library only. Preserve this item grouping and these exact test commands.' % len(items)]
    for index, item in enumerate(items, 1):
        identity, title, instructions, criteria = item[:4]
        argv = final_argv[:-1] + [final_argv[-1] + ('.' + item[4] if len(item) > 4 else '')]
        checks.append(argv)
        text.extend(['## Item %s: %s' % (index, title), 'Stable item ID: ' + identity,
                     instructions, 'Acceptance criteria:\n' + '\n'.join('- ' + c for c in criteria),
                     'Required check: `' + shlex.join(argv) + '`'])
    text.extend(['## Final integration check', '`' + shlex.join(final_argv) + '`'])
    return files, '\n\n'.join(text) + '\n', checks, final_argv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('level', choices=['easy', 'medium', 'hard', 'very-hard'])
    parser.add_argument('attempt', type=int)
    parser.add_argument('--input', choices=['prompt', 'document', 'combined'], required=True)
    parser.add_argument('--config-dir', type=Path, required=True, help='Existing pinned profile; never modified')
    parser.add_argument('--root', type=Path, required=True, help='Fresh measurement parent outside this repository')
    parser.add_argument('--live', action='store_true', help='Explicitly authorize planning inference only')
    args = parser.parse_args()
    if not args.live:
        parser.error('Planning makes live provider requests; it requires explicit --live. No Start action is implemented.')
    if args.attempt < 1:
        parser.error('Attempt must be positive')
    parent = args.root.expanduser().resolve()
    if parent == REPO or REPO in parent.parents:
        parser.error('Private trial state must be outside the repository')
    profile = args.config_dir.expanduser().resolve(strict=True)
    for name in ('config.json', 'preferences.json', 'gateway.json'):
        if not (profile / name).is_file():
            parser.error('Pinned profile is missing ' + name)
    files, text, expected_checks, expected_final = specification(args.level)
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = parent / ('planning-%s-%s-%s' % (args.level, args.input, args.attempt))
    root.mkdir(mode=0o700)  # Never overwrite another measurement or its state.
    source = root / 'project'; source.mkdir(mode=0o700)
    state = root / 'state'; state.mkdir(mode=0o700)
    for name in ('config.json', 'preferences.json', 'gateway.json'):
        destination = state / name
        descriptor = os.open(str(destination), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with (profile / name).open('rb') as original, os.fdopen(descriptor, 'wb') as copied:
            shutil.copyfileobj(original, copied)
    if args.input != 'prompt':
        files['TRIAL.md'] = text
    for name, content in files.items():
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    git(source, 'init', '-qb', 'main')
    git(source, 'config', 'user.name', 'cheapoS Planning Trial')
    git(source, 'config', 'user.email', 'trial@example.invalid')
    git(source, 'add', '.')
    git(source, 'commit', '-qm', 'Independent planning qualification baseline')
    baseline = git(source, 'rev-parse', 'HEAD').strip()
    prompt = text if args.input == 'prompt' else '' if args.input == 'document' else 'Prepare the complete job in TRIAL.md. Preserve the stated grouping and exact test commands.'
    request = {'planning_id':'planning-%s-%s-%s' % (args.level,args.input,args.attempt),
               'repository':str(source), 'prompt':prompt, 'document':None if args.input == 'prompt' else 'TRIAL.md',
               'measurement':True, 'limits':{'dollars':0}, 'base_ref':'refs/heads/main',
               'target_ref':'refs/heads/main', 'feature_ref':'refs/heads/feature/trial'}
    before = code_hash()
    result = {'kind':'planning_only', 'level':args.level, 'attempt':args.attempt, 'input':args.input,
              'measurement':True, 'profile_name':profile.name, 'execution_started':False, 'proposal_review_required':True,
              'app_commit':git(REPO,'rev-parse','HEAD').strip(), 'app_code_hash':before,
              'expected_item_count':len(expected_checks), 'expected_checks':expected_checks,
              'expected_final_checks':[expected_final]}
    engine = None; started = time.monotonic()
    try:
        engine = Engine(state)
        proposal = engine.branch.plan(request)
        private_json(root / 'proposal.private.json', proposal)
        plan = proposal['contract']['plan']
        actual_checks = [commands(item['required_checks']) for item in plan['items']]
        result.update(status='proposal', item_count=len(plan['items']),
                      grouping_count_matches=len(plan['items']) == len(expected_checks),
                      item_checks_match=actual_checks == [[argv] for argv in expected_checks],
                      final_checks_match=commands(plan['final_checks']) == [expected_final],
                      proposal_digest=proposal['digest'])
    except Exception as error:
        result.update(status='clarification' if type(error).__name__=='ClarificationRequired' else 'planning_error', error_type=type(error).__name__)
        private_json(root / 'error.private.json', {'type':type(error).__name__, 'detail':str(error)})
    finally:
        result['planning_seconds'] = time.monotonic() - started
        tasks = engine.store.list() if engine else []
        result['tasks'] = [{'id':task['id'], 'status':task['status'], 'usage':numeric(task.get('usage',{})),
                            'request_count':len(task.get('request_metrics',[])),
                            'requests_by_role':{role:sum(q.get('role') == role for q in task.get('request_metrics',[])) for role in ('worker','reviewer')},
                            'cost_provenance_counts':{kind:sum(q.get('cost_provenance') == kind for q in task.get('request_metrics',[])) for kind in ('provider_reported','estimated','uncertain_reservation')},
                            'consumption':numeric(task.get('branch_run',{}).get('consumption',{}))} for task in tasks]
        result['independent'] = {'source_main_unchanged':git(source,'rev-parse','main').strip() == baseline,
                                 'source_clean':not git(source,'status','--porcelain'),
                                 'feature_branch_absent':not git(source,'for-each-ref','--format=%(refname)','refs/heads/feature/trial').strip(),
                                 'no_run_authorized':all(not task.get('branch_run',{}).get('authorization') for task in tasks),
                                 'app_code_unchanged':code_hash() == before}
        if engine:
            engine.shutdown()
        private_json(root / 'result.json', result)
        print(json.dumps({'status':result['status'], 'input':args.input, 'planning_seconds':result['planning_seconds'],
                          'result':str(root / 'result.json'), 'proposal_review_required':True}), flush=True)
    return 0 if result['status'] == 'proposal' and all(result['independent'].values()) and all(result[key] for key in ('grouping_count_matches','item_checks_match','final_checks_match')) else 1


if __name__ == '__main__':
    raise SystemExit(main())
