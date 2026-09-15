"""Deliberate transport compatibility; no probing, model upgrades or JSON repair."""
import hashlib
import json

VERSION = 1


def choice(config, role, purpose, tools, streaming):
    # Observed in the ten-task trial. This is a route/role/tool workaround,
    # not evidence that the entire Gemini family cannot stream.
    known = (config.get('gateway') == 'omniroute'
             and config.get('model') == 'openrouter/google/gemini-2.5-flash'
             and role == 'reviewer' and bool(tools) and purpose != 'probe')
    planning = (purpose == 'branch_planning' and bool(tools))
    return 'json' if known or planning or not streaming else 'sse'


def retry_key(config, role, purpose):
    # One transport retry per route + role + purpose for the lifetime of a task.
    # Resume, reviewer reinvocation and process restart cannot replenish it.
    value = [VERSION, config.get('base_url'), config.get('model'), role, purpose or 'work']
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def json_preference(task, config, role, purpose):
    """Reuse a proven fallback for this task's exact route and connection.

    Old tasks can recover the evidence from their accounted request history.
    Failed/cancelled JSON attempts never establish compatibility.
    """
    key = retry_key(config, role, purpose)
    revision = (config.get('access_binding') or {}).get('connection_revision')
    saved = task.get('transport_json_routes', {}).get(key)
    if saved and saved.get('connection_revision') == revision:
        return saved
    original = task.get('transport_retries', {}).get(key)
    if not original:
        return None
    for record in reversed(task.get('request_metrics', [])):
        if (record.get('retry_of') == original and record.get('status') == 'responded'
                and record.get('transport') == 'json' and record.get('dispatched')
                and record.get('model') == config.get('model') and record.get('role') == role
                and record.get('purpose') == (purpose or 'work')
                and (record.get('dispatch_scope') or {}).get('connection_revision') == revision):
            return {'request_id': record['id'], 'connection_revision': revision}
    return None


def eligible(error, record):
    return (getattr(error, 'code', None) in {'streaming_unsupported', 'empty_response'}
            and record.get('dispatched') and record.get('transport') == 'sse')
