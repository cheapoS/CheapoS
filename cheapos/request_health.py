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


def historical_route_metadata(record, connections):
    """Recover only a legacy request's exact captured dispatch connection.

    A served model can omit its routing namespace. Current role selections and
    endpoint names are not historical evidence; never consult them here.
    """
    if 'request_gateway' in record or 'request_provider' in record:
        return {}  # Preserve explicit dispatch-time metadata, including unknown.
    scope = record.get('dispatch_scope')
    if record.get('access_class') == 'local' and not scope:
        return route_metadata({}, local=True)
    if not isinstance(scope, dict) or not isinstance(connections, list):
        return {}
    requested = safe_model(record.get('requested_model', record.get('model')))
    if (not requested or scope.get('model') != requested or scope.get('role') != record.get('role')
            or not isinstance(scope.get('base_url'), str) or not scope['base_url']
            or not isinstance(scope.get('connection_revision'), str) or not scope['connection_revision']
            or record.get('context_base_url', scope['base_url']) != scope['base_url']):
        return {}
    matches = [c for c in connections if isinstance(c, dict)
               and c.get('base_url') == scope['base_url']
               and c.get('connection_revision') == scope['connection_revision']]
    if len(matches) != 1 or matches[0].get('gateway_type') != 'omniroute':
        return {}
    return route_metadata({'gateway': 'omniroute', 'model': requested})


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
