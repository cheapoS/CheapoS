"""Route-scoped context planning. Unknown capacity is not a hidden small cap."""
import json
import math


def payload_bytes(messages, tools):
    return len(json.dumps({'messages': messages, 'tools': tools}, ensure_ascii=False).encode())


def decision(task, messages, tools, config, model=None, role=None):
    model = model or {}
    capacity = model.get('context_length')
    if type(capacity) is not int or capacity <= 0 or model.get('metadata_evidence', {}).get('stale'):
        capacity = None
    amount = payload_bytes(messages, tools)
    samples = []
    for record in task.get('request_metrics', [])[-100:]:
        scope = record.get('dispatch_scope', {})
        if (record.get('requested_model', record.get('model')) != config.get('model')
                or scope.get('base_url', record.get('context_base_url')) != config.get('base_url')):
            continue
        tokens, byte_count = record.get('input_tokens'), record.get('context_payload_bytes')
        if type(tokens) is int and tokens > 0 and type(byte_count) is int and byte_count > 0:
            samples.append(tokens / byte_count)
    # Approximation only; calibrate against reported usage on this exact route.
    ratio = max(samples[-8:]) * 1.1 if samples else 1 / 3
    estimate = math.ceil(amount * ratio)
    from .request_budget import resolve
    output = resolve(task, config, model, messages=messages, tools=tools, role=role or task.get('active_role'))['tokens']
    margin = math.ceil(capacity * .05) if capacity else None
    available = max(0, capacity - output - margin) if capacity else None
    return {'capacity_tokens': capacity, 'capacity_source': 'gateway_catalog' if capacity else 'unknown',
            'estimated_input_tokens': estimate, 'estimate_source': 'route_usage_calibrated' if samples else 'utf8_estimate',
            'output_reserve_tokens': output, 'margin_tokens': margin, 'payload_bytes': amount,
            'compact': available is not None and estimate > available,
            'target_characters': max(2000, int(available * .65 / ratio)) if available is not None else None,
            'policy': 'Retain context when capacity is unknown; no fixed character cutoff. Estimates are not exact tokenizer counts.'}


def context_rejection(error):
    text = str(error).lower()
    return getattr(error, 'code', None) in {'context_length_exceeded', 'context_window_exceeded'} or any(
        phrase in text for phrase in ('maximum context length', 'context window exceeded', 'context length exceeded', 'input is too long'))
