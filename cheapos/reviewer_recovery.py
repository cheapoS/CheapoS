"""Recover reviewer identity failures without replaying exhausted routes or work."""
import copy
from . import access_policy
from .served_identity import normalized, opaque, review_workers
from .providers import ProviderError, validate_provider

IDENTITY_ERRORS = {'review_identity_unknown', 'review_identity_conflict'}


def workers(task):
    scope = (task.get('pending_review') or {}).get('identity_scope') or {}
    return review_workers(task, {'review_candidate_id': scope.get('candidate_id')})


def unknown_workers(task):
    return [w for w in workers(task) if opaque(w.get('requested_model', w.get('model')))
            and not (w.get('identity_provenance') == 'response_model' and w.get('served_model'))]


def candidates(engine, task):
    current = task.get('providers', {}).get('reviewer') or {}
    gateway = engine.connection_for(current) if hasattr(engine,'connection_for') else engine.gateway
    if current.get('gateway') != 'omniroute' or current.get('base_url') != gateway.settings.get('base_url'):
        return []
    policy = access_policy.for_config(task, current) if task.get('gateway_connections') is not None else (task.get('route') or {}).get('access_policy', task.get('branch_run', {}).get('model_policy', {}).get('gateway_access'))
    access_policy.validate_current(policy, access_policy.effective_settings(task, gateway.settings))
    used = {normalized(task.get('providers', {}).get('worker', {}).get('model'))}
    from .branch_review_recovery import failed_models
    used.update(normalized(model) for model in failed_models(task))
    for worker in workers(task):
        used.update(normalized(worker.get(k)) for k in ('model', 'requested_model', 'served_model'))
    catalog = gateway.catalog(fresh=True)
    result = []
    for model in catalog.get('models', []):
        if not access_policy.eligible(model, policy) or opaque(model['id']) or normalized(model['id']) in used:
            continue
        pool = getattr(gateway, 'pool', None)
        if pool and pool.observation(current['base_url'], model['id'], (policy or {}).get('connection_revision')).get('cooling_down'):
            continue
        result.append({'id': model['id'], 'label': model.get('name') or model['id']})
    return result


def config(engine, task, model_id):
    cfg = copy.deepcopy(task['providers']['reviewer'])
    gateway = engine.connection_for(cfg) if hasattr(engine,'connection_for') else engine.gateway
    policy = access_policy.for_config(task,cfg) if task.get('gateway_connections') is not None else (task.get('route') or {}).get('access_policy', task.get('branch_run', {}).get('model_policy', {}).get('gateway_access'))
    cfg.update(model=model_id, input_rate=0, output_rate=0)
    for key in ('access', 'access_binding', 'pricing_source', 'catalog_pricing'):
        cfg.pop(key, None)
    catalog = gateway.catalog(fresh=False)
    model = next((m for m in catalog.get('models', []) if m['id'] == model_id), None)
    if model is None:
        catalog = gateway.catalog(fresh=True)
        model = next(m for m in catalog['models'] if m['id'] == model_id)
    cfg = validate_provider(cfg, 'reviewer')
    if policy is not None:
        cfg['access_binding'] = copy.deepcopy(policy)
        if access_policy.classify(model, policy) == 'included':
            cfg = access_policy.bind_provider(cfg, policy, model)
    return cfg


def request(engine, runtime, messages, tools, role, config_override=None, purpose=None, tool_choice=None):
    task = runtime.task
    if role != 'reviewer' or purpose == 'probe' or config_override is not None:
        return engine._request_routed(runtime, messages, tools, role, config_override, purpose, tool_choice=tool_choice)
    recovery = task.get('reviewer_identity_recovery')
    if not recovery:
        previous = next((r for r in reversed(task.get('request_metrics', [])) if r.get('role') == 'reviewer' and r.get('purpose') != 'probe'), {})
        if previous.get('error_code') in IDENTITY_ERRORS and previous.get('model') == (task.get('providers', {}).get('reviewer') or {}).get('model'):
            recovery = task['reviewer_identity_recovery'] = {'attempted': [previous['model']]}
            engine.store.save(task)
    if not recovery:
        try:
            return engine._request_routed(runtime, messages, tools, role, None, purpose, tool_choice=tool_choice)
        except ProviderError as error:
            if error.code not in IDENTITY_ERRORS:
                raise
            recovery = task['reviewer_identity_recovery'] = {'attempted': [task['providers']['reviewer']['model']]}
            engine.store.save(task)
    if unknown_workers(task):
        raise ProviderError('Historical worker identity is missing. A different reviewer cannot reconstruct it. Open Choose reviewer for the saved provenance limitation; no work or checks were discarded.', code='reviewer_recovery_required')
    from .model_pool import automatic
    if not automatic(task, 'reviewer') and not task.get('operator_reviewer_model'):
        raise ProviderError('Your manual reviewer could not establish independence. Choose reviewer to approve an eligible replacement.', code='reviewer_recovery_required')
    available = candidates(engine, task)
    selected = recovery.get('selected')
    chosen = task.get('operator_reviewer_model')
    choices = [m['id'] for m in available if m['id'] not in recovery['attempted']]
    if chosen:
        choices = [chosen] if chosen in {m['id'] for m in available} else []
    elif selected in {m['id'] for m in available}:
        choices.insert(0, selected)
    for model_id in dict.fromkeys(choices):
        runtime.guard()
        if model_id not in recovery['attempted']:
            recovery['attempted'].append(model_id)
        recovery.pop('selected', None)
        engine.event(task, 'reviewer_recovery', 'I couldn’t verify reviewer independence. I’m trying another reviewer and checking its identity.', {'model': model_id})
        engine.store.save(task)
        try:
            # _request retains accounting, permission and identity gates. The
            # recovery flag also requires actual response identity before tools.
            selected_config = config(engine, task, model_id)
            result = engine._request(runtime, messages, tools, role, selected_config, purpose, tool_choice=tool_choice)
        except ProviderError as error:
            if error.code not in IDENTITY_ERRORS and error.code != 'output_limit':
                raise
            engine.store.save(task)
            continue
        task['providers']['reviewer'] = selected_config
        if task.get('route'):
            task['route'].setdefault('preferred', {})['reviewer'] = model_id
        recovery['selected'] = model_id
        engine.store.save(task)
        return result
    raise ProviderError('No unused eligible reviewer could establish independence. Choose reviewer to inspect available models or update the connection. Saved work and passing checks are preserved.', code='reviewer_recovery_required')
