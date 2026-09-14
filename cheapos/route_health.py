"""Small, nonsecret capability/failure contracts; no network or response parser."""
import hashlib
import json

PROBE_VERSION = 2
PROBE_MARKER = 'cheapos-tool-check-v2'
METADATA_FIELDS = ('context_length', 'max_output_tokens', 'tool_calling', 'reasoning')


def probe_identity(endpoint, model, connection_revision):
    value = {'version': PROBE_VERSION, 'transport_contract': 1, 'endpoint': endpoint.replace('localhost', '127.0.0.1').rstrip('/'),
             'model': model['id'], 'connection_revision': connection_revision,
             'requirements': {'tool': 'routing_ready', 'marker': PROBE_MARKER},
             'metadata': {k: model.get(k) for k in METADATA_FIELDS}}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def classify(error, context=None):
    """Only stable codes and trusted context; never retain arbitrary error text."""
    context = context or {}
    code = getattr(error, 'code', None)
    scope = getattr(error, 'scope', None)
    if isinstance(error, InterruptedError) or code in {'cancelled', 'user_paused'}:
        kind, scope, retry, impact, action = 'cancelled', 'request', False, False, 'Resume only when requested.'
    elif code in {'review_identity_conflict', 'review_identity_unknown'}:
        kind, scope, retry, impact, action = 'capability_mismatch', 'request', False, False, 'Choose a verified different reviewer before continuing.'
    elif code in {'http_401', 'http_403', 'client_key_rejected', 'http_402'}:
        kind, scope, retry, impact, action = 'credential_access', 'connection', False, False, 'Inspect access for this connection in Models.'
    elif context.get('caller_error') or code in {'http_400', 'http_422', 'invalid_request'} or (code == 'http_404' and context.get('endpoint_invalid')):
        kind, scope, retry, impact, action = 'malformed_request', 'request', False, False, 'Correct the request or endpoint before retrying.'
    elif code == 'gateway_cooldown' or code == 'http_429':
        kind, retry, impact, action = 'rate_limit_quota', True, False, 'Wait for the reported reset, or inspect quota if its time is unknown.'
        scope = scope if scope in {'model', 'provider', 'account', 'connection'} else 'model'
    elif code == 'http_404':
        kind, scope, retry, impact, action = 'unavailable_route', 'model', True, False, 'Refresh the catalog or select another authorized route.'
    elif code in {'unsupported_tool', 'probe_failed', 'model_capability'}:
        kind, scope, retry, impact, action = 'capability_mismatch', 'model', True, True, 'Select another eligible tool-capable model.'
    elif code in {'http_408', 'http_500', 'http_502', 'http_503', 'http_504', 'model_connection', 'model_timeout', 'stream_timeout', 'stream_error', 'stream_interrupted'}:
        kind, scope, retry, impact, action = 'transient_provider', 'model', True, False, 'Retry after backoff or use another authorized route.'
    else:
        kind, scope, retry, impact, action = 'invalid_response', 'model', True, True, 'Inspect the incomplete or invalid response; no partial tools were executed.'
    return {'category': kind, 'scope': scope, 'retry': retry, 'quality_impact': impact, 'action': action}


def metadata_facts(models, previous, observed_at):
    old = {m['id']: m for m in previous}
    result = []
    for original in models:
        model = dict(original)
        changes = [key for key in METADATA_FIELDS if model['id'] in old
                   and old[model['id']].get(key) != model.get(key)]
        model['metadata_evidence'] = {'source': 'gateway_catalog', 'observed_at': observed_at,
                                       'changes': changes, 'stale': False}
        result.append(model)
    return result


def validate_probe(message, parse_call):
    """Require the explicit marker using the existing application tool parser."""
    from .providers import ProviderError
    calls = message.get('tool_calls', [])
    if not isinstance(calls, list) or len(calls) != 1:
        raise ProviderError('Tool marker response missing', code='probe_failed')
    try:
        name, args = parse_call(calls[0])
    except ValueError:
        raise ProviderError('Tool marker arguments invalid', code='invalid_tool_arguments') from None
    if name != 'routing_ready' or args != {'marker': PROBE_MARKER}:
        raise ProviderError('Tool marker response mismatched', code='probe_failed')
