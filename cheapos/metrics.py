"""Local evidence accounting. Exports intentionally omit prompts, paths and outputs."""
import hashlib
import math


def number(value):
    return value if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0 else None


def record_usage(record,usage,known):
    usage=usage if isinstance(usage,dict) else {}
    for target,key in [('input_tokens','prompt_tokens'),('output_tokens','completion_tokens')]:record[target]=number(usage.get(key))
    completion=usage.get('completion_tokens_details');prompt=usage.get('prompt_tokens_details')
    record['reasoning_tokens']=number(completion.get('reasoning_tokens')) if isinstance(completion,dict) else None
    record['cached_tokens']=number(prompt.get('cached_tokens')) if isinstance(prompt,dict) else None
    record['reported_cost']=number(usage.get('cost'))
    record['cost_provenance']='provider_reported' if known and record['reported_cost'] is not None else 'estimated' if known else 'uncertain_reservation'


def record_accounted(record, config, reservation, usage, known):
    """Freeze accounting provenance at dispatch/reconciliation, never today's prices."""
    reported = number(usage.get('cost'))
    record['usage_reconciled'] = bool(known)
    record['accounted_tokens'] = usage['prompt_tokens'] + usage['completion_tokens'] if known else reservation['tokens']
    record['accounted_cost'] = (reported if reported is not None else
        (usage['prompt_tokens'] * config['input_rate'] + usage['completion_tokens'] * config['output_rate']) / 1_000_000) if known else max(reservation['cost'], reported or 0)


def token_accounting(task):
    """Explain retained budget estimates without changing the authoritative ledger.

    Only reconciled requests establish reported consumption. Missing historical
    evidence stays unclassified, even when the session cost happens to be zero.
    """
    from .routing_trace import model_label
    roles = {role: {'reported': 0, 'reserved': 0,
                   'accounted': number((task.get('usage', {}).get(role) or {}).get('tokens'))}
             for role in ('coordinator', 'planner', 'worker', 'reviewer')}
    pending = []
    for record in task.get('request_metrics', []):
        bucket = roles.get(record.get('role'))
        if bucket is None:
            continue
        if record.get('usage_reconciled') is True:
            counts = [number(record.get(k)) for k in ('input_tokens', 'output_tokens')]
            if all(v is not None for v in counts):
                bucket['reported'] += sum(counts)
            continue
        reservation = record.get('reservation') or {}
        total = number(reservation.get('tokens'))
        if total is None:
            continue
        bucket['reserved'] += total
        basis = reservation.get('basis') == 'serialized_utf8_bytes_plus_buffer_v1'
        pending.append({'role': record['role'], 'model': model_label(record.get('model')),
                        'purpose': 'probe' if record.get('purpose') == 'probe' else 'planning' if record.get('purpose') == 'branch_planning' else 'model request',
                        'status': record.get('status') if record.get('status') in ('failed', 'cancelled', 'responded') else 'pending',
                        'error_code': model_label(record.get('error_code')) if record.get('error_code') else None,
                        'prompt_tokens': number(reservation.get('prompt_tokens')),
                        'output_tokens': number(reservation.get('completion_tokens')), 'tokens': total,
                        'prompt_bytes': number(reservation.get('prompt_bytes')) if basis else None,
                        'buffer_tokens': number(reservation.get('buffer_tokens')) if basis else None})
    for bucket in roles.values():
        accounted = bucket['accounted']
        explained = bucket['reported'] + bucket['reserved']
        bucket['unclassified'] = max(0, accounted - explained) if accounted is not None else None
        bucket['consistent'] = accounted is not None and explained <= accounted
    complete = (task.get('metrics_schema') == 1 and not task.get('request_metrics_truncated')
                and not task.get('metrics_history_truncated')
                and all(b['consistent'] and b['unclassified'] == 0 for b in roles.values() if b['accounted'] is not None))
    return {'reported': sum(b['reported'] for b in roles.values()),
            'reserved': sum(b['reserved'] for b in roles.values()),
            'accounted': sum(b['accounted'] or 0 for b in roles.values()),
            'unclassified': sum(b['unclassified'] or 0 for b in roles.values()),
            'coverage': 'complete' if complete else 'partial', 'roles': roles,
            'requests': list(reversed(pending[-50:])), 'reservation_count': len(pending),
            'omitted_requests': max(0, len(pending) - 50)}


def aggregate(task):
    events=task.get('events',[]);records=task.get('request_metrics',[]);runs=task.get('run_metrics',[])
    complete=task.get('metrics_schema')==1 and not task.get('request_metrics_truncated') and not task.get('metrics_history_truncated')
    usage=task.get('usage') or {};checks=task.get('checks',[]);reviews=task.get('checkpoints',[])
    def total(key):
        values=[r.get(key) for r in records if r.get('dispatched')]
        return sum(values) if complete and all(number(v) is not None for v in values) else None
    provenance='unknown'
    if task.get('demo'):provenance='scripted_no_model_requests'
    elif usage.get('uncertain_requests',0):provenance='includes_uncertain_reservations'
    elif complete and records:
        sources={r.get('cost_provenance','unknown') for r in records if r.get('dispatched')}
        provenance=next(iter(sources)) if len(sources)==1 else 'mixed_reported_and_estimated'
    elif usage.get('estimated_requests',0):provenance='includes_estimates'
    cancelled=bool(task.get('metrics_cancelled'))
    last_commit=max((i for i,e in enumerate(events) if e['kind']=='commit'),default=-1)
    last_user=max((i for i,e in enumerate(events) if e['kind']=='user'),default=-1)
    accepted=task.get('commits') and (task.get('status')=='completed' or task.get('status')=='awaiting_reply' and last_commit>last_user and not task.get('changes'))
    outcome='human_accepted' if accepted else 'reviewer_approved' if task.get('status')=='approved' else 'cancelled' if cancelled and task.get('status')=='paused' else task.get('status','unknown')
    timing={}
    finished=not task.get('metric_run_id') or task['metric_run_id'] in {r.get('id') for r in runs}
    for key in ('elapsed_seconds','provider_request_seconds','provider_cooldown_seconds','operator_wait_seconds','controller_work_seconds'):
        timing[key]=sum(r[key] for r in runs) if complete and finished and runs and all(number(r.get(key)) is not None for r in runs) else None
    return {'schema_version':1,'coverage':'complete_instrumented' if complete else 'partial_historical',
            'outcome':outcome,'human_accepted_commits':len(task.get('commits',[])),
            'commit_conflict_observed':bool(task.get('commit_conflict_observed')) if complete else None,
            'checks':{'runs':len(checks),'passed':sum(bool(c.get('passed')) for c in checks),'outcomes':[c.get('outcome','unknown') for c in checks]},
            'reviews':{'requests':sum(r.get('role')=='reviewer' and r.get('dispatched',False) for r in records) if complete else None,
                       'decisions':[r.get('decision','unknown') for r in reviews]},
            'calls':{role:sum(r.get('role')==role and r.get('dispatched',False) for r in records) if complete else None for role in ('worker','reviewer','coordinator','planner')},
            'roles':{role:{'tokens':number((usage.get(role) or {}).get('tokens')), 'cost':number((usage.get(role) or {}).get('cost'))} for role in ('worker','reviewer','coordinator','planner')},
            'tool_failures':sum(e['kind']=='tool_error' for e in events) if complete else None,
            'repeated_read_warnings':sum(e['kind']=='guard' and e['title']=='Asking the worker to use what it found' for e in events) if complete else None,
            'handoffs':sum(e['kind']=='handoff' for e in events) if complete else None,
            'recovery_attempts':sum(e['kind']=='guard' and e['title'] in {'Switching to smaller line edits','Preparing an answer from gathered evidence','Moving from repeated reads to the next action'} for e in events) if complete else None,
            'operator':{'check_approvals_requested':sum(e['kind']=='permission' and e['title']=='Permission needed to run the verification command' for e in events) if complete else None,
                        'resumes':sum(e['kind']=='state' and isinstance(e.get('detail'),dict) and e['detail'].get('run_kind')=='resume' for e in events) if complete else None,
                        'accepted_commits':len(task.get('commits',[]))},
            'tokens':{**{key:total(key) for key in ('input_tokens','output_tokens','reasoning_tokens','cached_tokens')},
                      'accounted_total':sum(usage[r]['tokens'] for r in ('worker','reviewer','coordinator','planner') if isinstance(usage.get(r),dict) and number(usage[r].get('tokens')) is not None) if usage else None},
            'cost':{'accounted':number(usage.get('cost')),'provenance':provenance,'uncertain_requests':usage.get('uncertain_requests'),'billing_receipt':False},
            'time':timing,'model_failure':False if cancelled else True if task.get('error_code') in {'invalid_tool_envelope','unsupported_tool','output_limit'} else None,
            'limitations':'Request time includes provider generation and network latency. Controller time excludes measured request/cooldown/operator waits. Historical or unreported fields are unknown; reviewer approval is not human acceptance.'}


def export(tasks):
    records=[{'fixture_id':hashlib.sha256(str(task.get('id','unknown')).encode()).hexdigest()[:16],**aggregate(task)} for task in tasks]
    return {'schema_version':1,'scope':'local evidence only; no model inference or telemetry',
            'summary':{'tasks':len(records),'reviewer_approved':sum(r['outcome']=='reviewer_approved' for r in records),
                       'human_accepted':sum(r['outcome']=='human_accepted' for r in records),'cancelled':sum(r['outcome']=='cancelled' for r in records),
                       'check_approval_interruptions':sum(r['operator']['check_approvals_requested'] or 0 for r in records),
                       'resumes_observed':sum(r['operator']['resumes'] or 0 for r in records)},'tasks':records}
