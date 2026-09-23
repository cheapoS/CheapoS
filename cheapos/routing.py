"""Opt-in execution placement. Automatic routes only use explicit free models."""
from .instructions.runtime import text as instruction

import copy
import math
import time

from . import access_policy, route_health, routing_trace, route_schedule
from .development import enabled as developing
from .providers import ProviderError, is_local_ollama, validate_provider


MODES = {"manual", "delegate", "local", "remote"}
DEFAULT_EXECUTION = {"mode": "manual", "local_model": "", "local_reviewer": "", "local_planner": "", "coordinator_assistance": False, "coordinator_model": "", "development_mode": False}
COORDINATOR_SYSTEM = instruction('coordinator.chat')
DELEGATE_TOOL = {"type": "function", "function": {
    "name": "delegate_work", "description": "Hand project work to a free remote worker; the local model goes idle.",
    "parameters": {"type": "object", "properties": {"summary": {"type": "string"}},
                   "required": ["summary"], "additionalProperties": False}}}
PROBE_MARKER = route_health.PROBE_MARKER
PROBE_VERSION = route_health.PROBE_VERSION
PROBE_TOOL = {"type": "function", "function": {
    "name": "routing_ready", "description": "Confirm tool calling works. This tool does not execute anything.",
    "parameters": {"type": "object", "properties": {"marker": {"type":"string", "enum":[PROBE_MARKER]}}, "required":["marker"], "additionalProperties": False}}}
PROBE_MESSAGES = [{"role": "user", "content": "Call routing_ready with marker cheapos-tool-check-v2 now. Do not do other work."}]


class RoutingPause(Exception):
    code = 'routing_unavailable'
    def __init__(self, message, retry_at=None, scope=None):
        super().__init__(message)
        self.retry_at = retry_at
        self.scope = scope


def qualify(engine, runtime, gateway, model, cfg, role, policy, *, trace=None, before_probe=None):
    """Shared scoped tool qualification for initial routing and recovery."""
    base_url = cfg['base_url']
    revision = (policy or {}).get('connection_revision')
    identity = route_health.probe_identity(base_url, model, revision)
    def note(reason):
        if trace is not None:
            routing_trace.candidate(trace, model['id'], reason)
    if gateway.pool.fresh_probe(base_url, model['id'], revision, identity):
        note('cached_probe')
        return True
    owner, pending = gateway.pool.claim_probe(identity)
    if pending is None and not owner:
        raise RoutingPause('Connection checks are busy. Your task will retry automatically.',
                           retry_at=time.time()+route_schedule.ROUND_SECONDS, scope='probe_capacity')
    try:
        if not owner:
            note('shared_probe')
            while not pending.wait(.1):
                runtime.guard()
                if runtime.stop.is_set(): raise InterruptedError('Task stopped')
            access_policy.validate_current(policy, access_policy.effective_settings(runtime.task, gateway.settings))
            return gateway.pool.fresh_probe(base_url, model['id'], revision, identity)
        if not gateway.pool.fresh_probe(base_url, model['id'], revision, identity):
            note('probe_required')
            if before_probe is not None: before_probe()
            probes = runtime.task.setdefault('progress_state', {}).setdefault('route_probes', {})
            probes[role] = probes.get(role, 0) + 1
            message = engine.request(runtime, PROBE_MESSAGES, [PROBE_TOOL], role,
                                     config_override=cfg, purpose='probe')
            route_health.validate_probe(message, engine.parse_call)
            gateway.pool.record(base_url, model['id'], role, probe=True,
                                connection_revision=revision, probe_identity=identity)
        return True
    finally:
        if owner: gateway.pool.release_probe(identity, pending)


def catalog_pause(status):
    if status == 'auth_required':
        return RoutingPause('OmniRoute needs a valid client API key. Open Models and update the gateway key; saved work is kept.')
    return RoutingPause('OmniRoute is temporarily unavailable. Saved work is queued for an automatic retry.',
                        retry_at=time.time() + route_schedule.ROUND_SECONDS, scope='connection')


def execution_from(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULT_EXECUTION):
        raise ValueError("Provide valid execution preferences")
    result = {**DEFAULT_EXECUTION, **value}
    if result["mode"] not in MODES:
        raise ValueError("Choose where the work runs")
    if type(result["development_mode"]) is not bool:
        raise ValueError("Development mode must be On or Off")
    if type(result["coordinator_assistance"]) is not bool:
        raise ValueError("Coordinator assistance must be On or Off")
    for key in ("local_model", "local_reviewer", "local_planner", "coordinator_model"):
        if not isinstance(result[key], str) or len(result[key]) > 200:
            raise ValueError("Enter an installed local model ID")
        result[key] = result[key].strip()
    return result


def local_config(model, role):
    if not model:
        raise ValueError("Choose an installed Ollama model for local chat")
    return validate_provider({"base_url": "http://127.0.0.1:11434/v1", "model": model,
                              "input_rate": 0, "output_rate": 0}, role)


def verify_local(config):
    # A localhost Ollama endpoint can proxy cloud models. Check metadata before
    # sending a conversation, and fail closed when the model cannot be identified.
    from .startup import local_json
    try:
        info = local_json(config["base_url"].removesuffix("/v1") + "/api/show", {"model": config["model"]})
        if info.get("remote_host") or info.get("remote_model") or "cloud" in config["model"].split(":")[-1]:
            raise RoutingPause("Choose an installed local model, not an Ollama cloud route, for local execution.")
        if not {"completion", "tools"}.issubset(info.get("capabilities", [])):
            raise RoutingPause("The selected local model must advertise completion and tool support. Check the installed model in Ollama.")
    except (OSError, ValueError, TypeError, AttributeError):
        raise RoutingPause("Could not verify the installed local model. Start Ollama and check the model ID, then resume.") from None


def coordinator_assistance_config(task, verify=False):
    """Resolve only the task's explicitly opted-in local recovery assistant.

    Saving preferences never probes or starts inference. A consultation caller
    verifies metadata at its trigger and handles unavailable local service as an
    optional skipped intervention, without changing worker/reviewer placement.
    """
    execution = task.get('execution') or {}
    if execution.get('coordinator_assistance') is not True:
        return None
    model = execution.get('coordinator_model') or execution.get('local_model')
    if not model:
        providers = task.get('providers') or {}
        for role in ('coordinator', 'worker'):
            provider = providers.get(role) or {}
            if is_local_ollama(provider):
                model = provider.get('model')
                break
    if not model:
        return None
    config = local_config(model, 'coordinator')
    if verify:
        verify_local(config)
    return config


def setup_task(task, execution, config, gateway):
    """Pin placement at creation. Old tasks keep their original pair."""
    task["execution"] = copy.deepcopy(execution)
    policy = access_policy.snapshot(gateway.settings)
    if policy is not None:
        task['access_policy'] = policy
    # Bind legacy model choices to their saved connection before selection.
    for role, provider in task.get('providers', {}).items():
        if provider and provider.get('gateway') == 'omniroute' and task.get('gateway_connections') is not None:
            matches = [e for e in task['gateway_connections'] if e['base_url'] == provider.get('base_url')
                       and e['gateway_type'] == provider.get('gateway_type','omniroute')]
            if len(matches) == 1: provider.setdefault('connection_id', matches[0]['connection_id'])
    mode = execution["mode"]
    if mode == "manual":
        return
    if not task["conversational"]:
        raise ValueError("Automatic execution choices require a chat")
    if mode in {"delegate", "local"}:
        model = execution["local_model"] or (config.get("worker", {}).get("model") if is_local_ollama(config.get("worker") or {}) else "")
        local = local_config(model, "worker")
        if mode == "local":
            reviewer = local_config(execution["local_reviewer"] or model, "reviewer")
            planner = local_config(execution.get("local_planner") or execution.get("local_reviewer") or model, "planner")
            task["providers"] = {"worker": local, "reviewer": reviewer, "planner": planner}
            return
        planner = copy.deepcopy(config.get("planner") or config.get("reviewer"))
        if planner: planner["credential_role"] = "planner" if config.get("planner") else "reviewer"
        task["providers"] = {"coordinator": local, "worker": None, "reviewer": None, "planner": planner}
        task["usage"]["coordinator"] = {"tokens": 0, "cost": 0}
        task["active_role"] = "coordinator"
    else:
        planner = copy.deepcopy(config.get("planner") or config.get("reviewer"))
        if planner: planner["credential_role"] = "planner" if config.get("planner") else "reviewer"
        task["providers"] = {"worker": None, "reviewer": None, "planner": planner}
    task["route"] = {"ready": False, "base_url": gateway.settings["base_url"],
                     "preferred": {r: (config.get(r) or {}).get("model") for r in ("worker", "reviewer", "planner")}}
    if policy is not None: task['route']['access_policy'] = copy.deepcopy(policy)
    planner = task['providers'].get('planner')
    if task.get('gateway_connections') is not None and planner and planner.get('gateway') == 'omniroute':
        entries = [e for e in task['gateway_connections'] if e['base_url'] == planner.get('base_url')
                   and e['gateway_type'] == planner.get('gateway_type','omniroute')]
        if not planner.get('connection_id') and len(entries) == 1: planner['connection_id'] = entries[0]['connection_id']
        entry = next((e for e in entries if e['connection_id'] == planner.get('connection_id')), None)
        if entry is None:
            task['providers']['planner'] = None
            return
        policy = access_policy.connection_policy(entry)
    if policy is not None and planner and planner.get('gateway') == 'omniroute' and planner.get('base_url') == policy['base_url']:
        if planner.get('access_binding') is None: planner['access_binding'] = copy.deepcopy(policy)
        if planner['access_binding'] != policy: raise ValueError('Planner access changed; save its model choice again')
        if planner['model'] in policy['included_models']:
            planner.update(access_policy.bind_provider(planner, policy))


def select_remote(engine, runtime, role="worker", replace=False):
    while True:
        try:
            return _select_connections(engine, runtime, role, replace)
        except RoutingPause as error:
            if not getattr(runtime, 'route_autorecover', False):
                raise
            # Only availability failures with a known retry schedule can wait.
            # Credentials, invalid requests and exhausted repair attempts need
            # their own recovery; inventing a five-second reset replays them.
            if not getattr(error, 'retry_at', None):
                raise
            info = engine.route_wait_info(runtime, error)
            if not info['can_wait']:
                raise
            task = runtime.task
            previous_status = task['status']
            task['route_unavailable'] = info
            task['retry_wait_enabled'] = True
            engine.wait_for_route(runtime)
            task['retry_wait_enabled'] = False
            task['status'] = previous_status


def _select_connections(engine, runtime, role, replace):
    task = runtime.task
    if task['providers'].get(role) and not replace: return
    entries = task.get('gateway_connections')
    if entries is None:
        gateway = engine.gateway
        if getattr(engine, 'connections', None):
            config = {**(task['providers'].get(role) or {}), 'base_url':task['route']['base_url']}
            try:
                gateway = engine.connections.resolve(config, gateway)
            except ValueError as error:
                raise RoutingPause(str(error)) from error
        return _select_remote(engine, runtime, role, replace, gateway)
    current = (task['providers'].get(role) or {}).get('connection_id')
    entries = sorted(entries, key=lambda e:e['connection_id'] != current)
    pauses = []
    for entry in entries:
        gateway = engine.connections.for_policy(entry)
        if gateway is None: continue
        try:
            return _select_remote(engine, runtime, role, replace, gateway, access_policy.connection_policy(entry), entry['connection_id'])
        except RoutingPause as error:
            pauses.append(error)
            engine.event(task,'routing','Trying another enabled gateway',{'connection_id':entry['connection_id'], 'gateway':entry['name'], 'role':role, 'reason':str(error)})
    if len(pauses) == 1:
        raise pauses[0]
    retry = [p.retry_at for p in pauses if p.retry_at]
    raise RoutingPause('No authorized gateway is ready. Saved work and usage are retained; checking enabled connections again.' if pauses else
                       'The connections authorized for this task are disabled or changed. Restore their saved settings in Models.',
                       retry_at=min(retry) if retry else None, scope='connection')


def _select_remote(engine, runtime, role="worker", replace=False, gateway=None, policy=None, connection_id=None):
    """Find one needed role; each candidate is probed at most once per selection."""
    task = runtime.task
    gateway = gateway or engine.gateway
    route = task["route"]
    policy = policy if connection_id else route.get("access_policy")
    base_url = gateway.settings["base_url"] if connection_id else route["base_url"]
    access_policy.validate_current(policy, access_policy.effective_settings(task, gateway.settings))
    if task["providers"].get(role) and not replace:
        return
    trace = routing_trace.begin(task, role, route.get("preferred", {}).get(role))
    if connection_id: trace.update(connection_id=connection_id, gateway=gateway.settings["name"])
    route["waiting_for"] = role
    if developing(task) and route.get('failures'):
        history=route.setdefault('failure_history',[])
        history.extend(copy.deepcopy(route['failures']))
        if len(history)>200:
            del history[:-200];route['failure_history_truncated']=True
    route["failures"] = []
    if not gateway.matches(base_url):
        raise RoutingPause("Connect this chat's OmniRoute gateway in Models, then resume. Local work will not start as a fallback.")
    catalog = gateway.catalog(fresh=True)
    if catalog["status"] != "ready":
        raise catalog_pause(catalog["status"])
    # Read-only planning does not reserve a model or make it a patch author.
    other = "worker" if role == "reviewer" else "reviewer" if role == "worker" else None
    used = {task["providers"][other]["model"]} if other and task["providers"].get(other) else set()
    if role == "reviewer":
        # A previous worker may have authored part of the patch before a handoff.
        used.update(e["detail"]["model"] for e in task["events"] if e["kind"] == "tool"
                    and e["title"] in {"write file", "replace text", "replace lines"} and isinstance(e.get("detail"), dict)
                    and e["detail"].get("model"))
    used.update(runtime.failed_models)
    used.update(task.get('branch_run',{}).get('implementation_recovery',{}).get('failed_models',[]))
    from .branch_review_recovery import failed_models
    from .served_identity import normalized
    failed_reviewers = {normalized(model) for model in failed_models(task)} if role == 'reviewer' else set()
    used.update(model['id'] for model in catalog['models'] if normalized(model['id']) in failed_reviewers)
    connection_revision=(policy or {}).get('connection_revision')
    from .provider_recovery import outage, provider
    # Pool records carry actual outage scope and expiry. Legacy request-level
    # provider exclusions must not survive recovery.
    route.setdefault('availability_recovery', {}).setdefault(role, {'handoffs':0,'providers':[]})['providers'] = []
    # A model-scoped outage must not ban its healthy siblings, but their cached
    # probes/preferences must not crowd out other providers during failover.
    deferred_providers = set()
    active_failure_provider = set()
    recovery = route.get('recovery', {}).get(role)
    current = task['providers'].get(role) or {}
    if (not connection_id or not current.get('connection_id') or current.get('connection_id') == connection_id):
        if recovery and recovery.get('from'):
            active_failure_provider.add(provider(recovery['from']))
        elif replace and current.get('model'):
            active_failure_provider.add(provider(current['model']))
    for failed_model in runtime.failed_models:
        deferred_providers.add(provider(failed_model))
    round_state = route_schedule.begin(task, role + ":" + connection_id if connection_id else role)
    rejected_probes = route.setdefault('rejected_probes', {})
    candidates = []
    for model in catalog['models']:
        probe_key = role + ':' + route_health.probe_identity(base_url, model, connection_revision)
        obs = gateway.pool.observation(base_url, model['id'], connection_revision)
        if obs['cooling_down'] and (obs.get('failure') or {}).get('category') in {'rate_limit_quota', 'transient_provider', 'credential_access'}:
            deferred_providers.add(provider(model['id']))
        if route_schedule.rejected(rejected_probes.get(probe_key)) or obs.get('probe_rejected'):
            used.add(model['id'])
            routing_trace.candidate(trace, model['id'], 'probe_rejected')
            continue
        fit = routing_trace.context_fit(task, model)
        minimum = task.get('context_route_minimum', {}).get(role)
        if minimum and (model.get('metadata_evidence', {}).get('stale') or not isinstance(model.get('context_length'), int) or model['context_length'] < minimum):
            fit = 'context_capacity_insufficient'
        reason = ('local_excluded' if model.get('local')
                  else 'auto_excluded' if model['id'].startswith('auto/')
                  else 'capability_missing' if (model.get('chat_completion') is False
                                               or (role != 'coordinator' and model.get('tool_calling') is not True))
                  else 'access_excluded' if not access_policy.eligible(model, policy)
                  else 'failed_model' if model['id'] in runtime.failed_models
                  else 'prior_worker' if model['id'] in used
                  else 'cooldown' if obs['cooling_down']
                  else fit)
        routing_trace.candidate(trace, model['id'], reason)
        if reason in {'eligible', 'fit_unknown'}: candidates.append(model)
    preferred = route.get("preferred", {})
    connection_revision=(policy or {}).get('connection_revision')
    text_only = getattr(runtime, 'text_only_route', False)
    if text_only:
        candidates.sort(key=lambda m: gateway.pool.conversation_rank(base_url, m, role, preferred.get(role), connection_revision))
    elif hasattr(gateway.pool, 'interleave'):
        candidates = gateway.pool.interleave(base_url, candidates, role, preferred.get(role), connection_revision)
    else:
        candidates.sort(key=lambda m: gateway.pool.rank(base_url, m, role, preferred.get(role), connection_revision))
    tried = set()
    probes = task.setdefault("progress_state", {}).setdefault("route_probes", {})
    probes.setdefault(role, 0)
    def provider_penalty(p):
        if p in active_failure_provider: return 2
        if p in deferred_providers: return 1
        return 0

    rank_order = {model['id']: index for index, model in enumerate(candidates)}
    remaining = list(candidates)
    while remaining:
        # Preserve ranking within each group. Reorder after availability errors,
        # so one provider cannot consume this discovery batch with siblings.
        remaining.sort(key=lambda model: (provider_penalty(provider(model['id'])), rank_order[model['id']]))
        model = remaining.pop(0)
        # A preceding probe may have cooled the whole provider. Do not repeat
        # its cached error against every other model or count those as failures.
        obs = gateway.pool.observation(base_url, model["id"], connection_revision)
        if obs["cooling_down"] or obs.get("probe_rejected"):
            routing_trace.candidate(trace, model["id"], "probe_rejected" if obs.get("probe_rejected") else "cooldown")
            continue
        identity = route_health.probe_identity(base_url, model, connection_revision)
        cached = gateway.pool.fresh_probe(base_url, model['id'], connection_revision, identity)
        if model['id'] in tried or (not text_only and not cached and round_state['probes'] >= route_schedule.BATCH_SIZE): continue
        tried.add(model['id'])
        candidate_provider = provider(model['id'])
        all_deferred = deferred_providers | active_failure_provider
        if all_deferred and candidate_provider not in all_deferred:
            engine.event(task, 'routing', 'Trying another provider', {
                'model': model['id'], 'role': role, 'provider': candidate_provider,
                'deferred_providers': sorted(all_deferred),
                'summary': 'Trying a different eligible provider after an availability failure. Saved work and model permissions are unchanged.'})
        cfg = validate_provider({"gateway_type": gateway.settings.get("gateway_type", "omniroute"), "gateway": "omniroute", "base_url": base_url, "model": model["id"],
                                 "input_rate": 0, "output_rate": 0, **({"provider": model["provider"]} if model.get("provider") else {})}, role)
        if connection_id: cfg['connection_id'] = connection_id
        if policy is not None: cfg['access_binding'] = copy.deepcopy(policy)
        if access_policy.classify(model, policy) == 'included':
            cfg = access_policy.bind_provider(cfg, policy, model)
        label = 'included' if cfg.get('access') == 'included' else 'free'
        engine.event(task, "routing", "Connecting for a chat reply" if text_only else ("Checking included " if label == "included" else "Checking a free ") + role, {"model": model["id"], "role": role, "connection_id":connection_id, "gateway":gateway.settings.get("name","OmniRoute")})
        try:
            if text_only:
                routing_trace.candidate(trace, model['id'], 'text_reply_no_tools')
            else:
                def count_probe():
                    round_state['probes'] += 1
                if not qualify(engine, runtime, gateway, model, cfg, role, policy,
                               trace=trace, before_probe=count_probe):
                    continue
            routing_trace.selected(trace, model['id'])
            observed=gateway.pool.observation(base_url,model['id'],connection_revision).get('role_evidence',{}).get(role,{})
            engine.event(task,'routing','Observed completion evidence' if observed.get('completed',0) else 'No prior completion evidence',
                         {'model':model['id'],'role':role,'completed':observed.get('completed',0),
                          'independently_disproved':observed.get('independently_disproved',0)})
            task["providers"][role] = cfg
            runtime.route_wait_started_at = None
            route["ready"] = bool(task["providers"].get("worker"))
            route.pop("waiting_for", None)
            engine.event(task, "routing", "Chat route selected" if text_only else label.capitalize() + " " + role + " is ready", {"model": model["id"], "role": role, "tool_check": "not needed for a text reply" if text_only else "recent cached observation" if cached else "new probe"})
            engine.store.save(task)
            return
        except (ProviderError, ValueError, TypeError, KeyError) as error:
            candidate_rejected = route_health.candidate_probe_rejection(error)
            classification = route_health.classify(error, {'purpose':'probe', 'caller_error':isinstance(error, ValueError), 'candidate_rejected': candidate_rejected})
            if classification['category'] == 'malformed_request' and not candidate_rejected:
                code = getattr(error, 'code', None)
                status = code.replace('http_', 'HTTP ') if code in {'http_400', 'http_422'} else 'request validation failure'
                classification['action'] = f"Connection check for {model['id']} was rejected ({status}). No task work was sent. Select another eligible worker in recovery controls, or inspect this route in OmniRoute; repeating the same request will not fix it."
            if candidate_rejected:
                classification['scope'] = 'model'
                classification['action'] = f"The connection probe was rejected for {model['id']}. Trying another authorized candidate; this is not a model quality finding."
                rejected_probes[role + ':' + identity] = {'model': model['id'], 'code': error.code, 'retry_at': time.time()+route_schedule.REJECTED_SECONDS}
                while len(rejected_probes) > 256:
                    rejected_probes.pop(next(iter(rejected_probes)))
                used.add(model['id'])
            cooldown = classification['category'] == 'rate_limit_quota'
            if cooldown or classification['category'] in {'transient_provider', 'unavailable_route', 'candidate_rejected', 'malformed_request', 'credential_access'}:
                deferred_providers.add(provider(model['id']))
            if classification['quality_impact']: runtime.failed_models.add(model['id'])
            gateway.pool.record(base_url, model['id'], role, error=error, connection_revision=connection_revision,
                                failure_context={'caller_error':isinstance(error, ValueError), 'candidate_rejected': candidate_rejected})
            failure = {'model':model['id'], 'role':role, 'error':classification['action'],
                       'scope':classification['scope'], 'failure_category':classification['category']}
            route['failures'].append(failure)
            metric = next((m for m in reversed(task.get('request_metrics', []))
                           if m.get('purpose') == 'probe' and m.get('model') == model['id']), None)
            if metric is not None:
                metric.update(status='failed', failure_category=classification['category'])
                routing_trace.request(task, metric)
            engine.event(task, 'routing', 'Provider is cooling down' if cooldown else 'Provider access denied' if classification['category'] == 'credential_access' else 'Model check failed', failure)
            engine.store.save(task)
            if classification['scope'] in {'request','connection','account'}:
                retry = time.time() + (getattr(error, 'retry_after', None) or route_schedule.ROUND_SECONDS) if cooldown else None
                raise RoutingPause(classification['action'], retry_at=retry, scope=classification['scope']) from None
    minimum = task.get('context_route_minimum', {}).get(role)
    if minimum and not any(access_policy.eligible(m, policy) and not m.get('local')
            and not m.get('metadata_evidence', {}).get('stale')
            and type(m.get('context_length')) is int and m['context_length'] >= minimum
            for m in catalog['models']):
        raise RoutingPause('This request needs an authorized model with a verified larger context window. Saved context and evidence are retained.', scope='context_capacity')
    provider_waits = [gateway.pool.observation(base_url, m["id"], connection_revision) for m in catalog["models"]
                      if access_policy.eligible(m, policy) and not m.get("local") and m["id"] not in used
                      and not m['id'].startswith('auto/') and m.get('tool_calling') is True
                      and routing_trace.context_fit(task, m) in {'eligible', 'fit_unknown'}
                      and (not minimum or (not m.get('metadata_evidence', {}).get('stale') and type(m.get('context_length')) is int and m['context_length'] >= minimum))]
    access_blocked = [h for h in provider_waits if h['cooling_down'] and (h.get('failure') or {}).get('category') == 'credential_access']
    if access_blocked and len(access_blocked) == len(provider_waits):
        # A local auth-failure cache expiry is not a provider quota reset.
        # All usable candidates were considered; another gateway may still
        # work, but repeating selection here cannot repair credentials/access.
        scope = 'connection' if any(h.get('cooldown_scope') in {'connection', 'account'} for h in access_blocked) else 'provider'
        raise RoutingPause('No authorized route can proceed because access was denied. Inspect access in Models; saved files, checks and usage are retained.', scope=scope)
    waits = [h["retry_at"] for h in provider_waits if h.get("cooldown_scope") in {"provider", "model", "account", "connection"} and (h.get("retry_known") or h.get('retry_scheduled')) and h["cooling_down"]]
    if round_state['probes'] >= route_schedule.BATCH_SIZE and candidates:
        raise RoutingPause('Checking more authorized routes automatically after a short backoff.', retry_at=route_schedule.retry_at(round_state), scope='probe_capacity')
    if waits:
        seconds = max(1, math.ceil(min(waits) - time.time()))
        scope = "provider" if any(h.get("cooldown_scope") == "provider" and h["cooling_down"] for h in provider_waits) else "model"
        message = f"The provider connection is cooling down. Retry in about {seconds} seconds. Other models on that connection were not tested or marked broken. Your chat, files, checks, and usage are saved." if scope == "provider" else f"Eligible models are cooling down. Earliest retry eligibility is in about {seconds} seconds. Saved work is kept."
        raise RoutingPause(message, retry_at=min(waits), scope=scope)
    if any(h.get("cooldown_scope") == "provider" and h["cooling_down"] and h not in access_blocked for h in provider_waits):
        reason = next((h.get('last_error') for h in provider_waits if h.get('cooldown_scope') == 'provider' and h['cooling_down'] and h not in access_blocked and h.get('last_error')), 'The provider is cooling down without a known retry time.')
        raise RoutingPause(reason + " Checking availability again automatically.", retry_at=time.time()+route_schedule.ROUND_SECONDS, scope="provider")
    allowed = [m for m in catalog['models'] if access_policy.eligible(m, policy) and not m.get('local')]
    if allowed and all(m['id'] in runtime.failed_models or (role == 'reviewer' and m['id'] in used) for m in allowed) and not any(route_schedule.rejected(v) for v in rejected_probes.values()):
        raise RoutingPause('No eligible independent model remains after response failures. Choose another model in Models; saved work and passing checks are kept.')
    retry_times = [v['retry_at'] for v in rejected_probes.values() if route_schedule.rejected(v)]
    retry = min(retry_times) if retry_times else time.time() + route_schedule.ROUND_SECONDS
    raise RoutingPause('No authorized route is ready yet. Saved work is queued; route availability will be checked automatically.', retry_at=retry, scope='model')


def coordinator_messages(task):
    # No file listing, diff, tool output, or large reasoning history on the laptop.
    latest = task.get("requests", [task["prompt"]])[-1]
    history = [{"role": "user" if e["kind"] == "user" else "assistant", "content": str(e["detail"])[:600]}
               for e in task["events"] if e["kind"] in {"user", "assistant"}][-4:]
    return [{"role": "system", "content": COORDINATOR_SYSTEM}] + history + [{"role": "user", "content": latest}]
