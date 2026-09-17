"""One atomic owner for future-chat settings; saved tasks never inherit live values.

The engine supplies its existing validators and lock. This module does no model,
connection or repository I/O. Project keys must be registry-canonical paths.
"""
import copy
import hashlib
import json
from pathlib import Path
import threading

from .storage import write_json

ROLES = ('planner', 'worker', 'reviewer')
ROLE_FIELDS = {'strategy', 'model', 'connection_id', 'provider'}
PROVIDER_FIELDS = {'base_url', 'model', 'input_rate', 'output_rate', 'key_env',
                   'gateway', 'connection_id', 'gateway_type', 'provider', 'pacing',
                   'pacing_interval', 'access', 'access_binding', 'pricing_source', 'catalog_pricing'}


class SettingsConflict(ValueError):
    def __init__(self, current):
        super().__init__('Settings changed. Review the newer settings before saving.')
        self.current = current


def canonical_project(project):
    if not isinstance(project, str) or not project or not Path(project).is_absolute():
        raise ValueError('Choose a registered project')
    return str(Path(project).resolve())


def fields(values):
    """Known two-level values, with role selections and connection lists atomic."""
    output = {}
    for group, value in values.items():
        if group in {'allowed_connections', 'keep_up_to_date'}:
            output[group] = copy.deepcopy(value)
        else:
            if not isinstance(value, dict):
                raise ValueError(f'{group} settings must be an object')
            for key, item in value.items():
                output[f'{group}.{key}'] = copy.deepcopy(item)
    return output


def overlay(values, patch):
    output = copy.deepcopy(values)
    for key, value in patch.items():
        if key in {'allowed_connections', 'keep_up_to_date'}:
            output[key] = copy.deepcopy(value)
        else:
            group, name = key.split('.')
            output[group][name] = copy.deepcopy(value)
    return output


def resolve(document, project=None, draft=None):
    """Pure field resolution. Missing overrides inherit; false/zero/[] do not."""
    project = canonical_project(project) if project else None
    app = document['defaults']
    record = document['projects'].get(project, {'revision': 0, 'overrides': {}})
    values = copy.deepcopy(app['values'])
    sources = {key: {'scope': 'defaults', 'revision': app['revision']}
               for key in fields(values)}
    for scope, revision, patch in (('project', record['revision'], record['overrides']),
                                   ('draft', None, draft or {})):
        values = overlay(values, patch)
        for key in patch:
            sources[key] = {'scope': scope, 'revision': revision}
            if scope == 'project':
                sources[key]['project'] = project
    return {'schema_version': 1, 'values': values, 'sources': sources,
            'revision': record['revision'] if project else app['revision'],
            'parent_revision': app['revision'], 'project': project,
            'overrides': copy.deepcopy(record['overrides']) if project else {}}


class SettingsStore:
    def __init__(self, root, *, limits_validator, execution_validator,
                 provider_validator, lock=None):
        self.path = Path(root) / 'settings.json'
        self.lock = lock or threading.RLock()
        self.limits_validator = limits_validator
        self.execution_validator = execution_validator
        self.provider_validator = provider_validator
        self.execution_keys = set(execution_validator({}))
        self.limit_keys = set(limits_validator({'dollars': 0})) | {'uncapped_work'}
        self.allowed = ({f'execution.{k}' for k in self.execution_keys}
                        | {f'limits.{k}' for k in self.limit_keys}
                        | {f'roles.{k}' for k in ROLES} | {'allowed_connections', 'keep_up_to_date'})

    def validate_patch(self, patch):
        if not isinstance(patch, dict) or set(patch) - self.allowed:
            raise ValueError('Unknown settings fields')
        return copy.deepcopy(patch)

    def validate(self, values, *, independence=True):
        if not isinstance(values, dict) or set(values) - {'execution', 'limits', 'roles', 'allowed_connections', 'keep_up_to_date'}:
            raise ValueError('Unknown settings groups')
        self.validate_patch(fields(values))
        result = copy.deepcopy(values)
        result['execution'] = self.execution_validator(values['execution'])
        result['limits'] = self.limits_validator(values['limits'])
        roles = values.get('roles', {})
        if set(roles) != set(ROLES):
            raise ValueError('Provide all three agent selections')
        for role, selection in roles.items():
            if not isinstance(selection, dict) or set(selection) - ROLE_FIELDS:
                raise ValueError(f'Invalid {role} selection')
            if selection.get('strategy') == 'automatic':
                if set(selection) != {'strategy'}:
                    raise ValueError(f'Automatic {role} cannot include a fixed binding')
            elif selection.get('strategy') == 'only':
                if not isinstance(selection.get('model'), str) or not selection['model'].strip():
                    raise ValueError(f'Choose the {role} model')
                if 'provider' in selection:
                    provider = selection['provider']
                    if not isinstance(provider, dict) or set(provider) - PROVIDER_FIELDS:
                        raise ValueError(f'Invalid public {role} provider binding')
                    self.provider_validator(provider, role)
                    if 'access_binding' in provider:
                        binding = provider['access_binding']
                        if not isinstance(binding, dict) or set(binding) - {'version', 'base_url', 'connection_revision', 'included_models'}:
                            raise ValueError('Invalid included-access binding')
                        from .access_policy import model_ids
                        model_ids(binding.get('included_models', []))
                        if binding.get('base_url') != provider['base_url']:
                            raise ValueError('Included-access endpoint differs from provider')
                    if 'catalog_pricing' in provider:
                        prices = provider['catalog_pricing']
                        if not isinstance(prices, dict) or set(prices) - {'input_rate', 'output_rate'}:
                            raise ValueError('Invalid public catalog pricing')
                    if provider['model'] != selection['model']:
                        raise ValueError(f'{role} model differs from its provider binding')
                    if selection.get('connection_id') != provider.get('connection_id'):
                        raise ValueError(f'{role} connection differs from its provider binding')
                elif not isinstance(selection.get('connection_id'), str) or not selection['connection_id']:
                    # Migrated role strings retain a precise unresolved pin rather
                    # than silently broadening to automatic model selection.
                    if selection.get('connection_id') is not None:
                        raise ValueError(f'Choose the {role} connection')
            else:
                raise ValueError('Choose Automatic or Use only this model')
        worker = roles['worker']
        for other in ('planner', 'reviewer'):
            candidate = roles[other]
            if independence and worker['strategy'] == candidate['strategy'] == 'only' and worker['model'] == candidate['model']:
                raise ValueError(f'The worker must use a different model from the {other}')
        if type(result.get('keep_up_to_date', False)) is not bool:
            raise ValueError('Keep up to date must be true or false')
        if 'allowed_connections' in result:
            ids = result['allowed_connections']
            if not isinstance(ids, list) or any(not isinstance(v, str) or not v for v in ids) or len(set(ids)) != len(ids):
                raise ValueError('Provide a list of authorized connection IDs')
        return result

    def validate_transition(self, old, proposed):
        self.validate(proposed, independence=False)
        for other in ('planner', 'reviewer'):
            pair = [(proposed['roles'][r]['strategy'], proposed['roles'][r].get('model')) for r in ('worker', other)]
            before = [(old['roles'][r]['strategy'], old['roles'][r].get('model')) for r in ('worker', other)]
            if pair != before and pair[0][0] == pair[1][0] == 'only' and pair[0][1] == pair[1][1]:
                raise ValueError(f'The worker must use a different model from the {other}')

    def initialize(self, preferences, mappings=None, providers=None, *, notices=None, fresh_install=False):
        """Migrate once from public legacy data. Invalid values never reset policy.

        Keep the public migration input in the same atomic document as a recovery
        record. Credentials are rejected/stripped from providers, never backed up.
        """
        with self.lock:
            if self.path.exists():
                return self.read()
            mappings = mappings or {'defaults': {}, 'projects': {}}
            providers = providers or {}
            execution = self.execution_validator(preferences.get('execution', {}))
            roles = {}
            for role in ROLES:
                model = mappings.get('defaults', {}).get(role)
                provider = providers.get(role)
                # Explicit role maps take precedence, retaining compatible binding.
                if not model and execution['mode'] == 'manual' and provider:
                    model = provider.get('model')
                roles[role] = {'strategy': 'automatic'}
                if model:
                    roles[role] = {'strategy': 'only', 'model': model, 'connection_id': None}
                    if provider and provider.get('model') == model:
                        public = {k: copy.deepcopy(v) for k, v in provider.items() if k in PROVIDER_FIELDS}
                        roles[role].update(provider=public, connection_id=public.get('connection_id'))
            values = {'execution': execution, 'limits': self.limits_validator(preferences.get('limits', {'dollars': 0})), 'roles': roles, 'keep_up_to_date': False}
            document = {'schema_version': 1, 'generation': 1,
                        'defaults': {'revision': 1, 'values': values}, 'projects': {}, 'operations': {}, 'migration_notices': copy.deepcopy(notices or []), 'placement_confirmed': not fresh_install}
            for project, choices in mappings.get('projects', {}).items():
                key = canonical_project(project)
                overrides = {}
                for role, model in choices.items():
                    if role not in ROLES:
                        raise ValueError(f'Invalid migrated role: {role}')
                    selection = {'strategy': 'only', 'model': model, 'connection_id': None}
                    provider = providers.get(role)
                    if provider and provider.get('model') == model:
                        public = {k: copy.deepcopy(v) for k, v in provider.items() if k in PROVIDER_FIELDS}
                        selection.update(provider=public, connection_id=public.get('connection_id'))
                    overrides[f'roles.{role}'] = selection
                document['projects'][key] = {'revision': 1, 'overrides': overrides}
            values['limits'].setdefault('uncapped_work', False)
            self.validate(values, independence=False)
            for project in document['projects']:
                try:
                    self.validate(resolve(document, project)['values'], independence=False)
                except ValueError as error:
                    raise ValueError(f'{project}: {error}') from error
            public_providers = {role: {k: copy.deepcopy(v) for k, v in provider.items() if k in PROVIDER_FIELDS} for role, provider in providers.items() if role in ROLES and provider}
            for role, provider in public_providers.items():
                self.provider_validator(provider, role)
            document['public_config'] = copy.deepcopy(public_providers)
            document['migration'] = {'version': 1, 'fresh_install': fresh_install, 'public_providers': public_providers, 'defaults': copy.deepcopy(document['defaults']),
                                     'projects': copy.deepcopy(document['projects'])}
            write_json(self.path, document)
            return copy.deepcopy(document)

    def read(self):
        document = json.loads(self.path.read_text())
        if document.get('schema_version') != 1:
            raise ValueError('Unsupported settings schema; saved defaults were not changed')
        return document

    def view(self, project=None):
        with self.lock:
            document = self.read()
            return {**resolve(document, project), 'migration_notices': copy.deepcopy(document.get('migration_notices', []))}

    def capture(self, project=None, *, draft=None, expected_revision=None, expected_parent_revision=None):
        with self.lock:
            document = self.read()
            current = resolve(document, project)
            if ((expected_revision is not None and current['revision'] != expected_revision)
                    or (expected_parent_revision is not None and current['parent_revision'] != expected_parent_revision)):
                raise SettingsConflict(current)
            resolved = resolve(document, project, self.validate_patch(draft or {}))
            self.validate_transition(current['values'], resolved['values'])
            resolved['values'] = self.validate(resolved['values'], independence=False)
            return {**resolved, 'revision': 1, 'source_revision': current['revision'],
                    'source_parent_revision': current['parent_revision']}

    def save(self, patch, *, expected_revision, operation_id, project=None,
             expected_parent_revision=None, remove=(), public_config=None, _allow_legacy_collision=False):
        project = canonical_project(project) if project else None
        if public_config is not None and project:
            raise ValueError('Public model configuration belongs to new chat defaults')
        if public_config is not None:
            if not isinstance(public_config, dict) or set(public_config) - set(ROLES):
                raise ValueError('Invalid public model configuration')
            public_config = {role: ({k: copy.deepcopy(v) for k, v in provider.items() if k in PROVIDER_FIELDS} if provider else None) for role, provider in public_config.items()}
            for role, provider in public_config.items():
                if provider:
                    self.provider_validator(provider, role)
        patch = self.validate_patch(patch)
        if not isinstance(remove, (list, tuple)) or any(k not in self.allowed for k in remove) or set(remove) & set(patch):
            raise ValueError('Invalid override removals')
        if remove and not project:
            raise ValueError('Only project overrides can inherit')
        if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 200:
            raise ValueError('Provide a client operation ID')
        payload = {'patch': patch, 'project': project, 'remove': list(remove),
                   'expected_revision': expected_revision, 'expected_parent_revision': expected_parent_revision, 'public_config': public_config}
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
        with self.lock:
            document = self.read()
            previous = document['operations'].get(operation_id)
            if previous:
                if previous['fingerprint'] != fingerprint:
                    raise ValueError('Operation ID was already used for different settings')
                return copy.deepcopy(previous['result'])
            current = resolve(document, project)
            if (type(expected_revision) is not int or current['revision'] != expected_revision
                    or (project and (type(expected_parent_revision) is not int or current['parent_revision'] != expected_parent_revision))):
                raise SettingsConflict(current)
            updated = copy.deepcopy(document)
            if project:
                record = updated['projects'].setdefault(project, {'revision': 0, 'overrides': {}})
                record['overrides'].update(patch)
                for key in remove:
                    record['overrides'].pop(key, None)
                record['revision'] += 1
            else:
                updated['defaults']['values'] = overlay(updated['defaults']['values'], patch)
                updated['defaults']['revision'] += 1
            for key in [None, *updated['projects']]:
                proposed = resolve(updated, key)['values']
                old = resolve(document, key)['values']
                try:
                    if _allow_legacy_collision:
                        self.validate(proposed, independence=False)
                    else:
                        self.validate_transition(old, proposed)
                except ValueError as error:
                    raise ValueError(f'{key or "New chat defaults"}: {error}') from error
            if not project and 'execution.mode' in patch:
                updated['placement_confirmed'] = True
            if not project:
                updated['migration_notices'] = [notice for notice in updated.get('migration_notices', []) if notice['field'] not in patch]
            if public_config is not None:
                updated['public_config'] = copy.deepcopy(public_config)
            updated['generation'] += 1
            result = {**resolve(updated, project), 'saved': True}
            updated['operations'][operation_id] = {'fingerprint': fingerprint, 'result': result}
            write_json(self.path, updated)
            return copy.deepcopy(result)

    def legacy_preferences(self):
        values = self.view()['values']
        return {key: values[key] for key in ('execution', 'limits')}

    def legacy_role_mappings(self):
        document = self.read()
        def pins(roles):
            return {role: choice['model'] for role, choice in roles.items() if choice['strategy'] == 'only'}
        return {'defaults': pins(document['defaults']['values']['roles']),
                'projects': {key: pins({field.split('.')[1]: value for field, value in record['overrides'].items()
                                       if field.startswith('roles.')}) for key, record in document['projects'].items()}}

    def provider_defaults(self):
        with self.lock:
            document = self.read()
            result = copy.deepcopy(document.get('public_config', document.get('migration', {}).get('public_providers', {})))
            result.setdefault('worker', None)
            result.setdefault('reviewer', None)
            return result

    def remember_provider_defaults(self, providers):
        """Remember discovery metadata without converting Automatic into pins."""
        if not isinstance(providers, dict) or set(providers) - set(ROLES):
            raise ValueError('Invalid public model configuration')
        public = {}
        for role, provider in providers.items():
            public[role] = None if provider is None else self.provider_validator(provider, role)
        with self.lock:
            document = self.read()
            document['public_config'] = public
            document['generation'] += 1
            write_json(self.path, document)
