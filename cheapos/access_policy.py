"""Operator-declared included access, separate from advertised catalog pricing."""
import copy


def model_ids(value):
    if not isinstance(value, list) or len(value) > 200:
        raise ValueError('Choose up to 200 exact included model IDs')
    if any(not isinstance(v, str) or not v.strip() or v != v.strip() or len(v) > 200
           or any(c in v for c in '*?\n\r') or v.startswith('auto/') for v in value):
        raise ValueError('Included access requires exact model IDs, not aliases, wildcards or automatic pools')
    if any(v.startswith('openrouter/') and not v.endswith(':free') for v in value):
        raise ValueError('OpenRouter models without :free cannot be authorized as included account models')
    return sorted(set(value))


def snapshot(settings):
    revision = settings.get('connection_revision')
    if not revision:
        return None  # Legacy connections and saved tasks retain their policy.
    return {'version': 1, 'base_url': settings['base_url'], 'connection_revision': revision,
            'included_models': model_ids(settings.get('included_models', []))}


def included(policy, model):
    if model['id'].startswith('openrouter/') and not model['id'].endswith(':free'):
        return False
    return bool(policy and model['id'] in policy.get('included_models', [])
                and not model['id'].startswith('auto/') and model.get('provider') != 'combo'
                and not model.get('local'))


def classify(model, policy=None):
    if model.get('local'):
        return 'local'
    if model.get('free'):
        return 'public_free'
    if included(policy, model):
        return 'included'
    rates = [model.get('input_rate'), model.get('output_rate')]
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in rates):
        return 'priced'
    return 'unknown'


def eligible(model, policy=None):
    is_free_auto = model['id'].startswith('auto/') and (':free' in model['id'] or '-free' in model['id'])
    return (classify(model, policy) in {'public_free', 'included'}
            and model.get('tool_calling') is True and not model.get('local')
            and (not model['id'].startswith('auto/') or is_free_auto)
            and (model.get('provider') != 'combo' or is_free_auto))


def validate_current(policy, settings):
    if policy is not None and policy != snapshot(settings):
        raise ValueError('Connection access changed. Inspect Models and authorize a new run; saved access cannot expand or follow a different connection.')


def bind_provider(config, policy, model=None):
    if (not policy or config.get('gateway') != 'omniroute' or config['base_url'] != policy['base_url']
            or config['model'] not in policy['included_models']):
        raise ValueError('Included access is not authorized for this exact connection and model')
    if model and (model.get('local') or model.get('provider') == 'combo' or model['id'].startswith('auto/')):
        raise ValueError('Included access cannot authorize a local or automatic model pool')
    return {**config, 'access': 'included', 'access_binding': copy.deepcopy(policy),
            'input_rate': 0.0, 'output_rate': 0.0, 'pricing_source': 'operator_included',
            'catalog_pricing': {k: model.get(k) if model else None for k in ('input_rate', 'output_rate')}}


def effective_settings(task, settings):
    if not isinstance(task, dict) or 'branch_run' not in task or not isinstance(settings, dict):
        return settings
    run = task.get('branch_run') or {}
    gw_access = run.get('model_policy', {}).get('gateway_access')
    if gw_access and settings.get('connection_revision') == gw_access.get('connection_revision'):
        return {**settings, 'included_models': gw_access.get('included_models', [])}
    return settings


def guard(task, config, settings, models=None, role=None):
    """Check before reservations/probes. Never grants access from a catalog alone."""
    settings = effective_settings(task, settings)
    policy = task.get('access_policy')
    if config.get('access') == 'included':
        validate_current(config.get('access_binding'), settings)
        if not policy or config.get('access_binding') != policy:
            raise ValueError('Included provider access is not bound to this saved task')
        bind_provider(config, policy)
    route = task.get('route') or {}
    if route.get('access_policy') is not None and (config.get('gateway') == 'omniroute' or role == 'planner'):
        validate_current(route['access_policy'], settings)
        if config.get('access_binding') != route['access_policy']:
            raise ValueError('Automatic provider is not bound to the captured access policy. Inspect Models and authorize a new run.')
        model = next((m for m in (models or []) if m['id'] == config['model']), None)
        if model is None or not eligible(model, route['access_policy']):
            raise ValueError('Automatic candidate is outside the captured access/capability policy')
        if classify(model, route['access_policy']) == 'included' and config.get('access') != 'included':
            raise ValueError('Included estimate needs its explicit access provenance')
        if config['base_url'] != route['access_policy']['base_url']:

            raise ValueError('Automatic provider endpoint differs from the authorized connection')
