"""Non-secret route evidence and measurements for signed request reports."""
import re
from .metrics import number
from .served_identity import safe_model


def route_metadata(config, local=False):
    # A catalog's owned_by/provider can be the model publisher. Only the
    # configured OmniRoute namespace establishes a routing provider here.
    if local:
        return dict(request_gateway='local', request_provider='local')
    if config.get('gateway') == 'omniroute' and config.get('gateway_type', 'omniroute') == 'omniroute':
        model = safe_model(config.get('model')) or ''
        prefix = model.split('/', 1)[0].lower() if '/' in model else 'unknown'
        if prefix in {'auto', 'router', 'combo', 'combos', 'automatic'}:
            prefix = 'unknown'
        return dict(request_gateway='omniroute', request_provider={'oc': 'opencode', 'kr': 'kiro'}.get(prefix, prefix))
    return dict(request_gateway='openai-compatible', request_provider='unknown')


def route_name(value):
    return value if isinstance(value, str) and re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', value) else 'unknown'


def event_health(row, share_models=False):
    status = row.get('status')
    outcome = status if status in {'responded', 'failed', 'cancelled'} else 'unknown'
    result = dict(version=1, outcome=outcome)
    seconds = number(row.get('seconds'))
    if outcome != 'unknown' and seconds is not None and seconds <= 1_000_000:
        result['duration_ms'] = round(seconds * 1000)
    if outcome == 'failed':
        result['failure_category'] = route_name(row.get('failure_category'))
    result['recovery'] = row.get('purpose') == 'recovery'
    if share_models:
        result['gateway'] = route_name(row.get('request_gateway'))
        result['provider'] = route_name(row.get('request_provider'))
    return result
