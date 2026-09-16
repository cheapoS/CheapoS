"""Operator-controlled agent role mapping.

Value type that binds the three cheapoS roles (planner, worker, reviewer)
to operator-selected model references from a configured candidate set.
Pure and deterministic: no network, storage, or side effects.
"""

import hashlib
import json

ROLES = ('planner', 'worker', 'reviewer')


class RoleMapping(object):
    """Selected planner/worker/reviewer models plus their candidate sets.

    Each role field stores a configured model reference (string) or None.
    """

    def __init__(self, candidates=None):
        normalized = {}
        for role in ROLES:
            candidate_set = (candidates or {}).get(role)
            if candidate_set is None:
                candidate_set = ()
            if not isinstance(candidate_set, (set, frozenset, list, tuple)):
                raise ValueError('Candidates for %s must be a collection of model references' % role)
            cleaned = []
            for model_id in candidate_set:
                if not isinstance(model_id, str) or not model_id:
                    raise ValueError('Model references must be non-empty strings')
                cleaned.append(model_id)
            if len(set(cleaned)) != len(cleaned):
                raise ValueError('Duplicate model references for %s' % role)
            normalized[role] = frozenset(cleaned)
        extra = set(candidates or ()) - set(ROLES)
        if extra:
            raise ValueError('Unknown role(s): %s' % ', '.join(sorted(extra)))
        self._candidates = normalized
        self._selected = {role: None for role in ROLES}

    @property
    def planner(self):
        return self._selected['planner']

    @property
    def worker(self):
        return self._selected['worker']

    @property
    def reviewer(self):
        return self._selected['reviewer']

    def candidates(self, role):
        self._check_role(role)
        return self._candidates[role]

    def get(self, role):
        self._check_role(role)
        return self._selected[role]

    def assign(self, role, model_id):
        self._check_role(role)
        if not isinstance(model_id, str) or not model_id:
            raise ValueError('Model reference must be a non-empty string')
        if model_id not in self._candidates[role]:
            raise ValueError('%r is not a configured candidate for %s' % (model_id, role))
        if role == 'worker':
            # Hard block: the worker must be a different model from the
            # planner and the reviewer. Planner and reviewer may coincide.
            for other in ('planner', 'reviewer'):
                if self._selected[other] == model_id:
                    raise ValueError(
                        '%r is already mapped to %s; choose a different worker' % (model_id, other))
        else:
            # Hard block (contrapositive): if assigning to planner/reviewer,
            # it cannot be the worker.
            if self._selected['worker'] == model_id:
                raise ValueError(
                    '%r is already mapped to worker; choose a different %s' % (model_id, role))

        self._selected[role] = model_id
        return self

    def digest(self):
        payload = json.dumps(
            {role: self._selected[role] for role in ROLES if self._selected[role] is not None},
            sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def canonical(self):
        """Mapped assignments only: unset roles are omitted (None)."""
        return {role: self._selected[role] for role in ROLES if self._selected[role] is not None}

    def __eq__(self, other):
        if not isinstance(other, RoleMapping):
            return NotImplemented
        return self._selected == other._selected and self._candidates == other._candidates

    def __repr__(self):
        return 'RoleMapping(%r)' % self.canonical()

    def _check_role(self, role):
        if role not in ROLES:
            raise ValueError('Unknown role: %r' % (role,))