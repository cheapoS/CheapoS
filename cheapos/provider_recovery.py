"""Availability failover is separate from repairing a model's work.

All dispatches retain their usage/request reservations. These helpers only stop
outages consuming the allowance intended for substantive review exchanges.
"""
OUTAGES = {'gateway_cooldown', 'http_429', 'http_408', 'http_500', 'http_502',
           'http_503', 'http_504', 'model_connection', 'model_timeout', 'stream_timeout', 'stream_error', 'stream_interrupted'}


def provider(model):
    # These transport aliases share the underlying provider's outage scope.
    return model.removeprefix('no-think/').split('/', 1)[0]


def outage(task, role, recovery):
    if not recovery: return False
    if recovery.get('error_code') in OUTAGES: return True
    # Older saved recovery records did not retain the code. Only the matching
    # actual failed request can supply it; arbitrary error strings cannot.
    record = next((r for r in reversed(task.get('request_metrics', []))
                   if r.get('role') == role and r.get('purpose') != 'probe'), {})
    return (record.get('model') == recovery.get('from') and record.get('status') == 'failed'
            and record.get('dispatched') and record.get('error_code') in OUTAGES)


def review_turns(task, pending):
    candidate = pending.get('branch_candidate_id')
    if not candidate: return pending.get('review_requests', 0)
    # Recover old branch records using the first checkpoint for this exact
    # candidate. A later candidate cannot inherit its predecessor's allowance.
    times = [e.get('time') for e in task.get('events', []) if e.get('kind') == 'checkpoint'
             and isinstance(e.get('detail'), dict) and e['detail'].get('candidate_id') == candidate and e.get('time')]
    start = min(times) if times else None
    failed = set()
    for r in task.get('request_metrics', []):
        same = r.get('review_candidate_id') == candidate
        if not r.get('review_candidate_id') and start:
            same = (r.get('branch_item_id') == task.get('branch_run', {}).get('current_item_id')
                    and r.get('requested_at', '') >= start)
        if (same and r.get('id') and r.get('role') == 'reviewer' and r.get('purpose') == 'work'
                and r.get('status') == 'failed' and r.get('dispatched') and r.get('error_code') in OUTAGES):
            failed.add(r['id'])
    return max(0, pending.get('review_requests', 0) - len(failed))
