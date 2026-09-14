"""Pure, versioned branch-run contracts. Call mutations under the controller lock.

These helpers grant no execution authority. Evidence fields are controller-owned
receipts, never assertions accepted from a plan or an HTTP request.
"""
import copy
from . import branch_pause
import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone

SCHEMA_VERSION = 1
RUN_STATES = frozenset(('draft', 'awaiting_authorization', 'running', 'paused', 'blocked', 'finalizing', 'ready_for_merge', 'merging', 'merged', 'left_on_branch'))
ITEM_STATES = frozenset(('pending', 'working', 'checking', 'reviewing', 'committing', 'committed', 'satisfied_without_change', 'blocked'))
DONE = frozenset(('committed', 'satisfied_without_change'))
PAUSE_REASONS = frozenset(('operator', 'command_grant', 'missing_setup', 'exhausted_work', 'branch_drift', 'restart', 'missing_information', 'authority_changed', 'recovery_exhausted'))
RUN_EDGES = {
    'draft': {'awaiting_authorization'}, 'awaiting_authorization': {'draft', 'running', 'left_on_branch'},
    'running': {'paused', 'blocked', 'finalizing'}, 'paused': {'running', 'blocked', 'left_on_branch'},
    'blocked': {'running', 'paused', 'left_on_branch'},
    'finalizing': {'paused', 'blocked', 'running', 'ready_for_merge'},
    'ready_for_merge': {'running', 'merging', 'left_on_branch', 'blocked'},
    'merging': {'merged', 'blocked', 'left_on_branch'}, 'merged': set(), 'left_on_branch': set(),
}
ITEM_EDGES = {'pending': {'working', 'blocked'}, 'working': {'checking', 'blocked'},
              'checking': {'working', 'reviewing', 'blocked'},
              'reviewing': {'working', 'committing', 'satisfied_without_change', 'blocked'},
              'committing': {'committed', 'blocked'}, 'blocked': {'working'},
              'committed': set(), 'satisfied_without_change': set()}


def _now(value=None):
    return value if value is not None else datetime.now(timezone.utc).isoformat()


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Run values must be finite JSON data') from exc


def _text(value, label, maximum, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError('%s must be %s–%s characters' % (label, 0 if empty else 1, maximum))
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value):
        raise ValueError('Use a stable item ID of 1–80 letters, digits, dots, dashes or underscores')
    return value


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) - {'items', 'limits', 'final_checks', 'measurement', 'continue_independent'}:
        raise ValueError('Plan must contain items, limits and optional final_checks')
    if 'measurement' in plan and type(plan['measurement']) is not bool:
        raise ValueError('Measurement mode must be explicitly true or false')
    if 'continue_independent' in plan and type(plan['continue_independent']) is not bool:
        raise ValueError('Independent continuation must be explicitly true or false')
    items = plan.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 50:
        raise ValueError('A plan requires 1–50 items; no subset will be executed')
    limits = plan.get('limits')
    if not isinstance(limits, dict) or not limits:
        raise ValueError('Specify finite cumulative limits')
    for key, value in limits.items():
        _text(key, 'Limit name', 80)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 or value > 10 ** 15 or (isinstance(value, float) and not math.isfinite(value)):
            raise ValueError('Limits must be finite nonnegative numbers')
    output = {'items': [], 'limits': copy.deepcopy(limits), 'final_checks': _checks(plan.get('final_checks', []))}
    if 'measurement' in plan: output['measurement'] = plan['measurement']
    if 'continue_independent' in plan: output['continue_independent'] = plan['continue_independent']
    seen = set()
    for item in items:
        allowed = {'id', 'title', 'instructions', 'dependencies', 'acceptance_criteria', 'required_checks', 'revision_of'}
        if not isinstance(item, dict) or set(item) - allowed:
            raise ValueError('Unknown plan item fields')
        identity = _id(item.get('id'))
        if identity in seen:
            raise ValueError('Duplicate item ID')
        seen.add(identity)
        criteria = item.get('acceptance_criteria')
        if not isinstance(criteria, list) or not 1 <= len(criteria) <= 12:
            raise ValueError('Each item requires 1–12 acceptance criteria')
        deps = item.get('dependencies', [])
        if not isinstance(deps, list) or len(deps) > 50 or len(set(_id(d) for d in deps)) != len(deps):
            raise ValueError('Invalid or duplicate dependencies')
        normalized = dict(id=identity, title=_text(item.get('title'), 'Title', 120),
                          instructions=_text(item.get('instructions'), 'Instructions', 4000),
                          dependencies=list(deps), acceptance_criteria=[_text(c, 'Criterion', 500) for c in criteria],
                          required_checks=_checks(item.get('required_checks', [])))
        if item.get('revision_of') is not None:
            normalized['revision_of'] = _id(item['revision_of'])
        output['items'].append(normalized)
    visited = set()
    # Execution order is part of the captured contract, not silently reordered.
    for item in output['items']:
        if any(d not in visited for d in item['dependencies']):
            raise ValueError('Dependencies must reference earlier items; cycles are invalid')
        visited.add(item['id'])
    if len(_json(output)) > 128000:
        raise ValueError('Plan exceeds the aggregate 128,000-character limit')
    return output


def _checks(values):
    if not isinstance(values, list) or len(values) > 12:
        raise ValueError('Specify at most 12 required checks')
    for value in values:
        if not isinstance(value, (str, dict)) or not value or len(_json(value)) > 4000:
            raise ValueError('Each check must be a nonempty bounded JSON specification')
        if isinstance(value, str) and not value.strip():
            raise ValueError('Checks cannot be blank')
    return copy.deepcopy(values)


def compatibility(run):
    supported = isinstance(run, dict) and type(run.get('schema_version')) is int and run['schema_version'] == SCHEMA_VERSION
    return {'supported': supported, 'message': '' if supported else 'This saved branch run uses an unsupported schema. Update cheapoS before resuming; the saved record is preserved.'}


def require_supported(run):
    result = compatibility(run)
    if not result['supported']:
        raise ValueError(result['message'])
    return run


def new_run(plan, original_request='', inputs=None, project=None, base_ref='', base_sha='', target_ref='', feature_ref='', now=None, run_id=None):
    plan = validate_plan(plan)
    _text(original_request, 'Original request', 128000, empty=True)
    captured = copy.deepcopy(inputs or {})
    if len(_json(captured)) > 256000:
        raise ValueError('Captured inputs exceed 256,000 characters')
    timestamp = _now(now)
    run = dict(id=_id(run_id or uuid.uuid4().hex), schema_version=SCHEMA_VERSION, plan_revision=1,
               plan_digest=hashlib.sha256(_json(plan).encode()).hexdigest(), plan=plan,
               original_request=original_request, inputs=captured, project=copy.deepcopy(project),
               base_ref=base_ref, base_sha=base_sha, target_ref=target_ref, feature_ref=feature_ref,
               expected_feature_tip=None, workspace_mapping={}, status='draft', current_item_id=None,
               authorization_ref=None, limits=copy.deepcopy(plan['limits']), consumption={k: 0 for k in plan['limits']},
               created_at=timestamp, updated_at=timestamp, pause_reason=None, pending_operations=[],
               final_evidence={}, events=[], event_sequence=0, items=[])
    for item in plan['items']:
        run['items'].append(dict(copy.deepcopy(item), status='pending', recovery={'attempts': 0},
                                 evidence={}, outcome_summary='', commit_receipt=None))
    _json(run)
    return run


create_run = new_run


def append_event(run, kind, detail=None, event_key=None, now=None):
    require_supported(run)
    _text(kind, 'Event kind', 80)
    if event_key is not None:
        _text(event_key, 'Event key', 160)
        for event in run['events']:
            if event.get('key') == event_key:
                return event
    if len(_json(detail)) > 4000:
        raise ValueError('Event detail exceeds 4,000 characters')
    sequence = run['event_sequence'] + 1
    event = dict(id='%s:%s' % (run['id'], sequence), sequence=sequence, kind=kind,
                 detail=copy.deepcopy(detail), key=event_key, created_at=_now(now))
    run['events'].append(event)
    run['event_sequence'] = sequence
    run['updated_at'] = event['created_at']
    return event


def _approved(evidence):
    return (isinstance(evidence, dict) and evidence.get('acceptance_satisfied') is True
            and evidence.get('checks_passed') is True and evidence.get('review_approved') is True
            and bool(evidence.get('candidate_id')) and evidence.get('candidate_id') == evidence.get('review_candidate_id')
            and bool(evidence.get('worker_model')) and bool(evidence.get('reviewer_model'))
            and evidence['worker_model'] != evidence['reviewer_model'])


def transition(run, status, reason=None, now=None):
    require_supported(run)
    old = run['status']
    if status == old:
        return run
    if status not in RUN_EDGES.get(old, set()):
        raise ValueError('Illegal run transition: %s → %s' % (old, status))
    if status in {'paused', 'blocked'} and reason not in PAUSE_REASONS:
        raise ValueError('A typed pause reason is required')
    if status == 'running' and not run.get('authorization_ref'):
        raise ValueError('Run authorization is required')
    if status in {'finalizing', 'ready_for_merge', 'merging', 'merged'} and any(i['status'] not in DONE for i in run['items']):
        raise ValueError('All items must have verified outcomes')
    if status in {'ready_for_merge', 'merging', 'merged'} and not _approved(run.get('final_evidence')):
        raise ValueError('Final check and independent review evidence is required')
    if status == 'merging' and not run.get('merge_authorization_ref'):
        raise ValueError('Explicit merge authorization is required')
    if status == 'merged' and not run.get('merge_receipt'):
        raise ValueError('A completed merge receipt is required')
    run['status'], run['pause_reason'] = status, reason if status in {'paused', 'blocked'} else None
    if status not in {'paused','blocked'}:branch_pause.clear(run)
    append_event(run, 'run_transition', {'from': old, 'to': status, 'reason': run['pause_reason']}, now=now)
    return run


transition_run = transition


def transition_item(run, item_id, status, evidence=None, now=None):
    require_supported(run)
    item = next((i for i in run['items'] if i['id'] == item_id), None)
    if item is None:
        raise ValueError('Unknown item ID')
    old = item['status']
    if old == status:
        return item
    if status not in ITEM_EDGES.get(old, set()):
        raise ValueError('Illegal item transition: %s → %s' % (old, status))
    if status == 'working':
        done = {i['id'] for i in run['items'] if i['status'] in DONE}
        if not set(item['dependencies']).issubset(done):
            raise ValueError('Dependencies are not complete')
        if any(i['id'] != item_id and i['status'] in {'working', 'checking', 'reviewing', 'committing'} for i in run['items']):
            raise ValueError('Only one item may execute at a time')
    candidate = copy.deepcopy(evidence if evidence is not None else item['evidence'])
    _json(candidate)
    if status in {'committing', 'committed', 'satisfied_without_change'} and not _approved(candidate):
        raise ValueError('Exact acceptance, checks and independent review evidence is required')
    if status == 'satisfied_without_change' and candidate.get('no_change') is not True:
        raise ValueError('A reviewed no-change outcome is required')
    if status == 'committed' and not item.get('commit_receipt'):
        raise ValueError('An immutable commit receipt is required')
    item['status'], item['evidence'] = status, candidate
    run['current_item_id'] = None if status in DONE else item_id
    append_event(run, 'item_transition', {'item_id': item_id, 'from': old, 'to': status}, now=now)
    return item


def summary(run):
    """Allowlist output: no original input, tokens, authorization or command grants."""
    state = compatibility(run)
    if not state['supported']:
        return {'compatible': False, 'compatibility_message': state['message'], 'status': 'blocked'}
    items = run.get('items', [])
    return {'id': str(run.get('id', ''))[:80], 'schema_version': SCHEMA_VERSION,
            'compatible': True, 'status': run.get('status') if run.get('status') in RUN_STATES else 'blocked',
            'plan_revision': run.get('plan_revision') if type(run.get('plan_revision')) is int and 0 <= run['plan_revision'] <= 10 ** 9 else None, 'current_item_id': str(run.get('current_item_id') or '')[:80] or None,
            'pause_reason': run.get('pause_reason') if run.get('pause_reason') in PAUSE_REASONS else None,
            'pause_detail': branch_pause.public(run.get('pause_detail')) if run.get('status') in {'paused','blocked'} else None,
            'item_count': len(items), 'completed_count': sum(i.get('status') in DONE for i in items),
            'items': [{'id': str(i.get('id', ''))[:80], 'title': str(i.get('title', ''))[:120],
                       'status': i.get('status') if i.get('status') in ITEM_STATES else 'blocked'} for i in items[:50]]}


def task_status(run):
    """Map execution state only; archive/trash metadata is independent."""
    if not compatibility(run)['supported']:
        return 'interrupted'
    return {'draft': 'ready', 'awaiting_authorization': 'ready',
            'running': 'running', 'paused': 'paused', 'blocked': 'paused',
            'finalizing': 'reviewing', 'ready_for_merge': 'approved', 'merging': 'running',
            'merged': 'completed', 'left_on_branch': 'completed'}.get(run.get('status'), 'interrupted')


def recover_restart(run, now=None):
    """Never dispatch at startup or renew allowances; preserve unknown records."""
    if compatibility(run)['supported'] and run.get('status') in {'running', 'finalizing', 'merging'}:
        old = run['status']
        run['status'] = 'paused'
        run['pause_reason'] = 'restart'
        run['pause_detail']=branch_pause.public({'version':1,'cause':'restart','stage':old,'item_id':run.get('current_item_id')})
        append_event(run, 'run_transition', {'from': old, 'to': 'paused', 'reason': 'restart'}, now=now)
    return run
