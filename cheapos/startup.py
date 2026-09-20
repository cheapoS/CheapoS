"""Discover a free worker and verify it with a bounded, repository-free greeting."""

import copy
import json
import math
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.request import ProxyHandler, Request, build_opener

from .gateways import gateway_for
from .providers import NoRedirects, ProviderError, is_local_ollama, reconcile, reserve, validate_provider
from .storage import write_json
from . import metrics
from .served_identity import apply, metadata


DEFAULTS = {"enabled": True, "allow_cloud": False}
GREETING = [
    {"role":"system", "content":"You are cheapoS, a coding assistant. Greet the user in one short sentence and ask what they would like to work on. The interface handles project selection, so do not tell them to open a project. You have not read any files or verified any coding tools. Do not claim otherwise."},
    {"role":"user", "content":"Say hi and ask what I would like to work on."},
]


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def local_json(url, body=None):
    request = Request(url, data=json.dumps(body).encode() if body is not None else None,
                      headers={"Content-Type":"application/json", "Accept":"application/json"})
    with build_opener(NoRedirects(), ProxyHandler({})).open(request, timeout=4) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Local model metadata is too large")
        return json.loads(raw)


def local_candidates(saved=None, preferred=()):
    """Read only installed Ollama metadata; never pull a model or start inference."""
    base = saved["base_url"] if saved and is_local_ollama(saved) else "http://127.0.0.1:11434/v1"
    origin = base.rsplit("/v1", 1)[0]
    try:
        models = local_json(origin + "/api/tags").get("models", [])
        try:
            running = {m.get("name") for m in local_json(origin + "/api/ps").get("models", [])}
        except (OSError, ValueError, TypeError, AttributeError):
            running = set()
        models = [m for m in models if isinstance(m, dict) and isinstance(m.get("name"), str)]
        models.sort(key=lambda m:(m["name"] not in preferred, m["name"] != (saved or {}).get("model"), m["name"] not in running, m.get("size", 0)))
        candidates = []
        for model in models[:6]:
            name = model["name"]
            try:
                details = local_json(origin + "/api/show", {"model":name})
                if details.get("remote_host") or details.get("remote_model") or "cloud" in name.split(":")[-1]:
                    continue
                capabilities = details.get("capabilities", [])
            except (OSError, ValueError, TypeError, AttributeError):
                continue
            if "completion" not in capabilities or "tools" not in capabilities:
                continue
            config = validate_provider({"base_url":base, "model":name, "input_rate":0, "output_rate":0, "key_env":"CHEAPOS_LOCAL_API_KEY"}, "worker")
            candidates.append({"config":config, "local":True, "transport":"Local Ollama"})
        return candidates
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def catalog_candidates(models, base_url, gateway):
    result = []
    for model in models:
        if not model.get("free") or model.get("tool_calling") is not True or model.get("health", {}).get("cooling_down"):
            continue
        config = validate_provider({"base_url":base_url, "gateway":gateway, "model":model["id"], "input_rate":0, "output_rate":0}, "worker")
        result.append({"config":config, "local":bool(model.get("local")), "transport":"OmniRoute" if gateway == "omniroute" else "Direct provider"})
    return sorted(result, key=lambda c:(not c["local"], c["config"]["model"]))


class StartupManager:
    def __init__(self, engine):
        self.engine = engine
        self.path = engine.store.root / "startup.json"
        try:
            saved = json.loads(self.path.read_text())
            self.settings = {key:saved[key] if isinstance(saved.get(key), bool) else default for key, default in DEFAULTS.items()}
        except (OSError, ValueError, TypeError, AttributeError):
            self.settings = dict(DEFAULTS)
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.closed = False
        self.thread = None
        self.state = {"session_id":uuid.uuid4().hex, "status":"idle", "message":"Free model startup has not run yet.", "model":None, "thinking":"", "content":"", "attempts":[], "started_at":None}

    def busy(self):
        return self.thread is not None and self.thread.is_alive()

    def snapshot(self):
        with self.lock:
            return {**copy.deepcopy(self.state), "settings":dict(self.settings), "busy":self.busy()}

    def _set(self, **values):
        with self.lock:
            self.state.update(values)
            self.state["updated_at"] = timestamp()

    def configure(self, values):
        if any(key not in DEFAULTS or not isinstance(value, bool) for key, value in values.items()):
            raise ValueError("Startup preferences must be enabled/allow_cloud booleans")
        with self.engine.lock, self.lock:
            if self.busy():
                raise ValueError("Stop the current connection check before changing startup preferences")
            self.settings.update(values)
            write_json(self.path, self.settings)
        return self.snapshot()

    def start(self, automatic=False):
        with self.engine.lock, self.lock:
            if self.closed or self.busy():
                return self.snapshot()
            if automatic and not self.settings["enabled"]:
                self._set(status="disabled", message="Automatic free-model startup is off.")
                return self.snapshot()
            if self.engine.admission.snapshot()["active"]:
                raise ValueError("Wait for the active chat or pause it before testing a startup model")
            self.cancelled.clear()
            self._set(status="discovering", message="Looking for an available free model…", model=None, thinking="", content="", attempts=[], started_at=timestamp(), usage=None)
            self.thread = threading.Thread(target=self._run, args=(automatic,), daemon=True)
            self.thread.start()
        return self.snapshot()

    def stop(self):
        self.cancelled.set()
        if self.busy():
            self._set(status="stopping", message="Stopping the connection check. A stalled request can take 30 seconds to release.")
        return self.snapshot()

    def models_changed(self):
        self._set(status="configured", message="Your model choices are saved. A new connection check can verify a free worker.", model=None, content="", thinking="")

    def shutdown(self):
        self.closed = True
        self.cancelled.set()
        if self.thread:
            self.thread.join(2)

    def _check_stop(self):
        if self.cancelled.is_set():
            raise InterruptedError("Free-model connection check stopped.")

    def _omni(self):
        self._set(message="Connecting to OmniRoute…")
        gateway = self.engine.gateway
        if not gateway.snapshot()["busy"]:
            gateway.startup()
        deadline = time.monotonic() + 45
        while gateway.snapshot()["busy"] and time.monotonic() < deadline:
            self._check_stop()
            self.cancelled.wait(.1)
        self._check_stop()
        catalog = gateway.catalog()
        candidates = catalog_candidates(catalog["models"], gateway.settings["base_url"], "omniroute") if catalog["status"] == "ready" else []
        for candidate in candidates:
            candidate["config"]["gateway_type"] = gateway.settings.get("gateway_type", "omniroute")
            candidate["transport"] = gateway.settings.get("gateway_type", "omniroute")
        return candidates

    def _candidates(self, saved):
        execution = self.engine.preferences()["execution"]
        # A fresh free-only work default is not consent for a cloud greeting.
        # Keep startup's local-first/allow-cloud rule until placement is chosen.
        settings = getattr(self.engine, 'settings_store', None)
        if settings and settings.read().get('placement_confirmed') is False:
            execution = {**execution, 'mode': 'manual'}
        if execution["mode"] == "remote":
            yield from (c for c in self._omni() if not c["local"])
            return
        if execution["mode"] in {"delegate", "local"}:
            selected = execution["local_model"]
            installed = local_candidates(saved, preferred=[selected])
            yield from (c for c in installed if not selected or c["config"]["model"] == selected)
            return
        locals_ = local_candidates(saved)
        omni = None
        # A saved explicit free choice has priority. A catalog entry is still required.
        if saved:
            if is_local_ollama(saved):
                for candidate in locals_:
                    if candidate["config"]["model"] == saved["model"]:
                        yield candidate
            elif saved.get("gateway") == "omniroute" and self.engine.gateway.matches(saved["base_url"]):
                omni = self._omni()
                for candidate in omni:
                    if candidate["config"]["model"] == saved["model"]:
                        yield candidate
        yield from locals_
        if omni is None:
            omni = self._omni()
        for candidate in omni:
            if candidate["local"] or self.settings["allow_cloud"]:
                yield candidate

    def _record(self, account):
        self.engine.store.lifetime.ingest_task(account)
        self._set(usage=copy.deepcopy(account["usage"]))
        # No project contents, credentials, or prompts enter this connection-check record.
        record = self.snapshot()
        record.pop("thinking", None)
        record.pop("busy", None)
        write_json(self.engine.store.root / "startup-last.json", record)

    def _attempt(self, attempt, **values):
        with self.lock:
            attempt.update(values)

    def _run(self, automatic):
        account = {"limits":{"output_tokens":512, "dollars":0}, "usage":{"worker":{"tokens":0,"cost":0}, "reviewer":{"tokens":0,"cost":0}, "cost":0, "uncertain_requests":0, "estimated_requests":0}}
        account.update(id="startup-"+uuid.uuid4().hex, metrics_schema=1, created_at=timestamp(), request_metrics=[], synthetic=self.engine.provider_factory is not None)
        try:
            saved = copy.deepcopy(self.engine.config.get("worker"))
            if saved and self.engine.preferences()["execution"]["mode"] == "manual" and (saved["input_rate"] or saved["output_rate"] or saved["model"].startswith("auto/")):
                if automatic:
                    self._set(status="configured", message="Your saved model is selected. Automatic greetings only use verified free or local models.")
                    return
                saved = None  # The user explicitly clicked Connect a free model.
            seen = set()
            for candidate in self._candidates(saved):
                self._check_stop()
                config = candidate["config"]
                identity = (config["base_url"], config["model"])
                if identity in seen:
                    continue
                if len(seen) >= 3:
                    break
                seen.add(identity)
                self._set(status="connecting", message="Asking the model to say hello…", model={"id":config["model"], "transport":candidate["transport"], "local":candidate["local"]}, thinking="", content="")
                attempt = {"model":config["model"], "transport":candidate["transport"], "status":"connecting", "started_at":timestamp()}
                with self.lock:
                    self.state["attempts"].append(attempt)
                self.engine.guard_route(config)
                reservation = reserve(account, config, GREETING, [], "worker")
                record = {'id':uuid.uuid4().hex,'role':'coordinator','purpose':'startup_greeting',
                          'model':config['model'],**metadata(config['model']),'requested_at':timestamp(),
                          'access_class':'local' if candidate['local'] else 'public_free',
                          'input_rate':config['input_rate'],'output_rate':config['output_rate'],
                          'reservation':{k:reservation[k] for k in ('tokens','cost','prompt_tokens','completion_tokens')},
                          'reservation_tokens':reservation['tokens'],'reservation_cost':reservation['cost'],
                          'cost_provenance':'uncertain_reservation','dispatched':False,'status':'pending',
                          'synthetic':self.engine.provider_factory is not None}
                # Greeting accounting historically used worker; retain that role
                # for consistency with the existing cumulative account buckets.
                record['role']='worker'
                from .request_health import route_metadata
                record.update(route_metadata(config, local=candidate['local']))
                account['request_metrics'].append(record)
                self._record(account)
                def emit(kind, value):
                    self._check_stop()
                    if kind in {"thinking", "answer"}:
                        key = "thinking" if kind == "thinking" else "content"
                        with self.lock:
                            self._set(**{key:(self.state[key] + value)[:4000]})
                try:
                    provider = self.engine.provider_factory("worker", config) if self.engine.provider_factory else gateway_for(self.engine.gateway_config(config), self.engine.provider_key("worker", config))
                    record["dispatched"]=True
                    self._record(account)
                    message, usage = provider.greet(GREETING, emit, self.cancelled.is_set)
                    known = reconcile(account, config, reservation, usage)
                    apply(record,usage)
                    metrics.record_usage(record,usage,known)
                    metrics.record_accounted(record,config,reservation,usage,known)
                    record["status"]="responded"
                    reported_cost = usage.get("cost")
                    if not known and isinstance(reported_cost, (int, float)) and not isinstance(reported_cost, bool) and math.isfinite(reported_cost) and reported_cost > 0:
                        account["usage"]["cost"] += reported_cost
                        account["usage"]["worker"]["cost"] += reported_cost
                    self._check_stop()
                    if account["usage"]["cost"] > 0:
                        with self.lock:
                            self.settings["enabled"] = False
                            write_json(self.path, self.settings)
                        self._attempt(attempt, status="failed", error="The route reported a charge; automatic startup is now off.")
                        self._set(status="unavailable", message=attempt["error"], content="")
                        return
                    content = message.get("content")
                    if not known or not isinstance(content, str) or not content.strip() or message.get("tool_calls"):
                        raise ProviderError("The greeting did not return a complete answer and token usage. No tools were executed.")
                    # In delegate/remote mode, dynamic routing evaluates and selects models
                    # across the gateway catalog. Do not permanently pin the greeting model to config.json.
                    with self.engine.lock:
                        self._check_stop()
                        selected = copy.deepcopy(self.engine.config)
                        selected["worker"] = config
                        if not selected.get("reviewer"):
                            selected["reviewer"] = validate_provider({**config, "key_env":config["key_env"]}, "reviewer")
                        self.engine.remember_provider_defaults(selected)
                    self._attempt(attempt, status="ready", finished_at=timestamp())
                    self._set(status="ready", message="The model answered. Open a project to start.", content=content.strip()[:2000], thinking="", verified_at=timestamp())
                    return
                except ProviderError as error:
                    record['status']='failed'
                    if isinstance(error.usage,dict) and error.usage and not record.get('usage_reconciled'):
                        usage=error.usage
                        known=reconcile(account,config,reservation,usage)
                        apply(record,usage)
                        metrics.record_usage(record,usage,known)
                        metrics.record_accounted(record,config,reservation,usage,known)
                        extra=max(0,(metrics.number(usage.get('cost')) or 0)-reservation['cost']) if not known else 0
                        account['usage']['cost']+=extra
                        account['usage']['worker']['cost']+=extra
                    self._attempt(attempt, status="failed", error=str(error)[:500], finished_at=timestamp())
                    self._set(content="", thinking="")
                finally:
                    self._record(account)
            detail = "No free model answered successfully." if seen else "No eligible free model is available yet."
            self._set(status="unavailable", message=detail + (" Connect a model in OmniRoute or start Ollama, then try again." if self.settings["allow_cloud"] else " Start Ollama, or enable free cloud models through OmniRoute."), content="", thinking="")
        except InterruptedError:
            self._set(status="stopped", message="Connection check stopped. Try again when you’re ready.", content="", thinking="")
        except Exception:
            self._set(status="unavailable", message="The connection check could not finish. Check Models and try again.", content="", thinking="")
        finally:
            self._record(account)
