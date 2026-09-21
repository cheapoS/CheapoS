"""Signed terminal request facts, independent of token reconciliation."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from .request_health import event_health
from .served_identity import safe_model


def collect_attempts(manager, rows):
    attempts, fingerprints = [], {}
    baseline = set(manager.state['baseline'])
    sent = manager.state.get('attempts_sent', {})
    for row in rows:
        rid = row['request_id']
        # raw_requests contains only dispatched, non-synthetic journal records.
        # An unfinished request is not evidence of either success or failure.
        if rid in baseline or row.get('status') not in {'responded', 'failed', 'cancelled'}:
            continue
        try:
            stamp = datetime.strptime(row['date'], '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            continue
        if stamp > datetime.now(timezone.utc):
            continue
        fact = dict(event_id=str(uuid.uuid5(uuid.UUID(manager.state['installation_id']), rid)),
                    requested_at=stamp.strftime('%Y-%m-%dT00:00:00Z'),
                    request_health=event_health(row, bool(manager.state.get('share_models'))))
        role = row.get('role')
        if role in {'worker', 'reviewer', 'planner', 'coordinator', 'unknown'}:
            fact['role'] = role
        if manager.state.get('share_models'):
            model = safe_model(row.get('served_model') or row.get('requested_model'))
            if model:
                fact['model_name'] = model[:160]
        fingerprint = hashlib.sha256(json.dumps(fact, sort_keys=True).encode()).hexdigest()
        if sent.get(rid) == fingerprint:
            continue
        attempts.append(fact)
        fingerprints[rid] = fingerprint
        if len(attempts) == 40:
            break
    if attempts:
        # Older services may ignore unknown sync fields. Do not enqueue these
        # facts until both ingestion and explicit acknowledgment are supported.
        try:
            status = manager._call('status')
        except (ValueError, OSError):
            return [], {}
        if 'request_attempts_v1' not in (status.get('capabilities') or []):
            return [], {}
    return attempts, fingerprints
