"""Operator policy v2: independent nullable work budgets, separate from money."""
FIELDS = {'work_requests':'requests', 'work_turns':'worker_turns', 'work_tools':'tool_actions',
          'work_seconds':'working_seconds', 'work_review_tokens':'reviewer_tokens', 'work_iterations':'iterations'}
OPERATIONS = {'response_tokens', 'verification_seconds', 'request_seconds'}
KEYS = set(FIELDS) | OPERATIONS | {'work_policy_version'}


def validate(values):
    if 'work_policy_version' in values and values['work_policy_version'] != 2:
        raise ValueError('Unsupported work policy version')
    result = {}
    for key in KEYS & values.keys():
        value = values[key]
        if key in FIELDS and value is None: pass
        elif key in OPERATIONS and value == 'automatic': pass
        elif type(value) is not int or not 0 <= value <= 2**53-1 or (key in OPERATIONS and value < 1):
            raise ValueError('Invalid limit: '+key)
        result[key] = value
    return result


def active(task):
    limits = task.get('branch_run', {}).get('plan', {}).get('limits', {}) if 'branch_run' in task else task.get('limits', {})
    return limits.get('work_policy_version') == 2


def effective(task):
    limits = task.get('limits', {})
    run = task.get('branch_run')
    if run is not None:
        limits = {**limits, **run.get('plan', {}).get('limits', {})}
        uncapped = bool(run.get('plan', {}).get('uncapped_work') or run.get('plan', {}).get('measurement'))
    else: uncapped = limits.get('uncapped_work') is True
    result = {}
    for key, counter in FIELDS.items():
        legacy = limits.get(counter)
        if counter == 'working_seconds': legacy = limits.get('working_seconds', limits.get('run_minutes',15)*60)
        result[key] = limits.get(key, None if uncapped else legacy)
    return result


def usage(task, *, seconds=None):
    from .metrics import action_totals
    counts = action_totals(task)['counts']
    replies = task.get('discussion_requests', {})
    counts = {role: max(0, value - replies.get(role, 0)) for role, value in counts.items()}
    consumed = task.get('branch_run', {}).get('consumption', {})
    used = {'work_requests': sum(v for k,v in counts.items() if k != 'tools'),
            'work_turns': counts.get('worker',0), 'work_tools':counts.get('tools',0),
            'work_review_tokens':task.get('usage', {}).get('reviewer', {}).get('tokens',0),
            'work_iterations':len(task.get('checkpoints',[])),
            'work_seconds':seconds if seconds is not None else consumed.get('working_seconds',task.get('active_work_seconds',0))}
    return used


def guard(task, *, additions=None, seconds=None):
    if not active(task): return
    from .providers import BudgetError
    used = usage(task, seconds=seconds)
    for key, limit in effective(task).items():
        value = used[key] + (additions or {}).get(key,0)
        if limit is not None and value > limit:
            task['limit_hit']={'key':key,'used':used[key],'allowed':limit,'remaining':max(0,limit-used[key])}
            raise BudgetError('The selected '+key.removeprefix('work_')+' budget is exhausted. Increase this chat budget to continue saved work.',key,used[key],limit)
