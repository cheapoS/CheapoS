"""Controller-owned, immutable candidate receipts for unattended branch work.

No model completion status or manual takeover exception grants eligibility here.
Persist receipts as JSON strings; later baseline advances never rewrite them.
"""
import copy
import hashlib
import json
import shlex
from .verification import evidence_identity, normalize_unittest
from .workspace import Workspace, git


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def commands(specifications):
    """Normalize captured check specs without mutating a task's command field."""
    if not isinstance(specifications, list) or len(specifications) > 20:
        raise ValueError('Required checks must be a finite list')
    result = []
    for spec in specifications:
        command = spec.get('command') if isinstance(spec, dict) else spec
        argv = shlex.split(command) if isinstance(command, str) else command
        if not isinstance(argv, list) or not argv or not all(isinstance(s, str) and s and '\0' not in s for s in argv):
            raise ValueError('Invalid required check command')
        argv = normalize_unittest(argv)
        if argv in result:
            raise ValueError('Duplicate required check command')
        result.append(list(argv))
    return result


def candidate(task, context, required_checks, criteria=None):
    """Read the actual workspace; context is supplied by the owning controller."""
    required = ('run_id', 'plan_revision', 'item_id', 'item_revision', 'feature_parent')
    if any(context.get(key) is None for key in required):
        raise ValueError('Incomplete run candidate context')
    criteria = criteria if criteria is not None else context.get('acceptance_criteria')
    if not isinstance(criteria, list) or not criteria or not all(isinstance(c, str) and c.strip() for c in criteria) or len(set(criteria)) != len(criteria):
        raise ValueError('Candidate requires distinct acceptance criteria')
    workspace = Workspace(task['workspace'])
    patch = workspace.patch(validate=True)
    checks = []
    for argv in commands(required_checks):
        identity = evidence_identity({**task, 'check_command': argv})
        if not identity:
            raise ValueError('Verification environment is missing or cannot be identified')
        checks.append({'command': argv, 'verification_identity': identity})
    value = {'version': 1, 'context': copy.deepcopy(context), 'criteria': list(criteria),
             'workspace': str(workspace.root), 'generation': task.get('workspace_generation', 0),
             'private_baseline': git(workspace.root, 'rev-parse', 'HEAD').strip(),
             'patch': patch, 'patch_digest': hashlib.sha256(patch.encode()).hexdigest(),
             'check_specifications': copy.deepcopy(required_checks), 'checks': checks}
    value['id'] = _digest(value)
    return value


def bind_check(current, command, record):
    """Accept only controller-executed, complete checks of these exact inputs."""
    from .test_policy import require_verification
    require_verification(command)
    expected = next((c for c in current['checks'] if c['command'] == command), None)
    if not expected or record.get('command') != command or record.get('passed') is not True or record.get('exit_code') != 0 or record.get('reason') or record.get('truncated') or record.get('outcome', 'passed') != 'passed':
        raise ValueError('Required verification did not complete successfully')
    if record.get('verification_identity') != expected['verification_identity'] or record.get('input_identity') != expected['verification_identity']:
        raise ValueError('Verification is stale or its inputs changed')
    return {'candidate_id': current['id'], 'command': list(command), 'record': copy.deepcopy(record)}


def current_checks(current, records):
    """Use the latest result matching each command; older failures are history."""
    result = []
    for expected in current['checks']:
        record = next((r for r in reversed(records) if r.get('command') == expected['command']), {})
        result.append(bind_check(current, expected['command'], record))
    return result


def review_packet(current, item, plan, checks, uncertainties=''):
    if item.get('acceptance_criteria') != current['criteria']:
        raise ValueError('Item criteria changed')
    return {'candidate_id': current['id'], 'context': copy.deepcopy(current['context']),
            'item': {key: copy.deepcopy(item[key]) for key in ('id','title','instructions','dependencies','acceptance_criteria','required_checks','revision_of','revision') if key in item}, 'plan': copy.deepcopy(plan), 'diff': current['patch'],
            'checks': copy.deepcopy(checks), 'uncertainties': str(uncertainties),
            'acceptance_criteria': list(current['criteria'])}


def model_identity(model):
    """Compare named models, not gateway URLs or provider request IDs."""
    value = (model.get('model') or model.get('id')) if isinstance(model, dict) else model
    if not isinstance(value, str) or not value.strip():
        raise ValueError('A named model identity is required')
    value = value.strip().lower()
    if value.startswith('openrouter/'):
        value = value[len('openrouter/'):]
    if value.endswith(':free'):
        value = value[:-5]
    if value in {'auto', 'free', 'router', 'openrouter/auto', 'openrouter/free'}:
        raise ValueError('An opaque router cannot establish model independence')
    return value


def ready_receipt(current, checks, review, worker_model, reviewer_model, criteria_outcomes):
    worker, reviewer = model_identity(worker_model), model_identity(reviewer_model)
    if worker == reviewer:
        raise ValueError('Automatic commits require a distinct reviewer model')
    from .branch_disagreement import decision
    decision(review)
    if review.get('candidate_id') != current['id'] or review.get('decision') != 'APPROVE' or not isinstance(review.get('feedback'), str):
        raise ValueError('Independent APPROVE for this candidate is required')
    if not isinstance(criteria_outcomes, dict):
        raise ValueError('criteria_outcomes must be an object keyed by each exact acceptance criterion')
    if set(criteria_outcomes) != set(current['criteria']):
        raise ValueError('Use the exact criterion keys. Missing: '+json.dumps(sorted(set(current['criteria'])-set(criteria_outcomes)))+'; unexpected: '+json.dumps(sorted(set(criteria_outcomes)-set(current['criteria']))))
    for criterion, value in criteria_outcomes.items():
        if not isinstance(value, dict) or value.get('passed') is not True or not isinstance(value.get('evidence'), str) or not value['evidence'].strip():
            raise ValueError('Criterion '+json.dumps(criterion)+' requires {"passed": true, "evidence": "specific nonempty evidence"}; passed must be a JSON boolean, not a string')
    if len(checks) != len(current['checks']):
        raise ValueError('Missing required checks')
    for expected, bound in zip(current['checks'], checks):
        if bound.get('candidate_id') != current['id']:
            raise ValueError('Check belongs to a different candidate')
        bind_check(current, expected['command'], bound['record'])
    receipt = {'version': 1, 'candidate': copy.deepcopy(current), 'checks': copy.deepcopy(checks),
               'review': copy.deepcopy(review), 'worker_model': worker, 'reviewer_model': reviewer,
               'criteria_outcomes': copy.deepcopy(criteria_outcomes),
               'outcome': 'ready' if current['patch'] else 'satisfied_without_change'}
    receipt['id'] = _digest(receipt)
    return _json(receipt)


def revalidate(receipt, task, context, required_checks, criteria=None):
    """Re-read files/environment/HEAD immediately before controller commit."""
    saved = json.loads(receipt)
    identity = saved.pop('id')
    if _digest(saved) != identity:
        raise ValueError('Receipt contents changed')
    current = candidate(task, context, required_checks, criteria)
    if current != saved['candidate']:
        raise ValueError('Candidate changed since checks and independent review')
    rebuilt = ready_receipt(current, saved['checks'], saved['review'], saved['worker_model'], saved['reviewer_model'], saved['criteria_outcomes'])
    if rebuilt != receipt:
        raise ValueError('Invalid ready receipt')
    return json.loads(receipt)
