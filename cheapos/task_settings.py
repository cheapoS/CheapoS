"""Atomic task-scoped settings edits, preserving saved work and authority.

HTTP callers supply only a flat settings patch, revision and operation ID. The
controller remains the owner of dispatch; active edits explicitly require Pause.
"""
import copy
from .branch_authorization import digest
from .settings_store import SettingsConflict, overlay, fields

EXECUTION_FIELDS = {'execution.coordinator_assistance', 'execution.coordinator_model'}
TERMINAL = {'complete', 'completed', 'cancelled', 'merged', 'abandoned'}


def busy(engine, task_id):
    runtime = engine.runtimes.get(task_id)
    return bool(runtime and runtime.thread and runtime.thread.is_alive())


def saved_values(task):
    snapshot = task.get('settings_snapshot')
    if snapshot:
        return _saved_authority(task, copy.deepcopy(snapshot['values']))
    # Historical compatibility is explicit, never today's defaults. Preserve
    # missing fields instead of inventing provenance or changing task authority.
    from .routing import execution_from
    from .model_pool import automatic
    roles = {}
    for role in ('planner', 'worker', 'reviewer'):
        provider = (task.get('providers') or {}).get(role)
        if isinstance(provider, dict) and provider.get('model') and not automatic(task, role):
            roles[role] = {'strategy': 'only', 'model': provider['model'],
                           'connection_id': provider.get('connection_id')}
        else:
            roles[role] = {'strategy': 'automatic'}
    return _saved_authority(task, {'execution': execution_from(task.get('execution') or {}),
            'limits': copy.deepcopy(task.get('limits') or {}), 'roles': roles,
            'keep_up_to_date': bool(task.get('integration_policy', {}).get('keep_up_to_date', False))})


def _saved_authority(task, values):
    """Display approved task allowances without rewriting their capture receipt."""
    values.setdefault('limits', {}).update(copy.deepcopy(task.get('limits') or {}))
    run = task.get('branch_run') or {}
    limits = run.get('limits') or {}
    for key in ('dollars', 'worker_turns', 'reviewer_tokens', 'check_seconds', 'output_tokens'):
        if key in limits:
            values['limits'][key] = limits[key]
    if 'working_seconds' in limits:
        minutes = limits['working_seconds'] / 60
        values['limits']['run_minutes'] = int(minutes) if minutes.is_integer() else minutes
    if run and 'uncapped_work' in run.get('plan', {}):
        values['limits']['uncapped_work'] = run['plan']['uncapped_work']
    return values


def view(engine, task_id):
    with engine.lock:
        task = engine.store.get(task_id)
        values = saved_values(task)
        snapshot = task.get('settings_snapshot') or {}
        run = task.get('branch_run') or {}
        sources = copy.deepcopy(snapshot.get('sources') or {}) if snapshot else {
            key: {'scope': 'saved', 'provenance': 'unknown'} for key in fields(values)}
        captured = fields(snapshot.get('values') or {})
        for key, value in fields(values).items():
            if snapshot and (key not in captured or captured[key] != value):
                sources[key] = {'scope': 'task', 'provenance': 'approved_plan' if run else 'saved_task'}
        active = busy(engine, task_id)
        unfinished = task.get('status') not in TERMINAL and run.get('status') not in TERMINAL
        eligible = unfinished and not task.get('demo') and not task.get('commit_pending')
        eligible = eligible and (not run or run.get('status') in {'paused', 'blocked'} or active)
        eligible = eligible and not any(run.get(k) for k in ('pending_operations', 'merge_operation', 'target_update'))
        from .work_budgets import KEYS, usage, effective
        editable = sorted({f'limits.{key}' for key in KEYS} | EXECUTION_FIELDS | {f'limits.{key}' for key in values['limits']} | {'limits.uncapped_work', 'roles.reviewer'}) if eligible else []
        if task.get('planning_request') and not run.get('authorization') and not run.get('authorization_workspace'):
            editable = [key for key in editable if key.startswith('limits.')]
        return {'task_id': task_id, 'title': task.get('title', task_id), 'project': task.get('source'),
                'values': values, 'revision': snapshot.get('revision', 0),
                'active': active, 'paused': bool(eligible and not active and task.get('status') not in {'approved', 'awaiting_reply'}),
                'sources': sources,
                'approved_allowance': copy.deepcopy(run.get('limits')) if run else None,
                'current_models': {role: (provider or {}).get('model') for role, provider in task.get('providers', {}).items() if isinstance(provider, dict)},
                'editable_fields': editable, 'capabilities': {'apply': bool(eligible and not active),
                    'apply_and_continue': bool(eligible and not active and task.get('status') not in {'approved', 'awaiting_reply'}), 'pause_apply_and_continue': False,
                    'pause_to_apply': bool(eligible and active)},
                'reason': 'Pause to apply; your settings draft will be retained.' if active else
                    ('This task needs its existing proposal or integration controls.' if not eligible else ''),
                'accounted_cost': task.get('usage', {}).get('cost', 0),
                'work_usage': usage(task), 'work_budgets': effective(task)}


def reviewer_config(engine, task, selection):
    """Use cached eligibility on the captured connection, without model probes."""
    from . import access_policy, reviewer_recovery
    from .providers import validate_provider
    from .served_identity import normalized, opaque
    current = (task.get('providers') or {}).get('reviewer') or {}
    if selection.get('strategy') == 'automatic':
        if set(selection) != {'strategy'} or task.get('execution', {}).get('mode') not in {'remote', 'delegate'} or not task.get('route'):
            raise ValueError('Automatic review requires the saved remote placement')
        return current
    if set(selection) - {'strategy', 'model', 'connection_id'} or selection.get('strategy') != 'only':
        raise ValueError('Choose Automatic or a reviewer on this chat’s saved connection')
    if current.get('gateway') != 'omniroute' or selection.get('connection_id') != current.get('connection_id'):
        raise ValueError('Reviewer changes must use this chat’s saved gateway connection')
    chosen = selection.get('model')
    if not isinstance(chosen, str) or not chosen or opaque(chosen):
        raise ValueError('Choose an identifiable reviewer model')
    if reviewer_recovery.unknown_workers(task):
        raise ValueError('Saved worker identity must be established before changing the reviewer')
    used = {normalized((task.get('providers', {}).get('worker') or {}).get('model'))}
    for worker in reviewer_recovery.workers(task):
        used.update(normalized(worker.get(key)) for key in ('model', 'requested_model', 'served_model'))
    if normalized(chosen) in used:
        raise ValueError('Choose a reviewer independent of the saved authors')
    engine.guard_route(current)
    gateway = engine.connection_for(current)
    policy = access_policy.for_config(task, current)
    if task.get('gateway_connections') is None and policy is None:
        policy = (task.get('branch_run') or {}).get('model_policy', {}).get('gateway_access')
    access_policy.validate_current(policy, access_policy.effective_settings(task, gateway.settings))
    model = next((m for m in gateway.models if m.get('id') == chosen), None)
    if not model or not access_policy.eligible(model, policy):
        raise ValueError('Choose a cached eligible free or included reviewer; refresh shared connection metadata if needed')
    cfg = validate_provider({**current, 'model': chosen, 'input_rate': 0, 'output_rate': 0}, 'reviewer')
    if policy is not None:
        cfg['access_binding'] = copy.deepcopy(policy)
    if access_policy.classify(model, policy) == 'included':
        cfg = access_policy.bind_provider(cfg, policy, model)
    return cfg


def prepare(engine, task, patch):
    """Validate and alter an isolated task copy. No persistence or dispatch."""
    from .engine import limits_from
    from .routing import execution_from
    updated = copy.deepcopy(task)
    values = saved_values(task)
    execution_patch = {key.split('.')[1]: value for key, value in patch.items() if key.startswith('execution.')}
    limit_patch = {key.split('.')[1]: value for key, value in patch.items() if key.startswith('limits.')}
    if execution_patch:
        updated['execution'] = execution_from({**task.get('execution', {}), **execution_patch})
    if limit_patch:
        updated['limits'] = limits_from({**task['limits'], **limit_patch})
        if 'uncapped_work' in limit_patch:
            from .development import enabled
            if enabled(task):
                updated['operator_bounded_work'] = not updated['limits']['uncapped_work']
    run = updated.get('branch_run') or {}
    if updated.get('planning_request') and not run.get('authorization') and not run.get('authorization_workspace'):
        if any(not key.startswith('limits.') for key in patch):
            raise ValueError('Planning settings can amend work budgets; model selection uses the planning controls')
        from .branch_controller import run_limits, planning_work_policy, apply_planning_work_policy
        from .work_budgets import KEYS
        updated.setdefault('planning_policy_history', []).append({
            'limits':copy.deepcopy(updated['planning_limits']), 'work_policy':planning_work_policy(updated)})
        revised = copy.deepcopy(updated['planning_limits'])
        for key,target,scale in [('dollars','dollars',1),('worker_turns','worker_turns',1),
                ('run_minutes','working_seconds',60),('reviewer_tokens','reviewer_tokens',1),
                ('check_seconds','check_seconds',1),('output_tokens','output_tokens',1)]:
            if key in limit_patch: revised[target]=updated['limits'][key]*scale
        revised.update({key:value for key,value in updated['limits'].items() if key in KEYS})
        revised=run_limits(revised,3)
        updated['planning_limits']=revised
        updated['planning_task_limits']=copy.deepcopy(updated['limits'])
        policy=planning_work_policy(updated)
        if 'uncapped_work' in limit_patch: policy['uncapped_work']=limit_patch['uncapped_work']
        updated['planning_work_policy']=policy
        run['limits']=copy.deepcopy(revised);run['plan']['limits']=copy.deepcopy(revised)
        apply_planning_work_policy(run['plan'],policy)
        values=overlay(values,patch);values['limits']=copy.deepcopy(updated['limits'])
        return updated,values
    if 'roles.reviewer' in patch:
        selection = patch['roles.reviewer']
        if not isinstance(selection, dict):
            raise ValueError('Provide a reviewer selection')
        config = reviewer_config(engine, task, selection)
        updated.setdefault('operator_model_history', []).append({'role': 'reviewer', 'provider': copy.deepcopy(task['providers']['reviewer'])})
        updated['providers']['reviewer'] = config
        if selection['strategy'] == 'only':
            updated['operator_reviewer_model'] = config['model']
        else:
            updated.pop('operator_reviewer_model', None)
        # Failed exchanges/findings stay retained. Only incompatible approval
        # coverage is removed, never worker edits or passing check receipts.
        if updated.get('pending_review'):
            updated.setdefault('operator_review_history', []).append(copy.deepcopy(updated['pending_review']))
            updated['pending_review']['reviewer_model'] = config['model']
        updated['fresh_review'] = True
        if updated.get('route'):
            updated['route'].setdefault('preferred', {})['reviewer'] = config['model']
        run = updated.get('branch_run')
        if run:
            if run.get('final_review_packets'):
                run.setdefault('final_review_packet_history', []).extend(copy.deepcopy(list(run['final_review_packets'].values())))
            run['final_review_packets'] = {}
            run.pop('readiness', None)
            run['final_evidence'] = {}
    run = updated.get('branch_run')
    if run:
        if not run.get('authorization') or not isinstance(run['authorization'].get('contract'), dict):
            raise ValueError('This run has no saved authorization to amend')
        engine.branch.validate_authority(task, task['branch_run'])
        run.setdefault('settings_authority_history', []).append(copy.deepcopy(run['authorization']))
        for key, target, scale in [('worker_turns', 'worker_turns', 1), ('dollars', 'dollars', 1),
                                  ('run_minutes', 'working_seconds', 60), ('reviewer_tokens', 'reviewer_tokens', 1),
                                  ('check_seconds', 'check_seconds', 1), ('output_tokens', 'output_tokens', 1)]:
            if key in limit_patch:
                run['limits'][target] = updated['limits'][key] * scale
                run['plan']['limits'][target] = run['limits'][target]
        if 'uncapped_work' in limit_patch:
            run['plan']['uncapped_work'] = limit_patch['uncapped_work']
            if not limit_patch['uncapped_work'] and run['plan'].get('measurement'):
                run['plan']['measurement'] = False
        if execution_patch or 'roles.reviewer' in patch:
            run['model_policy']['execution'] = copy.deepcopy(updated['execution'])
            run['model_policy']['providers'] = copy.deepcopy(updated['providers'])
        contract = run['authorization']['contract']
        from .work_budgets import KEYS
        run['limits'].update({k:v for k,v in updated['limits'].items() if k in KEYS})
        run['plan']['limits']=copy.deepcopy(run['limits'])
        contract['limits'] = copy.deepcopy(run['limits'])
        contract['plan']['limits'] = copy.deepcopy(run['limits'])
        for flag in ('uncapped_work', 'measurement'):
            if flag in run['plan']: contract['plan'][flag] = run['plan'][flag]
        contract['model_policy'] = copy.deepcopy(run['model_policy'])
        run['authorization']['digest'] = digest(contract)
        run['plan_digest'] = digest(run['plan'])
        if run.get('development_authorization'):
            run['development_authorization']['plan_digest'] = digest(contract['plan'])
    values = overlay(values, patch)
    if limit_patch:
        values['limits'] = saved_values(updated)['limits']
    return updated, values


def save(engine, task_id, request):
    if not isinstance(request, dict) or set(request) - {'patch', 'expected_revision', 'operation_id', 'intent'}:
        raise ValueError('Provide a scoped task settings request')
    operation_id = request.get('operation_id')
    if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 200:
        raise ValueError('Provide a client operation ID')
    intent = request.get('intent', 'apply')
    if intent not in {'apply', 'apply-and-continue'}:
        raise ValueError('Pause to apply; active changes are not queued')
    fingerprint = digest(request)
    with engine.lock:
        engine.require_active_task(task_id)
        task = engine.store.get(task_id)
        previous = task.get('settings_operations', {}).get(operation_id)
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise ValueError('Operation ID was already used for different settings')
            return copy.deepcopy(previous['result'])
        current = view(engine, task_id)
        if type(request.get('expected_revision')) is not int or request['expected_revision'] != current['revision']:
            raise SettingsConflict(current)
        if not current['capabilities']['apply']:
            raise ValueError(current['reason'] or 'Pause this chat before applying settings')
        if intent == 'apply-and-continue' and not current['capabilities']['apply_and_continue']:
            raise ValueError('This chat has no paused work to continue; apply without continuing')
        patch = request.get('patch')
        if not isinstance(patch, dict) or not patch or set(patch) - set(current['editable_fields']):
            raise ValueError('These fields cannot be changed at this stage; workflow and placement use dedicated transitions')
        candidate, values = prepare(engine, task, patch)
        revision = current['revision'] + 1
        sources = copy.deepcopy(current['sources'])
        for key in patch:
            sources[key] = {'scope': 'task', 'revision': revision}
        candidate['settings_snapshot'] = {**candidate.get('settings_snapshot', {}), 'schema_version': 1,
                                          'revision': revision, 'values': values, 'sources': sources}
        _refresh_snapshot_policy(candidate)
        if candidate.get('branch_run', {}).get('authorization'):
            run = candidate['branch_run']
            run['settings_snapshot_digest'] = digest(candidate['settings_snapshot'])
            run['authorization']['contract']['settings_snapshot_digest'] = run['settings_snapshot_digest']
            run['authorization']['digest'] = digest(run['authorization']['contract'])
        result = {'saved': True, 'applied': True, 'pending': intent == 'apply-and-continue',
                  'continuing': False, 'revision': revision, 'task_id': task_id, 'operation_id': operation_id}
        candidate.setdefault('settings_operations', {})[operation_id] = {'fingerprint': fingerprint,
            'intent': intent, 'stage': 'pending' if result['pending'] else 'applied', 'result': result}
        engine.store.save(candidate)
    if intent == 'apply-and-continue':
        return continue_operation(engine, task_id, operation_id)
    return copy.deepcopy(result)


def continue_operation(engine, task_id, operation_id):
    """Resume persisted pending operations on restart; never dispatch twice."""
    with engine.lock:
        task = engine.store.get(task_id)
        operation = task['settings_operations'][operation_id]
        if operation['stage'] != 'pending':
            return copy.deepcopy(operation['result'])
        operation['stage'] = 'dispatching'
        engine.store.save(task)
    try:
        if task.get('branch_run'):
            outcome = engine.branch.resume(task_id, {})
            continued = bool(outcome.get('task')) and not outcome.get('needs_consent') and not outcome.get('needs_merge_recovery')
            reason = '' if continued else 'The saved continuation needs its existing authorization or integration action.'
        else:
            engine.start(task_id, {})
            continued, reason = True, ''
    except (ValueError, OSError) as error:
        continued, reason = False, str(error)
    with engine.lock:
        runtime = engine.runtimes.get(task_id)
        task = runtime.task if busy(engine, task_id) and hasattr(runtime, 'task') else engine.store.get(task_id)
        operation = task['settings_operations'][operation_id]
        operation['stage'] = 'continuing' if continued else 'waiting'
        operation['result'].update(pending=not continued, continuing=continued, reason=reason)
        engine.store.save(task)
        return copy.deepcopy(operation['result'])


def restore(engine):
    """Recover acknowledged apply-and-continue after process loss, using saved work."""
    for task in engine.store.list():
        for operation_id, operation in task.get('settings_operations', {}).items():
            if operation.get('stage') not in {'pending', 'dispatching'}:
                continue
            with engine.lock:
                saved = engine.store.get(task['id'])
                current = saved['settings_operations'][operation_id]
                if busy(engine, task['id']):
                    current['stage'] = 'continuing'
                    current['result'].update(pending=False, continuing=True)
                    engine.store.save(saved)
                    continue
                current['stage'] = 'pending'
                engine.store.save(saved)
            continue_operation(engine, task['id'], operation_id)


def sync_saved(task):
    """Keep legacy operator controls on the same task snapshot owner."""
    snapshot = task.get('settings_snapshot')
    if not snapshot:
        return
    values = copy.deepcopy(snapshot['values'])
    patch = {}
    for group in ('limits', 'execution'):
        for key, value in task.get(group, {}).items():
            if values.get(group, {}).get(key) != value:
                patch[group+'.'+key] = copy.deepcopy(value)
    for role in ('worker','reviewer'):
        if task.get('operator_'+role+'_model'):
            provider = task.get('providers', {}).get(role) or {}
            choice = {'strategy':'only','model':provider.get('model'),'connection_id':provider.get('connection_id')}
            if values.get('roles', {}).get(role) != choice:
                patch['roles.'+role] = choice
    if not patch:
        return
    snapshot['revision'] += 1
    snapshot['values'] = overlay(values, patch)
    for key in patch:
        snapshot.setdefault('sources', {})[key] = {'scope':'task','revision':snapshot['revision']}
    _refresh_snapshot_policy(task)
    run = task.get('branch_run')
    if run and 'settings_snapshot_digest' in run:
        run['settings_snapshot_digest'] = digest(snapshot)
        if run.get('authorization'):
            run['authorization']['contract']['settings_snapshot_digest'] = run['settings_snapshot_digest']
            run['authorization']['digest'] = digest(run['authorization']['contract'])


def _refresh_snapshot_policy(task):
    snapshot = task['settings_snapshot']
    if 'model_policy' not in snapshot:
        return
    policy = copy.deepcopy(snapshot['model_policy'])
    policy['execution'] = copy.deepcopy(task['execution'])
    for role, choice in snapshot['values']['roles'].items():
        policy['providers'][role] = copy.deepcopy(task.get('providers', {}).get(role)) if choice['strategy'] == 'only' else None
    snapshot['model_policy'] = policy
    snapshot['policy_values_digest'] = digest(snapshot['values'])
