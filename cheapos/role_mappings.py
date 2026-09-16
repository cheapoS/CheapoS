"""Durable operator/user agent role mappings.

Settings store the *defaults* for the three cheapoS roles (planner, worker,
reviewer). Chat work setup captures *explicit* selections per project that
override the defaults for that project only. Resolution prefers explicit over
defaults role by role and reports, per role, whether the effective choice is
user-selected (explicit) or operator-selected (default).

Hard block: the worker must be a different model from the planner and the
reviewer. Planner and reviewer may share a model (that is not independent
review; the UI says so).

Storage is role-mappings.json under the Store root, written atomically with
the same write_json used for preferences. Corrupt or legacy content degrades
to empty defaults instead of taking the app down.
"""

import json
from pathlib import Path

from .agents import ROLES
from .storage import write_json


def _clean_roles(section):
    if not isinstance(section, dict):
        return {}
    return {role: model for role, model in section.items()
            if role in ROLES and isinstance(model, str) and model}


def _clean_data(data):
    """Tolerate legacy flat files, non-dicts, and junk without raising."""
    if not isinstance(data, dict):
        return {'defaults': {}, 'projects': {}}
    if 'defaults' in data or 'projects' in data:
        defaults = _clean_roles(data.get('defaults'))
        projects = {}
        saved_projects = data.get('projects')
        if isinstance(saved_projects, dict):
            for project, section in saved_projects.items():
                if not isinstance(project, str) or not project:
                    continue
                clean = _clean_roles(section)
                if clean:
                    projects[project] = clean
        return {'defaults': defaults, 'projects': projects}
    # Legacy flat file: promote valid role selections to defaults.
    return {'defaults': _clean_roles(data), 'projects': {}}


def load(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'defaults': {}, 'projects': {}}
    data = _clean_data(data)
    if data == {'defaults': {}, 'projects': {}} and path.exists():
        return data
    return data


def save(path, data):
    write_json(path, _clean_data(data))
    return _clean_data(data)


def worker_collision(mapping):
    """Hard block: worker must differ from planner and reviewer."""
    worker = mapping.get('worker')
    if not worker:
        return None
    for other in ('planner', 'reviewer'):
        if mapping.get(other) == worker:
            return other
    return None


def effective(data, project=None):
    """Resolve the effective role mapping for a project.

    Returns {'mapping', 'roles', 'source', 'missing', 'error', 'reason'}.
    'roles' maps each role to 'user' (explicit) or 'operator' (default).
    """
    data = _clean_data(data)
    defaults = data['defaults']
    explicit = data['projects'].get(project, {}) if isinstance(project, str) else {}
    mapping, roles = {}, {}
    for role in ROLES:
        if role in explicit:
            mapping[role], roles[role] = explicit[role], 'user'
        elif role in defaults:
            mapping[role], roles[role] = defaults[role], 'operator'
    missing = [role for role in ROLES if role not in mapping]
    collision = worker_collision(mapping)
    if missing:
        return {'mapping': mapping, 'roles': roles,
                'source': 'operator',
                'missing': missing,
                'error': 'incomplete',
                'reason': 'Choose the %s model(s) in settings before planning.'
                          % ', '.join(missing)}
    if collision:
        return {'mapping': mapping, 'roles': roles,
                'source': 'user' if any(r == 'user' for r in roles.values()) else 'operator',
                'missing': [],
                'error': 'worker-duplicate',
                'reason': 'The worker must use a different model from the %s' % collision}
    return {'mapping': mapping, 'roles': roles,
            'source': 'user' if any(r == 'user' for r in roles.values()) else 'operator',
            'missing': [], 'error': None, 'reason': None}


def validate(data, project=None):
    """Raise ValueError on an incomplete/invalid effective mapping."""
    result = effective(data, project)
    if result['error'] == 'incomplete':
        raise ValueError('Choose the %s model(s) in settings before planning'
                         % ', '.join(result['missing']))
    if result['error'] == 'worker-duplicate':
        raise ValueError('The worker must use a different model from the %s'
                         % result['reason'])
    return result