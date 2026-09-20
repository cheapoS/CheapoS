"""Metadata-only repair of already accepted Club usage, never a usage upload."""
import hashlib
import json
import time
import uuid

from .request_health import route_name


def backfill_routes(club, lifetime):
    """Called under the Club lock after normal usage sync and outbox recovery.

    Probe with opaque IDs first so a pre-consent model/route never leaves the
    installation. Only the server's owned, receipt-backed matches can be amended.
    A separate processed map must not make these IDs eligible for usage uploads.
    """
    state = club.state
    if (not state.get('sync_enabled') or not state.get('share_models')
            or not state.get('identity') or state.get('pending') or state.get('revoking')):
        return 0
    if time.monotonic() < getattr(club, '_route_backfill_retry_at', 0):
        return 0
    scope = [state['installation_id'], state['pairing_id'], state['identity'].get('account_id')]
    if state.get('route_backfill_scope') != scope:
        state['route_backfill_scope'] = scope
        state['route_backfill_processed'] = {}
    processed = state.setdefault('route_backfill_processed', {})
    baseline = set(state['baseline'])
    candidates = {}
    for row in lifetime.raw_requests():
        rid = row['request_id']
        if rid not in baseline:
            continue  # Normal signed event corrections already handle these.
        gateway, provider = (route_name(row.get(k)) for k in ('request_gateway', 'request_provider'))
        if 'unknown' in (gateway, provider):
            continue
        event_id = str(uuid.uuid5(uuid.UUID(state['installation_id']), rid))
        correction = dict(event_id=event_id, gateway=gateway, provider=provider)
        fingerprint = hashlib.sha256(json.dumps(correction, sort_keys=True).encode()).hexdigest()
        if processed.get(rid) != fingerprint:
            candidates[event_id] = (rid, fingerprint, correction)
        if len(candidates) == 500:  # Bounded signed request and response sizes.
            break
    if not candidates:
        return 0
    try:
        result = club._call('route_history', event_ids=list(candidates))
        if not isinstance(result, dict):
            raise ValueError('Club history lookup returned an invalid response.')
        accepted = result.get('event_ids')
        if (result.get('status') != 'route_history' or not isinstance(accepted, list)
                or any(not isinstance(eid, str) or eid not in candidates for eid in accepted)
                or len(set(accepted)) != len(accepted)):
            raise ValueError('Club history lookup did not match the requested records.')
        accepted = set(accepted)
        # Negative lookups disclose no model or route and do not create usage.
        for eid, (rid, fingerprint, _) in candidates.items():
            if eid not in accepted:
                processed[rid] = fingerprint
        corrections, fingerprints = [], {}
        for eid, (rid, fingerprint, correction) in candidates.items():
            if eid in accepted:
                corrections.append(correction)
                fingerprints[rid] = fingerprint
                if len(corrections) == 100:
                    break
        if corrections:
            club._queue('sync', _route_fingerprints=fingerprints, events=[], route_corrections=corrections)
            club._flush()
        else:
            club._save()
        state.pop('route_backfill_error', None)
        return len(corrections)
    except ValueError as error:
        # Discovery failures (including an older server) do not block usage.
        # An uncertain mutation keeps its exact envelope for ordered replay.
        state['route_backfill_error'] = str(error)
        club._route_backfill_retry_at = time.monotonic() + 300
        club._save()
        return 0
