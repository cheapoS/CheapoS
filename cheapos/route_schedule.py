"""Paced route discovery. Counts are telemetry, never lifetime retry locks."""
import time

BATCH_SIZE = 4
ROUND_SECONDS = 30
REJECTED_SECONDS = 300


def begin(task, role, now=None):
    now = time.time() if now is None else now
    rounds = task.setdefault('route_schedule', {})
    state = rounds.setdefault(role, {'started_at': now, 'probes': 0, 'round': 1})
    if now >= state['started_at'] + ROUND_SECONDS:
        state.update(started_at=now, probes=0, round=state['round'] + 1)
    return state


def retry_at(state):
    return state['started_at'] + ROUND_SECONDS


def rejected(record, now=None):
    now = time.time() if now is None else now
    # Legacy exclusions without an expiry get one fresh opportunity.
    return bool(record and record.get('retry_at', 0) > now)
