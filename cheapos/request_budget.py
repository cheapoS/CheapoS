"""One output allowance for context headroom, reservations and wire fields."""
import math
import json


def resolve(task, config, model=None, *, messages=None, tools=None, role=None):
    limits = task['limits']
    choice = limits.get('response_tokens', limits['output_tokens'])
    model = model or {}
    capacity = model.get('max_output_tokens')
    if type(capacity) is not int or capacity <= 0 or model.get('metadata_evidence', {}).get('stale'):
        capacity = None
    automatic = choice == 'automatic'
    requested = (capacity or limits['output_tokens']) if automatic else choice
    # Unknown capacity is a conservative estimate, never an invented capacity.
    if automatic and capacity is None:
        previous = next((r for r in reversed(task.get('request_metrics', [])) if r.get('model') == config.get('model') and r.get('error_code') == 'output_limit'), None)
        if previous and type(previous.get('requested_output_limit')) is int:
            requested = max(requested, previous['requested_output_limit'] * 2)
    output = min(requested, capacity) if capacity else requested
    constraints = []
    if messages is not None:
        prompt = len(json.dumps({'messages':messages,'tools':tools or []},ensure_ascii=False).encode()) + 1024
        from .work_budgets import active, effective
        review = effective(task)['work_review_tokens'] if active(task) else None
        if role == 'reviewer' and review is not None:
            allowed = max(0, review - task.get('usage',{}).get('reviewer',{}).get('tokens',0) - prompt)
            if allowed < output: constraints.append('review_budget')
            output = min(output, allowed)
        if config.get('output_rate',0) > 0 and 'dollars' in limits:
            remaining = limits['dollars'] - task.get('usage',{}).get('cost',0)
            allowed = max(0, math.floor((remaining - prompt * config.get('input_rate',0) / 1_000_000) * 1_000_000 / config['output_rate']))
            if allowed < output: constraints.append('spending')
            output = min(output, allowed)
    return {'tokens':output,'requested':choice,'capacity_tokens':capacity,'constraints':constraints,
            'source':'catalog' if automatic and capacity else 'automatic_estimate' if automatic else 'operator',
            'wire':'explicit', 'automatic':automatic}


def verification(task, command):
    """Adaptive deadlines use this command's observations, never a work ceiling."""
    choice = task['limits'].get('verification_seconds')
    if choice != 'automatic': return choice
    allowance = task['limits'].get('check_seconds', 90)
    for check in task.get('checks', []):
        if check.get('command') != command: continue
        if check.get('outcome') == 'process_timeout':
            allowance = max(allowance, (check.get('allowed_seconds') or check.get('duration') or allowance) * 2)
        elif check.get('passed'):
            allowance = max(allowance, math.ceil(check.get('duration',0) * 2))
    return allowance
