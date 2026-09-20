"""Deidentified local usage journal. Task deletion does not erase accounted work."""
import copy
import hashlib
import json
import os
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .metrics import number
from .request_health import route_name, historical_route_metadata
from . import __version__
from .served_identity import safe_model, normalized

ROLES = ('coordinator', 'planner', 'worker', 'reviewer', 'unknown')
CATEGORIES = ('public_free', 'local', 'included', 'paid', 'unknown')


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def date(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc).date().isoformat()
    except (ValueError, TypeError, AttributeError):
        return None


def resolve_category(record, fallback_cat=None):
    cat = fallback_cat or record.get('category') or record.get('access_class')
    srv_m = safe_model(record.get('served_model'))
    req_m = safe_model(record.get('requested_model', record.get('model')))
    if srv_m and req_m:
        srv_n = normalized(srv_m)
        req_n = normalized(req_m)
        if srv_n != req_n and not req_n.endswith('/' + srv_n) and not srv_n.endswith('/' + req_n):
            return 'unknown'
    if cat in CATEGORIES and cat != 'unknown':
        return cat
    req_lower = (req_m or '').lower()
    if record.get('role') == 'coordinator' or any(req_lower.startswith(p) for p in ('gemma', 'llama', 'qwen', 'ollama')):
        return 'local'
    if any(req_lower.startswith(p) for p in ('antigravity/', 'kiro/', 'kr/', 'nvidia/', 'opencode/')):
        return 'included'
    if ':free' in req_lower or '-free' in req_lower or req_lower.startswith('openrouter/'):
        return 'public_free'
    if (record.get('input_rate') or 0) > 0 or (record.get('output_rate') or 0) > 0 or (record.get('reported_cost') or 0) > 0:
        return 'paid'
    return 'unknown'


def clean(record):
    if not record.get('dispatched') or record.get('synthetic'):
        return None
    result = {key: number(record.get(key)) for key in (
        'input_tokens', 'output_tokens', 'reasoning_tokens', 'cached_tokens', 'reported_cost',
        'accounted_cost', 'accounted_tokens', 'reservation_tokens', 'reservation_cost', 'input_rate', 'output_rate')}
    reservation = record.get('reservation') or {}
    for field, source in [('reservation_tokens', 'tokens'), ('reservation_cost', 'cost')]:
        if result[field] is None:
            result[field] = number(reservation.get(source))
    req_m = safe_model(record.get('requested_model', record.get('model')))
    srv_m = safe_model(record.get('served_model'))
    cat = resolve_category(record, fallback_cat=record.get('access_class'))

    status = record.get('status') or ('responded' if record.get('usage_reconciled') else 'pending')
    purpose = record.get('purpose') or 'work'
    failure_category = record.get('failure_category')
    error_code = record.get('error_code')
    seconds = number(record.get('seconds'))

    result.update(role=record.get('role') if record.get('role') in ROLES else 'unknown',
                  date=date(record.get('requested_at', record.get('created_at'))), category=cat,
                  reconciled=bool(record.get('usage_reconciled') or record.get('cost_provenance') in {'provider_reported', 'estimated'}),
                  requested_model=req_m,
                  served_model=srv_m,
                  status=status,
                  purpose=purpose,
                  failure_category=failure_category,
                  error_code=error_code,
                  seconds=seconds,
                  request_gateway=route_name(record.get('request_gateway')),
                  request_provider=route_name(record.get('request_provider')))
    # Club classification requires explicit access evidence; never infer free pricing from a model prefix.
    result['club_category'] = cat if record.get('access_class') in CATEGORIES else 'unknown'
    if (result['reported_cost'] or 0) > 0: result['club_category'] = 'paid'
    result['charged_free'] = result['category'] == 'public_free' and (result['reported_cost'] or 0) > 0
    if result['charged_free']:
        result['category'] = 'paid'
    known = result['input_tokens'] is not None and result['output_tokens'] is not None
    if result['accounted_tokens'] is None:
        result['accounted_tokens'] = result['input_tokens'] + result['output_tokens'] if known and result['reconciled'] else result['reservation_tokens']
    if result['accounted_cost'] is None:
        if result['reconciled'] and result['reported_cost'] is not None:
            result['accounted_cost'] = result['reported_cost']
        elif known and result['reconciled'] and all(result[k] is not None for k in ('input_rate', 'output_rate')):
            result['accounted_cost'] = (result['input_tokens'] * result['input_rate'] + result['output_tokens'] * result['output_rate']) / 1_000_000
        elif result['category'] in ('public_free', 'included', 'local') and (result['input_rate'] or 0) == 0 and (result['output_rate'] or 0) == 0:
            result['accounted_cost'] = 0.0
        else:
            result['accounted_cost'] = result['reservation_cost']
    return result


class LifetimeUsage:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.suffix != '.json':
            self.path = self.path / 'lifetime-usage.json'
        self.lock = threading.RLock()
        self._summaries = {}
        if self.path.exists():
            # Never silently replace a damaged lifetime journal with zero totals.
            self.state = json.loads(self.path.read_text())
            if self.state.get('schema_version') != 1:
                raise ValueError('Unsupported lifetime usage journal version')
        else:
            stamp = now()
            self.state = dict(schema_version=1, recorded_since=stamp, updated_at=stamp, tasks={})

    def ingest(self, task):
        if task.get('demo') or task.get('synthetic'):
            return
        with self.lock:
            key = digest(task['id'])
            previous = self.state['tasks'].get(key, {})
            entry = copy.deepcopy(previous) or {'requests': {}, 'residual': {}, 'partial': False}
            for record in task.get('request_metrics', []):
                route = historical_route_metadata(record, task.get('gateway_connections'))
                sanitized = clean({**record, **route})
                if sanitized is not None and record.get('id'):
                    request_id = digest(record['id'])
                    prior = entry['requests'].get(request_id, {})
                    if (not route and 'request_gateway' not in record and 'request_provider' not in record
                            and sanitized['requested_model'] == prior.get('requested_model')
                            and sanitized['role'] == prior.get('role')):
                        # Later chat settings may no longer retain the original
                        # connection. Keep already recorded evidence for this ID.
                        for field in ('request_gateway', 'request_provider'):
                            sanitized[field] = route_name(prior.get(field))
                    entry['requests'][request_id] = sanitized
            usage = copy.deepcopy(task.get('usage') or {})
            for record in task.get('request_metrics', []):
                if record.get('synthetic'):
                    synthetic = clean({**record, 'synthetic': False})
                    if synthetic:
                        bucket = usage.get(synthetic['role']) or {}
                        for source, field in [('tokens', 'accounted_tokens'), ('cost', 'accounted_cost')]:
                            if number(bucket.get(source)) is not None:
                                bucket[source] = max(0, bucket[source] - (synthetic[field] or 0))
                        if number(usage.get('cost')) is not None:
                            usage['cost'] = max(0, usage['cost'] - (synthetic['accounted_cost'] or 0))
            # Residual is the task's retained total minus ALL recorded requests,
            # including ones subsequently evicted from capped task history.
            for role in ROLES:
                bucket = usage.get(role) or {}
                records = [r for r in entry['requests'].values() if r['role'] == role]
                entry['residual'][role] = {
                    field: max(0, (number(bucket.get(source)) or 0) - sum(r.get(accounted) or 0 for r in records))
                    for field, source, accounted in [('tokens', 'tokens', 'accounted_tokens'), ('cost', 'cost', 'accounted_cost')]}
            role_cost = sum(v['cost'] for v in entry['residual'].values()) + sum(r.get('accounted_cost') or 0 for r in entry['requests'].values())
            entry['residual']['unknown']['cost'] += max(0, (number(usage.get('cost')) or 0) - role_cost)
            entry['partial'] = bool(entry['partial'] or task.get('metrics_schema') != 1 or task.get('request_metrics_truncated') or task.get('metrics_history_truncated') or
                                    any(v['tokens'] or v['cost'] for v in entry['residual'].values()) or
                                    any(not r['date'] for r in entry['requests'].values()))
            run = task.get('branch_run') or {}
            latest = {role: next((r for r in reversed(list(entry['requests'].values())) if r['role'] == role), {}) for role in ROLES}
            worker, reviewer = latest['worker'].get('served_model'), latest['reviewer'].get('served_model')
            planner = latest['planner'].get('served_model') or latest['planner'].get('requested_model')
            coordinator = latest['coordinator'].get('served_model') or latest['coordinator'].get('requested_model')
            independent = bool(worker and reviewer and normalized(worker) != normalized(reviewer))
            checks = task.get('checks', [])
            checkpoints = task.get('checkpoints', [])
            entry['worker_model'] = worker
            entry['reviewer_model'] = reviewer
            entry['planner_model'] = planner
            entry['coordinator_model'] = coordinator
            entry['independent'] = independent
            entry['checks_summary'] = {
                'runs': len(checks),
                'passed': sum(bool(c.get('passed')) for c in checks),
            }
            entry['reviews_summary'] = {
                'decisions': [c.get('decision') for c in checkpoints if c.get('decision')],
            }
            entry['completion'] = {
                'merged_runs': bool(previous.get('completion', {}).get('merged_runs') or run.get('status') == 'merged' and run.get('merge_receipt')),
                'human_accepted_jobs': bool(previous.get('completion', {}).get('human_accepted_jobs') or not run and task.get('commits')),
                'independent_review_approved_jobs': bool(previous.get('completion', {}).get('independent_review_approved_jobs') or
                    run.get('final_evidence', {}).get('review_approved') is True or
                    task.get('status') == 'approved' and independent and any(c.get('decision') == 'APPROVE' for c in task.get('checkpoints', [])))}
            has_plan = bool(task.get('proposal') or run.get('plan') or run.get('items') or any(r.get('role') == 'planner' for r in entry['requests'].values()))
            review_count = len(entry['reviews_summary']['decisions'])
            if not review_count and any(r.get('role') == 'reviewer' for r in entry['requests'].values()):
                review_count = 1
            is_completed = bool(entry['completion']['merged_runs'] or entry['completion']['human_accepted_jobs'])
            has_coord = bool(entry.get('coordinator_model') or any(r.get('role') == 'coordinator' for r in entry['requests'].values()))
            entry['stage_completion'] = {
                'planning': has_plan,
                'reviewing': review_count,
                'implementation': is_completed,
                'coordination': has_coord
            }
            if entry == previous:
                return
            state = copy.deepcopy(self.state)
            state['tasks'][key] = entry
            state['updated_at'] = now()
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = self.path.with_suffix('.tmp')
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream, allow_nan=False, separators=(',', ':'))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.state = state
            self._summaries.clear()

    ingest_task = ingest

    def summary(self, days=None, allowed_request_ids=None):
        if days not in (None, 'all', 7, 30):
            raise ValueError('Usage period must be all, 7 or 30 days')
        allowed_set = set(allowed_request_ids) if allowed_request_ids is not None else None
        with self.lock:
            cache_key = (days, datetime.now(timezone.utc).date().isoformat())
            if allowed_set is None and cache_key in self._summaries:
                return copy.deepcopy(self._summaries[cache_key])
            state = copy.deepcopy(self.state)
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat() if isinstance(days, int) else None
        result = {k: state[k] for k in ('schema_version', 'recorded_since', 'updated_at')}
        result.update(app_version=__version__, scope='Local installation', period=days or 'all', partial_earlier_history=any(t['partial'] for t in state['tasks'].values()) if allowed_set is None else False,
                      tokens=dict(reported=0, accounted_historical=0, estimated=0, reserved=0, input=0, output=0, reasoning=0, cached=0, unknown_requests=0, unknown_reasoning_requests=0, unknown_cached_requests=0),
                      categories={k: dict(tokens=0, requests=0) for k in CATEGORIES}, roles={k: dict(tokens=0, requests=0) for k in ROLES},
                      models={},
                      purposes={},
                      model_pairs={},
                      cost=dict(provider_reported=0, configured_estimate=0, reserved=0, historical_accounted=0, accounted=0),
                      charged_free_requests=0, charged_free_tokens=0, missing_identity_requests=0, undated_requests=0, history=[],
                      completion=dict(human_accepted_jobs=0, merged_runs=0, independent_review_approved_jobs=0), savings_comparison='not configured')
        history = {}
        for task in state['tasks'].values():
            if allowed_set is not None:
                task_requests = [r for req_id, r in task['requests'].items() if req_id in allowed_set]
                if not task_requests:
                    continue
            else:
                task_requests = list(task['requests'].values())

            # Completion receipts have no reliable date; show lifetime only.
            if not cutoff:
                for k, v in task['completion'].items():
                    result['completion'][k] += int(v)
                if allowed_set is None:
                    for role, residual in task['residual'].items():
                        result['tokens']['accounted_historical'] += residual['tokens']
                        result['cost']['historical_accounted'] += residual['cost']
            for r in task_requests:
                if not r['date']:
                    result['undated_requests'] += 1
                if cutoff and (not r['date'] or r['date'] < cutoff):
                    continue
                known = r['input_tokens'] is not None and r['output_tokens'] is not None
                tokens = (r['input_tokens'] or 0) + (r['output_tokens'] or 0)
                result['tokens']['reported'] += tokens
                result['tokens']['unknown_requests'] += int(not known)
                result['tokens']['unknown_reasoning_requests'] += int(r['reasoning_tokens'] is None)
                result['tokens']['unknown_cached_requests'] += int(r['cached_tokens'] is None)
                for target, source in [('input', 'input_tokens'), ('output', 'output_tokens'), ('reasoning', 'reasoning_tokens'), ('cached', 'cached_tokens')]:
                    result['tokens'][target] += r[source] or 0
                cat = resolve_category(r)
                result['categories'][cat]['tokens'] += tokens
                result['categories'][cat]['requests'] += 1
                result['roles'][r['role']]['tokens'] += tokens
                result['roles'][r['role']]['requests'] += 1
                purp = r.get('purpose') or 'work'
                p_stat = result['purposes'].setdefault(purp, dict(tokens=0, requests=0))
                p_stat['tokens'] += tokens
                p_stat['requests'] += 1
                m = r.get('served_model') or r.get('requested_model')
                if m:
                    m_stat = result['models'].setdefault(m, dict(tokens=0, requests=0, category=cat, successes=0, failures=0, success_rate=None, total_seconds=0.0, duration_samples=0, avg_latency_ms=None, failure_breakdown={}))
                    m_stat['tokens'] += tokens
                    m_stat['requests'] += 1
                    sec = number(r.get('seconds'))
                    st = r.get('status')
                    if sec is not None and st in {'responded', 'failed', 'cancelled'}:
                        m_stat['total_seconds'] += sec
                        m_stat['duration_samples'] += 1
                    if st == 'responded' or (st is None and r.get('reconciled')):
                        m_stat['successes'] += 1
                    elif st == 'failed':
                        m_stat['failures'] += 1
                        fc = r.get('failure_category') or 'unknown'
                        m_stat['failure_breakdown'][fc] = m_stat['failure_breakdown'].get(fc, 0) + 1
                result['charged_free_requests'] += int(r['charged_free'])
                result['charged_free_tokens'] += tokens if r['charged_free'] else 0
                result['missing_identity_requests'] += int(not r['served_model'])
                cost = r['accounted_cost'] or 0
                if cat in ('public_free', 'included', 'local') and (r.get('reported_cost') or 0) == 0 and (r.get('input_rate') or 0) == 0 and (r.get('output_rate') or 0) == 0:
                    cost = 0.0
                if r['reported_cost'] is not None:
                    result['cost']['provider_reported'] += r['reported_cost']
                if r['reconciled']:
                    if r['reported_cost'] is None:
                        result['cost']['configured_estimate'] += cost
                else:
                    result['tokens']['reserved'] += r['reservation_tokens'] or 0
                    result['cost']['reserved'] += max(0, cost - (r['reported_cost'] or 0))
                if r['date']:
                    day = history.setdefault(r['date'], dict(date=r['date'], tokens=0, cost=0))
                    day['tokens'] += tokens
                    day['cost'] += max(cost, r['reported_cost'] or 0)
        result['cost']['accounted'] = sum(result['cost'][k] for k in ('provider_reported', 'configured_estimate', 'reserved', 'historical_accounted'))
        for m_data in result['models'].values():
            decided = m_data['successes'] + m_data['failures']
            if decided > 0:
                m_data['success_rate'] = round((m_data['successes'] / decided) * 100, 1)
            if m_data['duration_samples']:
                m_data['avg_latency_ms'] = round((m_data['total_seconds'] / m_data['duration_samples']) * 1000)

        model_pairs = {}
        for task in state['tasks'].values():
            if allowed_set is not None:
                task_requests = [r for req_id, r in task['requests'].items() if req_id in allowed_set]
                if not task_requests:
                    continue
            else:
                task_requests = list(task['requests'].values())
            w = task.get('worker_model')
            rv = task.get('reviewer_model')
            if w and rv:
                pair_key = f"{w} + {rv}"
                pair = model_pairs.setdefault(pair_key, {
                    'pair_id': pair_key,
                    'worker': w,
                    'reviewer': rv,
                    'is_independent': bool(task.get('independent')),
                    'total_jobs': 0,
                    'merged_runs': 0,
                    'human_accepted_jobs': 0,
                    'review_approved_jobs': 0,
                    'completion_rate': 0.0,
                    'total_tokens': 0,
                    'avg_tokens_per_job': 0,
                })
                pair['total_jobs'] += 1
                task_tokens = sum((r.get('input_tokens') or 0) + (r.get('output_tokens') or 0) for r in task_requests)
                pair['total_tokens'] += task_tokens
                pair['avg_tokens_per_job'] = round(pair['total_tokens'] / pair['total_jobs'])
                comp = task.get('completion', {})
                if comp.get('merged_runs'): pair['merged_runs'] += 1
                if comp.get('human_accepted_jobs'): pair['human_accepted_jobs'] += 1
                if comp.get('independent_review_approved_jobs'): pair['review_approved_jobs'] += 1
                completed = pair['merged_runs'] + pair['human_accepted_jobs']
                pair['completion_rate'] = round((completed / pair['total_jobs']) * 100, 1)
        result['model_pairs'] = dict(sorted(model_pairs.items(), key=lambda item: item[1]['total_jobs'], reverse=True))

        work_tokens = result['purposes'].get('work', {}).get('tokens', 0)
        recovery_tokens = result['purposes'].get('recovery', {}).get('tokens', 0)
        total_code_tokens = work_tokens + recovery_tokens
        result['self_healing_index'] = {
            'initial_work_tokens': work_tokens,
            'recovery_tokens': recovery_tokens,
            'repair_overhead_pct': round((recovery_tokens / max(total_code_tokens, 1)) * 100, 1) if total_code_tokens > 0 else 0.0
        }

        tasks_by_role = {role: {'completed_tasks': 0, 'tokens': 0, 'models': {}} for role in ROLES}
        task_types = {
            'planning': {'completed': 0, 'tokens': 0},
            'implementation': {'completed': 0, 'tokens': 0},
            'reviewing': {'completed': 0, 'tokens': 0},
            'coordination': {'completed': 0, 'tokens': 0},
        }
        for task in state['tasks'].values():
            if allowed_set is not None:
                task_requests = [r for req_id, r in task['requests'].items() if req_id in allowed_set]
                if not task_requests:
                    continue
            else:
                task_requests = list(task['requests'].values())
            stg = task.get('stage_completion') or {}
            comp = task.get('completion') or {}
            if stg.get('planning') or any(r.get('role') == 'planner' for r in task_requests):
                task_types['planning']['completed'] += 1
                tasks_by_role['planner']['completed_tasks'] += 1
                pm = task.get('planner_model')
                if pm:
                    tasks_by_role['planner']['models'][pm] = tasks_by_role['planner']['models'].get(pm, 0) + 1
            if stg.get('implementation') or comp.get('merged_runs') or comp.get('human_accepted_jobs'):
                task_types['implementation']['completed'] += 1
                tasks_by_role['worker']['completed_tasks'] += 1
                wm = task.get('worker_model')
                if wm:
                    tasks_by_role['worker']['models'][wm] = tasks_by_role['worker']['models'].get(wm, 0) + 1
            rev_count = stg.get('reviewing') if isinstance(stg.get('reviewing'), int) else len(task.get('reviews_summary', {}).get('decisions', []))
            if rev_count > 0 or comp.get('independent_review_approved_jobs') or any(r.get('role') == 'reviewer' for r in task_requests):
                task_types['reviewing']['completed'] += max(1, rev_count)
                tasks_by_role['reviewer']['completed_tasks'] += max(1, rev_count)
                rm = task.get('reviewer_model')
                if rm:
                    tasks_by_role['reviewer']['models'][rm] = tasks_by_role['reviewer']['models'].get(rm, 0) + 1
            if stg.get('coordination') or any(r.get('role') == 'coordinator' for r in task_requests):
                task_types['coordination']['completed'] += 1
                tasks_by_role['coordinator']['completed_tasks'] += 1
                cm = task.get('coordinator_model')
                if cm:
                    tasks_by_role['coordinator']['models'][cm] = tasks_by_role['coordinator']['models'].get(cm, 0) + 1

        for role in ROLES:
            if role in result['roles']:
                tasks_by_role[role]['tokens'] = result['roles'][role]['tokens']

        task_types['planning']['tokens'] = tasks_by_role['planner']['tokens']
        task_types['implementation']['tokens'] = tasks_by_role['worker']['tokens']
        task_types['reviewing']['tokens'] = tasks_by_role['reviewer']['tokens']
        task_types['coordination']['tokens'] = tasks_by_role['coordinator']['tokens']

        result['tasks_by_role'] = tasks_by_role
        result['task_types'] = task_types

        total_free = sum(result['categories'][k]['tokens'] for k in ('public_free', 'included', 'local'))
        result['total_free_tokens'] = total_free
        result['zero_cost_share'] = round((total_free / max(result['tokens']['reported'], 1)) * 100, 1) if result['tokens']['reported'] > 0 else 100.0
        result['estimated_savings'] = None
        result['models'] = dict(sorted(result['models'].items(), key=lambda item: item[1]['tokens'], reverse=True))
        result['history'] = sorted(history.values(), key=lambda d: d['date'])[-366:]
        result['limitations'] = [
            'Local installation usage only; no account-wide or other-tool activity. Historical startup/probe usage may be unavailable.',
            'Reported tokens are input plus output; reasoning and cached tokens are subsets, not additional tokens. Missing usage remains unknown.',
            'Undated historical accounted totals are excluded from date filters and have unknown access classification; reservations are not reported usage.',
            'Categories use saved request-time access evidence, never current settings or a zero configured price. Missing served identity does not prove the underlying model.',
            'Local API usage excludes hardware/electricity; included access excludes subscription costs. Accounted cost is not a billing receipt.',
            'Deidentified request accounting and completion counts remain after chat deletion. Prompts, paths, outputs and task titles are not retained here.',
            'Completion counts are lifetime distinct jobs: merged runs separate from human-accepted interactive jobs; independent review is not human acceptance.',
            'Missing daily history is a gap, not zero. Free tokens used do not establish tokens saved or equivalent outcomes.']
        with self.lock:
            if state['updated_at'] == self.state['updated_at']:
                self._summaries[cache_key] = copy.deepcopy(result)
        return result

    def raw_requests(self, days=None):
        with self.lock:
            state = copy.deepcopy(self.state)
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days - 1)).isoformat() if isinstance(days, int) else None
        records = []
        for task_id, task in sorted(state['tasks'].items(), key=lambda t: t[0]):
            for req_id, r in sorted(task['requests'].items(), key=lambda req: (req[1].get('date') or '', req[0])):
                if cutoff and (not r.get('date') or r['date'] < cutoff):
                    continue
                records.append({**r, 'task_id': task_id, 'request_id': req_id})
        return records
