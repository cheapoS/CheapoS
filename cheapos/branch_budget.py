"""Cumulative branch accounting with conservative, renewable time reservations.

The controller retains task usage/counters across items. Persist includes the
whole task. A crash charges the last open segment (at most 30 seconds ahead of
its last heartbeat); only this live ledger can refund unused reserved seconds.
Wall clock timestamps are never used for allowances. The watchdog only accounts
and cancels; it cannot dispatch work or resume a run.
"""
import math
import json
import threading
import time
import uuid
from .measurement import enabled as measuring


class LimitExceeded(ValueError):
    def __init__(self, key, used, allowed):
        self.key, self.used, self.allowed = key, used, allowed
        super().__init__('Run limit reached: %s (%s / %s)' % (key, used, allowed))


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid cumulative usage counter')
    return value


class Ledger:
    def __init__(self, runtime, persist, lock=None, clock=None, segment_seconds=30):
        if not 0 < segment_seconds <= 30:
            raise ValueError('Time reservation must be at most 30 seconds')
        self.runtime = runtime
        self.task = runtime.task
        self.run = self.task['branch_run']
        self.persist = persist
        self.lock = lock or threading.RLock()
        self.clock = clock or time.monotonic
        self.segment = segment_seconds
        self.closed = threading.Event()
        self.thread = None
        self.active = False
        self.start = None
        self.last_elapsed = 0
        self.last_saved = 0
        self.base = 0
        self.token = uuid.uuid4().hex
        self.data = self.run.setdefault('budget_ledger', {'version': 1, 'request_ids': [], 'observed': {}})
        self.run.setdefault('consumption', {})

    def _sync(self):
        consumed = self.run['consumption']
        observed = self.data['observed']
        before = json.dumps([consumed, self.data], sort_keys=True)
        for name in ('worker_turns', 'tool_actions'):
            current = _number(self.task.get(name, 0))
            previous = observed.get(name)
            delta = current - previous if previous is not None and current >= previous else current
            consumed[name] = max(_number(consumed.get(name, 0)), current) if previous is None else _number(consumed.get(name, 0)) + delta
            observed[name] = current
        # Stable IDs survive the bounded request_metrics preview history. Pending
        # and uncertain requests count too; no retry is made free by a restart.
        seen = set(self.data['request_ids'])
        seen.update(str(r['id']) for r in self.task.get('request_metrics', []) if r.get('id'))
        self.data['request_ids'] = sorted(seen)
        consumed['requests'] = max(_number(consumed.get('requests', 0)), len(seen), _number(self.task.get('worker_turns', 0)) + _number(self.task.get('review_count', 0)) if self.task.get('demo') else 0)
        usage = self.task.get('usage', {})
        # Existing usage accounting already includes reservations and refunds only
        # reconciled known usage. Preserve it, instead of charging the same cost twice.
        for name, current in (('dollars', usage.get('cost', 0)), ('reviewer_tokens', usage.get('reviewer', {}).get('tokens', 0))):
            current = _number(current)
            prior = observed.get(name)
            consumed[name] = max(_number(consumed.get(name, 0)), current) if prior is None else max(0, _number(consumed.get(name, 0)) + current - prior)
            observed[name] = current
        consumed['worker_tokens'] = _number(usage.get('worker', {}).get('tokens', 0))
        consumed['check_seconds'] = sum(_number(check.get('duration', 0)) for check in self.task.get('checks', []))
        self.data['usage'] = {role: dict(usage.get(role, {})) for role in ('worker', 'reviewer', 'planner', 'coordinator')}
        self.data['uncertain_requests'] = usage.get('uncertain_requests', 0)
        return before != json.dumps([consumed, self.data], sort_keys=True)

    def _elapsed(self):
        value = _number(self.clock())
        # Even a faulty/injected monotonic clock cannot refund already seen time.
        self.last_elapsed = max(self.last_elapsed, value - self.start, 0)
        return self.last_elapsed

    def _check(self, next_request=False, next_action=False, next_worker_turn=False):
        from .work_budgets import guard
        guard(self.task, seconds=self.base + self._elapsed() if self.active else self.run['consumption'].get('working_seconds',0))
        limits = self.run['limits']
        additions = {'requests': int(next_request), 'tool_actions': int(next_action), 'worker_turns': int(next_worker_turn)}
        for key in ('dollars', 'requests', 'worker_turns', 'tool_actions', 'reviewer_tokens'):
            used = self.run['consumption'].get(key, 0) + additions.get(key, 0)
            if key in limits and used > limits[key] and (key == 'dollars' or not measuring(self.task)):
                raise LimitExceeded(key, used, limits[key])
        actual = self.base + self._elapsed() if self.active else self.run['consumption'].get('working_seconds', 0)
        if not measuring(self.task) and actual >= limits['working_seconds']:
            raise LimitExceeded('working_seconds', actual, limits['working_seconds'])

    def _reserve(self):
        elapsed = self._elapsed()
        amount = self.base + elapsed + self.segment
        if not measuring(self.task): amount = min(self.run['limits']['working_seconds'], amount)
        self.run['consumption']['working_seconds'] = amount
        self.data['active_segment'] = {'owner': self.token, 'reserved_through_seconds': amount, 'measured_seconds': self.base + elapsed}
        self.last_saved = elapsed
        self.persist()

    def begin(self, start_watchdog=True):
        with self.lock:
            if self.active:
                return
            if self.closed.is_set():
                raise ValueError('Closed ledger cannot restart; construct one for Resume')
            self._sync()
            self.base = _number(self.run['consumption'].get('working_seconds', 0))
            self.start = self.clock()
            self.last_elapsed = 0
            self.active = True
            try:
                self._check()
                self._reserve()
            except Exception:
                self.active = False
                self.runtime.stop.set()
                raise
            if start_watchdog and self.thread is None:
                self.thread = threading.Thread(target=self._watch, daemon=True, name='cheapos-run-budget')
                self.thread.start()

    resume = begin

    def guard(self, next_request=False, next_action=False, next_worker_turn=False):
        with self.lock:
            changed = self._sync()
            try:
                self._check(next_request, next_action, next_worker_turn)
                if self.active and self._elapsed() - self.last_saved >= self.segment / 2:
                    self._reserve()
                elif changed:
                    self.persist()
            except Exception as error:
                self.runtime.branch_budget_error = error
                self.runtime.stop.set()
                self.persist()
                raise

    def suspend(self):
        """Only for confirmed operator wait/pause; cooldown keeps counting."""
        with self.lock:
            self._sync()
            if self.active:
                self.run['consumption']['working_seconds'] = self.base + self._elapsed()
                self.data.pop('active_segment', None)
                self.active = False
            self.persist()

    def end(self):
        self.closed.set()
        self.suspend()
        # Do not join while holding the controller lock; the daemon may be waiting
        # to acquire it. closed prevents any subsequent work or renewal.

    def _watch(self):
        while not self.closed.wait(min(self.segment / 2, 1)):
            if self.closed.is_set():
                return
            try:
                with self.lock:
                    if self.closed.is_set() or not self.active:
                        continue
                    self.guard()
            except Exception as error:
                self.runtime.branch_budget_error = error
                self.runtime.stop.set()
                return
