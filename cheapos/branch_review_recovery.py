"""Continue stalled item reviews on unused, authorized independent routes.

Failure history belongs to the candidate and survives Resume/restart. A handoff
starts a new review conversation, never a new work/spending allowance.
"""
import copy

from .model_pool import automatic
from .provider_recovery import review_turns
from .served_identity import normalized


def failed_models(task):
    run=task.get('branch_run',{})
    active=run.get('active_final_review') or {}
    if active and (run.get('current_item_id') is None or active.get('kind') == 'item'):
        return run.get('final_review_recovery',{}).get(active.get('manifest_id'),{}).get('failed_models',[])
    candidate = (task.get('pending_review') or {}).get('branch_candidate_id')
    return task.get('branch_run', {}).get('review_recovery', {}).get(candidate, {}).get('failed_models', [])


def invalid_attempts(task, pending):
    saved = task['branch_run'].get('review_disagreements', {}).get(pending['branch_candidate_id'], {})
    return max(0, saved.get('unsupported_attempts', 0) - pending.get('unsupported_baseline', 0))


def recover(engine, runtime, diagnostic):
    from . import routing, reviewer_recovery
    task = runtime.task
    pending = task['pending_review']
    current = (task.get('providers', {}).get('reviewer') or {})
    current = current.get('model') if isinstance(current, dict) else current
    if (not automatic(task, 'reviewer') or task.get('operator_reviewer_model') == current):
        pending['stop_diagnostic']['recovery'] = 'manual'
        engine.store.save(task)
        return False
    runtime.guard()
    if runtime.stop.is_set():
        raise InterruptedError('Task stopped')
    if reviewer_recovery.unknown_workers(task):
        pending['stop_diagnostic']['recovery'] = 'identity'
        engine.store.save(task)
        return False
    run = task['branch_run']
    candidate = pending['branch_candidate_id']
    recovery = run.setdefault('review_recovery', {}).setdefault(candidate, {'failed_models': [], 'history': []})
    selection = recovery.get('selection')
    if not selection:
        if current not in recovery['failed_models']:
            recovery['failed_models'].append(current)
        selection = recovery['selection'] = {'from': current, 'reason': diagnostic['reason']}
        engine.event(task, 'reviewer_recovery', 'The reviewer stalled. Selecting another eligible reviewer.', {
            'role': 'reviewer', 'item_id': run['current_item_id'], 'from': current,
            'reason': diagnostic['reason'], 'candidate_id': candidate,
            'summary': 'Keeping saved changes and verification evidence; continuing independent review.'})
        engine.store.save(task)  # Before route selection/probes, including interrupted selection.
    failed = {normalized(model) for model in recovery['failed_models']}
    if normalized(current) in failed:
        routing.select_remote(engine, runtime, 'reviewer', replace=True)
        current = task['providers']['reviewer']['model']
    if normalized(current) in failed:
        raise routing.RoutingPause('No unused eligible reviewer is available. Saved changes and checks are retained. Choose another reviewer or restore an authorized connection.')
    runtime.guard()
    if runtime.stop.is_set():
        raise InterruptedError('Task stopped')
    # Archive the entire failed exchange; only the next reviewer's local counters
    # get a new baseline. Cumulative requests, usage, limits and findings remain.
    recovery['history'].append({'from': selection['from'], 'to': current,
                                'reason': selection['reason'], 'review': copy.deepcopy(pending)})
    fresh = {key: copy.deepcopy(pending[key]) for key in
             ('branch_candidate_id', 'identity_scope', 'worker_summary', 'uncertainties', 'repair_dispositions', 'pull_request') if key in pending}
    proof = pending.get('evidence_review') or {}
    from .review_assessment import VERSION
    if proof.get('version') == VERSION and proof.get('scope') == candidate:
        # Read results are controller-owned facts about this unchanged candidate,
        # not the failed reviewer's judgment. Let the successor retrieve them.
        fresh['evidence_review'] = copy.deepcopy(proof)
    fresh.update(reviewer_model=current, review_requests=pending.get('review_requests', 0),
                 review_turn_baseline=review_turns(task, pending) + pending.get('review_turn_baseline', 0),
                 unsupported_baseline=run.get('review_disagreements', {}).get(candidate, {}).get('unsupported_attempts', 0),
                 messages=[], observations={})
    task['pending_review'] = fresh
    recovery.pop('selection', None)
    task.update(status='reviewing', error=None, error_code=None)
    engine.event(task, 'handoff', 'Continuing saved review with another reviewer', {
        'role': 'reviewer', 'from': selection['from'], 'to': current, 'candidate_id': candidate,
        'summary': 'The new reviewer receives the current changes, criteria, checks and unresolved findings. Implementation is unchanged.'})
    engine.store.save(task)
    return True
