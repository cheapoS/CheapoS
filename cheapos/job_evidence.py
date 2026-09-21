"""Forward-only, private durable evidence for distinct unattended objectives.

No prompts, paths, model identities or Git refs enter this journal. It is not a
certificate of software correctness. Existing tasks are explicitly partial.
"""
import copy
import hashlib
import uuid
from datetime import datetime, timezone


def stamp():
    return datetime.now(timezone.utc).isoformat()


def opaque(value):
    return str(uuid.uuid5(uuid.NAMESPACE_OID, str(value)))


def prepare(task, previous=None):
    if not task.get('branch_run') or task.get('demo') or task.get('synthetic'):
        return
    prior = previous or {}
    changed = (prior.get('branch_run', {}).get('id') != task['branch_run']['id']
               and prior.get('branch_run', {}).get('status') in {'merged', 'left_on_branch'})
    if not task.get('coding_job_id') or changed:
        task['coding_job_id'] = str(uuid.uuid4())
        task['coding_job_observed_at'] = (task.get('created_at') if prior.get('branch_run') and not changed else None) or stamp()
        task['coding_job_complete'] = changed or not bool(prior.get('branch_run'))


def observe(jobs, task, at=None):
    job_id = task.get('coding_job_id')
    if not job_id:
        return False
    at = at or stamp()
    run = task.get('branch_run') or {}
    previous = jobs.get(job_id)
    j = copy.deepcopy(previous) if previous else dict(
        job_id=job_id, started_at=task['coding_job_observed_at'], revision=0, forward_observed=bool(task.get('coding_job_complete')),
        authorized_at=None, ready_at=None, accepted_at=None, candidate_id=None,
        acceptance_id=None, state='draft', membership_complete=bool(task.get('coding_job_complete')),
        timing_complete=bool(task.get('coding_job_complete')), observation_complete=bool(task.get('coding_job_complete')),
        active_ms=0, provider_wait_ms=0, operator_wait_ms=0,
        rescue_actions=0, approvals=0, unclassified_actions=0, actions={}, last_at=at, clock='draft')
    if run.get('authorization_ref') and not j['authorized_at']:
        j['authorized_at'] = at
        j['approvals'] += 1
    # One mutually exclusive controller clock, never a sum of parallel requests.
    if j['authorized_at'] and previous and previous.get('authorized_at') and not previous.get('ready_at'):
        elapsed = (datetime.fromisoformat(at) - datetime.fromisoformat(j['last_at'])).total_seconds()
        if elapsed < 0:
            j['timing_complete'] = False
        elif j['clock'] in {'active', 'provider_wait', 'operator_wait'}:
            j[j['clock'] + '_ms'] += round(elapsed * 1000)
    state = run.get('status', 'draft')
    j['state'] = ('accepted' if state == 'merged' else 'ready' if state == 'ready_for_merge'
                  else 'stopped' if state == 'left_on_branch' else 'waiting' if state in {'paused', 'blocked'}
                  else 'working' if j['authorized_at'] else 'draft')
    j['clock'] = ('provider_wait' if task.get('route_wait') else 'operator_wait'
                  if state in {'paused', 'blocked'} or task.get('pending_approval') else 'active')
    evidence = run.get('final_evidence') or {}
    ready = run.get('readiness') or {}
    candidate = ready.get('id')
    eligible_candidate = state in {'ready_for_merge', 'merging', 'merged'} or (state == 'paused' and ready.get('integration_blocker'))
    if not eligible_candidate and j['ready_at']:
        j.update(ready_at=None, accepted_at=None, candidate_id=None, acceptance_id=None, timing_complete=False)
    verified = bool(eligible_candidate and candidate and evidence.get('candidate_id') == candidate == evidence.get('review_candidate_id')
                    and all(evidence.get(k) is True for k in ('checks_passed', 'review_approved', 'acceptance_satisfied')))
    if verified:
        if j['candidate_id'] != opaque(candidate):
            if j['ready_at']: j['timing_complete'] = False
            j.update(candidate_id=opaque(candidate), ready_at=at, accepted_at=None, acceptance_id=None)
        receipt = run.get('merge_receipt') or {}
        contract = (run.get('merge_authorization') or {}).get('contract') or {}
        if state == 'merged' and receipt.get('id') and contract.get('readiness_id') == candidate and contract.get('operation', {}).get('id') == receipt['id']:
            j['accepted_at'] = j.get('accepted_at') or at
            j['acceptance_id'] = opaque(receipt['id'])
    if j['state'] == 'accepted' and not j['acceptance_id']:
        j['state'] = 'stopped'
    # API provenance is not proof of human attention. Ambiguous chat is counted
    # separately; only explicit controller action kinds classify rescue.
    for event in task.get('events', []):
        kind = event.get('kind')
        category = ('rescue_actions' if kind in {'operator_revision', 'job_resume'} else
                    'approvals' if kind in {'branch_merged', 'check_approval', 'job_approval'} else
                    'unclassified_actions' if kind in {'user', 'operator_direction', 'branch_guidance'} else None)
        if not j['authorized_at'] or (event.get('time') or '') < j['authorized_at']:
            continue
        if not category:
            continue
        key = hashlib.sha256(str((event.get('id'), event.get('time'), kind)).encode()).hexdigest()
        if key not in j['actions']:
            detail = event.get('detail') if isinstance(event.get('detail'), dict) else {}
            actor = detail.get('evidence_actor') if detail.get('evidence_actor') in {'api', 'operator_ui', 'automation'} else 'unknown'
            j['actions'][key] = {'kind': kind, 'actor': actor, 'classification': category}
            j[category] += 1
            if category == 'rescue_actions' and actor == 'unknown':
                # The action is known, but its caller could be an external
                # automation. Do not claim a complete human-help sample.
                j['unclassified_actions'] += 1
    j['last_at'] = at
    if j != previous:
        j['revision'] += 1
        jobs[job_id] = j
        return True
    return False


def export(journal, rows):
    result = []
    for j in journal.values():
        public = {k: v for k, v in j.items() if k not in {'actions', 'clock', 'last_at'}}
        public['requests'] = [{k: r.get(k) for k in ('request_id', 'status', 'reported_cost_exact', 'reported_currency', 'cost_provenance')}
                              for r in rows if r.get('job_id') == j['job_id']]
        result.append(public)
    return result
