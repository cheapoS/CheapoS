"""One output allowance for context headroom, reservations and wire fields."""
import math


def resolve(task, config, model=None):
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
    return {'tokens':output,'requested':choice,'capacity_tokens':capacity,
            'source':'catalog' if automatic and capacity else 'automatic_estimate' if automatic else 'operator',
            'wire':'explicit', 'automatic':automatic}
