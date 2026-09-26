"""Engine adapters for the single future-chat defaults document."""
import copy
import json
import uuid
from pathlib import Path

from .settings_store import SettingsStore, canonical_project
from .routing import execution_from, local_config
from .providers import validate_provider
from . import access_policy



def _load_legacy_preferences(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        preferences = json.loads(path.read_text())
    except ValueError as error:
        raise ValueError('Saved preferences.json is invalid; repair it before migrating settings') from error
    if not isinstance(preferences, dict):
        raise ValueError('Saved preferences.json must contain an object')
    return preferences


def _normalize_section(group, section, validator, initial, notices):
    if not isinstance(section, dict):
        notices.append({'field': group, 'message': f'Legacy {group} were invalid; review the migrated defaults.'})
        section = {}
    valid = dict(initial)
    for key, value in section.items():
        try:
            allowed = set(validator(initial)) | ({'uncapped_work'} if group == 'limits' else set())
            if key not in allowed:
                raise ValueError('Unknown field')
            validator({**valid, key: value})
            valid[key] = value
        except (ValueError, TypeError):
            notices.append({'field': f'{group}.{key}', 'message': f'Legacy {group}.{key} needs review; its invalid value was not applied.'})
    return validator(valid)


def initialize(engine):
    from .engine import limits_from
    from .role_mappings import load
    store = SettingsStore(engine.store.root, limits_validator=limits_from,
        execution_validator=execution_from, provider_validator=validate_provider, lock=engine.lock)
    if not store.path.exists():
        path = engine.store.root / 'preferences.json'
        preferences = _load_legacy_preferences(path)
        fresh_install = (not path.exists() and not (engine.store.root / 'config.json').exists()
                         and not (engine.store.root / 'role-mappings.json').exists() and not any(engine.config.values()))
        notices = []
        normalized = {}
        for group, validator, initial in (('execution', execution_from, {}), ('limits', limits_from, {'dollars': 0})):
            normalized[group] = _normalize_section(group, preferences.get(group, {}), validator, initial, notices)
        if fresh_install:
            normalized['execution']['mode'] = 'remote'
            from .work_budgets import FIELDS
            normalized['limits'].update(work_policy_version=2, **{key:None for key in FIELDS}, response_tokens='automatic', verification_seconds='automatic', request_seconds='automatic')
        store.initialize(normalized, load(engine.store.root / 'role-mappings.json'), engine.config, notices=notices, fresh_install=fresh_install)
    engine.settings_store = store

def project_key(engine, project):
    key = canonical_project(project)
    registered = {canonical_project(p['path']) for p in engine.projects(include_hidden=True)}
    if key not in registered:
        raise ValueError('Project not found; open it before changing project defaults')
    return key


def preferences(engine, values=None):
    if values is None:
        return engine.settings_store.legacy_preferences()
    if not isinstance(values, dict) or not values or set(values) - {'limits', 'execution'}:
        raise ValueError('Provide limits or execution preferences')
    patch = {}
    for group, section in values.items():
        if not isinstance(section, dict):
            raise ValueError(f'Provide valid {group} preferences')
        patch.update({f'{group}.{key}': value for key, value in section.items()})
    with engine.lock:
        current = engine.settings_store.view()
        engine.settings_store.save(patch, expected_revision=current['revision'], operation_id=uuid.uuid4().hex)
        return engine.settings_store.legacy_preferences()


def role_mappings(engine, values=None):
    if values is None:
        return engine.settings_store.legacy_role_mappings()
    if not isinstance(values, dict) or not values or set(values) - {'defaults', 'projects'}:
        raise ValueError('Provide defaults or one project role mapping')
    # One legacy request may no longer mutate independent scopes.
    if len(values) != 1:
        raise ValueError('Save one settings scope at a time')
    project = None
    if 'projects' in values:
        if not isinstance(values['projects'], dict) or len(values['projects']) != 1:
            raise ValueError('Save one named project at a time')
        project, choices = next(iter(values['projects'].items()))
        project = project_key(engine, project)
    else:
        choices = values['defaults']
    if not isinstance(choices, dict) or set(choices) - {'worker', 'reviewer', 'planner'}:
        raise ValueError('Provide agent role mappings')
    patch = {}
    with engine.lock:
        current = engine.settings_store.view(project)
        for role, model in choices.items():
            if not isinstance(model, str) or not model.strip():
                raise ValueError(f'Choose the {role} model')
            provider = engine.config.get(role)
            selection = {'strategy': 'only', 'model': model, 'connection_id': None}
            if provider and provider['model'] == model:
                selection.update(provider=copy.deepcopy(provider), connection_id=provider.get('connection_id'))
            patch[f'roles.{role}'] = selection
        remove = [key for key in current['overrides'] if key.startswith('roles.') and key not in patch] if project else []
        if not project:
            patch.update({f'roles.{role}': {'strategy': 'automatic'} for role in ('worker', 'reviewer', 'planner') if role not in choices})
        engine.settings_store.save(patch, remove=remove, project=project, expected_revision=current['revision'],
                             expected_parent_revision=current['parent_revision'], operation_id=uuid.uuid4().hex)
        return engine.settings_store.legacy_role_mappings()


def effective_roles(engine, project=None):
    current = engine.settings_store.view(project)['values']['roles']
    view = engine.settings_store.view(project)
    mapping = {role: choice['model'] for role, choice in current.items() if choice['strategy'] == 'only'}
    sources = {role: 'user' if view['sources'][f'roles.{role}']['scope'] == 'project' else 'operator' for role in mapping}
    return {'mapping': mapping, 'roles': sources, 'source': 'user' if 'user' in sources.values() else 'operator',
            'missing': [], 'error': None, 'reason': None, 'selections': copy.deepcopy(current)}


def capture(engine, values, project=None):
    if not isinstance(values, dict):
        raise ValueError('Provide a new chat request')
    project = project or values.get('repository') or values.get('source')
    # Creation may open a project for the first time; canonical identity is enough
    # here. The project-default mutation endpoint requires registry membership.
    project = canonical_project(project) if project else None
    settings = values.get('settings', {})
    if not isinstance(settings, dict) or set(settings) - {'overrides', 'expected_revision', 'expected_parent_revision'}:
        raise ValueError('Provide the displayed new chat setup')
    if 'settings' in values and (type(settings.get('expected_revision')) is not int or (project and type(settings.get('expected_parent_revision')) is not int)):
        raise ValueError('Review the current new chat setup before submitting; its displayed revisions are required')
    overrides = copy.deepcopy(settings.get('overrides', {}))
    if not isinstance(overrides, dict):
        raise ValueError('Provide new chat overrides')
    for group in ('execution', 'limits'):
        if group in values:
            if not isinstance(values[group], dict):
                raise ValueError(f'Provide {group} settings')
            for key, value in values[group].items():
                field = f'{group}.{key}'
                if field in overrides and overrides[field] != value:
                    raise ValueError(f'Conflicting new chat setting: {field}')
                overrides[field] = value
    with engine.lock:
        snapshot = engine.settings_store.capture(project, draft=overrides,
            expected_revision=settings.get('expected_revision'), expected_parent_revision=settings.get('expected_parent_revision'))
        for role, selection in snapshot['values']['roles'].items():
            if selection['strategy'] == 'only' and not selection.get('provider') and not selection.get('connection_id'):
                legacy = engine.config.get(role)
                if legacy and legacy.get('model') == selection['model']:
                    selection['provider'] = copy.deepcopy(legacy)
                    selection['connection_id'] = legacy.get('connection_id')
        from .branch_authorization import digest
        snapshot['model_policy'] = _capture_policy(engine, snapshot)
        snapshot['policy_values_digest'] = digest(snapshot['values'])
        return snapshot



def policy(engine, snapshot):
    from .branch_authorization import digest
    if 'model_policy' in snapshot:
        if snapshot.get('policy_values_digest') != digest(snapshot['values']):
            raise ValueError('Saved settings snapshot changed without its model policy')
        return copy.deepcopy(snapshot['model_policy'])
    # Compatibility for callers holding a pre-capture resolver result. New chat
    # creation always stores this policy before its first request.
    return _capture_policy(engine, snapshot)


def _capture_policy(engine, snapshot):
    values = snapshot['values']
    config = {}
    entries = engine.connections.capture(include=[selection.get("connection_id") for selection in values["roles"].values() if selection["strategy"] == "only"])
    if 'allowed_connections' in values:
        allowed = values['allowed_connections']
        entries = [entry for entry in entries if entry['connection_id'] in allowed]
    for role, selection in values['roles'].items():
        if selection['strategy'] == 'automatic':
            config[role] = None
            continue
        provider = copy.deepcopy(selection.get('provider'))
        connection_id = selection.get('connection_id')
        if provider and provider.get('gateway') != 'omniroute':
            # Preserve an exact legacy local binding. No direct remote path.
            from .providers import is_local_ollama
            if not is_local_ollama(provider) and values['execution']['mode'] != 'manual':
                raise ValueError(f'The saved {role} needs a gateway connection')
            # Preserve legacy/custom bindings without dispatching them. The
            # existing inference route guard still rejects unsupported endpoints.
            if values['execution']['mode'] in {'remote', 'delegate'}:
                raise ValueError(f'The pinned local {role} conflicts with remote placement')
            config[role] = validate_provider(provider, role)
            continue
        if values['execution']['mode'] == 'local':
            raise ValueError(f'The pinned remote {role} conflicts with local placement')
        if not connection_id and provider:
            matches = [e for e in entries if e['base_url'] == provider['base_url'] and e['gateway_type'] == provider.get('gateway_type', 'omniroute')]
            if len(matches) == 1:
                connection_id = matches[0]['connection_id']
        if not connection_id:
            raise ValueError(f'Choose the saved connection for pinned {role} {selection["model"]}')
        entry = next((e for e in entries if e['connection_id'] == connection_id), None)
        if entry is None:
            raise ValueError(f'The {role} connection is disabled or excluded by this setup')
        manager = engine.connections.for_policy(entry)
        if manager is None:
            raise ValueError(f'The {role} connection changed; review its setup')
        model = next((m for m in manager.models if m['id'] == selection['model']), None)
        if provider:
            if provider.get('base_url') != entry['base_url'] or provider.get('gateway_type', 'omniroute') != entry['gateway_type']:
                raise ValueError(f'The saved {role} connection identity changed')
            if provider.get('access') == 'included':
                access_policy.validate_current(provider.get('access_binding'), manager.settings)
        else:
            if model is None:
                raise ValueError(f'The {role} model has no saved price; refresh connection metadata or save its explicit configuration')
            classification = access_policy.classify(model, access_policy.connection_policy(entry))
            if classification not in {'local', 'public_free', 'included', 'priced'}:
                raise ValueError(f'The {role} model price is unknown')
            provider = {'model': selection['model'], 'input_rate': model.get('input_rate', 0) if classification == 'priced' else 0,
                        'output_rate': model.get('output_rate', 0) if classification == 'priced' else 0}
        provider.update(gateway='omniroute', connection_id=connection_id, gateway_type=entry['gateway_type'], base_url=entry['base_url'], model=selection['model'])
        config[role] = validate_provider(provider, role)
        if provider.get('access') == 'included' or (model and access_policy.classify(model, access_policy.connection_policy(entry)) == 'included'):
            config[role] = access_policy.bind_provider(config[role], access_policy.connection_policy(entry), model)
    result = {'execution': copy.deepcopy(values['execution']), 'providers': config, 'gateway_connections': entries}
    selected = next((e for e in entries if e['connection_id'] == engine.connections.selected_id), None)
    if selected:
        result['gateway_access'] = access_policy.connection_policy(selected)
    return result
