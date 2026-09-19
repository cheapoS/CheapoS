"""Optional local OmniRoute lifecycle. Never install software or resume model work."""

import copy
import json
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .gateways import OmniRouteGateway, OpenAICompatibleGateway
from .model_pool import FreeModelPool
from .providers import ProviderError
from .storage import write_json
from .credentials import CredentialStore, CredentialError
from . import access_policy, route_health


GATEWAY_TYPES = {
    "omniroute": "OmniRoute",
    "cliproxyapi": "CLIProxyAPI",
    "9router": "9Router",
    "litellm": "LiteLLM",
    "ollama": "Ollama",
    "vllm": "vLLM",
    "lmstudio": "LM Studio",
    "localai": "LocalAI",
    "compatible": "OpenAI-compatible",
}

GATEWAY_DEFAULT_URLS = {
    "omniroute": "http://127.0.0.1:20128/v1",
    "cliproxyapi": "http://127.0.0.1:8317/v1",
    "9router": "http://127.0.0.1:20128/v1",
    "litellm": "http://127.0.0.1:4000/v1",
    "ollama": "http://127.0.0.1:11434/v1",
    "vllm": "http://127.0.0.1:8000/v1",
    "lmstudio": "http://127.0.0.1:1234/v1",
    "localai": "http://127.0.0.1:8080/v1",
    "compatible": "http://127.0.0.1:8000/v1",
}


def register_gateway_type(type_id, label, default_url="http://127.0.0.1:8000/v1"):
    """Register a new gateway type definition dynamically."""
    GATEWAY_TYPES[type_id] = label
    GATEWAY_DEFAULT_URLS[type_id] = default_url


def gateway_types_catalog():
    return [{"id": k, "label": label, "default_url": GATEWAY_DEFAULT_URLS.get(k, "http://127.0.0.1:8000/v1"), "default_name": label}
            for k, label in GATEWAY_TYPES.items()]

DEFAULT_SETTINGS = {"name": "OmniRoute", "enabled": True, "quota_groups": {}, "gateway_type": "omniroute", "base_url": "http://127.0.0.1:20128/v1", "auto_start": True, "keep_running": True, "remember_key": False}


def validate_settings(values):
    if not isinstance(values, dict):
        raise ValueError("Gateway settings must be an object")
    settings = {key: values.get(key, default) for key, default in DEFAULT_SETTINGS.items()}
    if settings["gateway_type"] not in GATEWAY_TYPES:
        raise ValueError("Choose a supported gateway type")
    if not isinstance(settings["name"], str) or not 1 <= len(settings["name"].strip()) <= 80:
        raise ValueError("Name this gateway connection (up to 80 characters)")
    settings["name"] = settings["name"].strip()
    groups = settings["quota_groups"]
    if not isinstance(groups, dict) or len(groups) > 50 or any(not isinstance(k,str) or not isinstance(v,str) or not k or not v or len(k)>100 or len(v)>100 for k,v in groups.items()):
        raise ValueError("Quota groups must map provider prefixes to account labels")
    url = settings["base_url"]
    if not isinstance(url, str):
        raise ValueError("Provide a local gateway API URL")
    parsed = urlsplit(url.rstrip("/"))
    try:
        port = parsed.port if parsed.port is not None else 80
    except ValueError:
        raise ValueError("Invalid gateway port") from None
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path != "/v1" or not 1 <= port <= 65535):
        raise ValueError("Use a loopback gateway URL such as http://127.0.0.1:20128/v1")
    for key in ("auto_start", "keep_running", "remember_key", "enabled"):
        if not isinstance(settings[key], bool):
            raise ValueError("Gateway startup preferences must be true or false")
    if settings["gateway_type"] != "omniroute":
        settings["auto_start"] = False
    key = values.get("api_key")
    if 'api_key' in values and (not isinstance(key, str) or len(key) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in key)):
        raise ValueError("Invalid gateway client API key")
    settings["base_url"] = url.rstrip("/")
    if 'connection_revision' in values:
        revision = values['connection_revision']
        if not isinstance(revision, str) or len(revision) != 32 or any(c not in '0123456789abcdef' for c in revision):
            raise ValueError('Invalid connection revision')
        settings['connection_revision'] = revision
    if 'included_models' in values:
        settings['included_models'] = access_policy.model_ids(values['included_models'])
    if "tool_models" in values:
        settings["tool_models"] = access_policy.model_ids(values["tool_models"])
    return settings


def find_executable():
    located = shutil.which("omniroute")
    if located:
        return located
    # Finder-launched Python often has a smaller PATH than an interactive shell.
    for filename in ("/opt/homebrew/bin/omniroute", "/usr/local/bin/omniroute"):
        if Path(filename).is_file() and os.access(filename, os.X_OK):
            return filename
    return None


class OmniRouteManager:
    def __init__(self, directory, credential_store=None, use_environment=True):
        self.path = Path(directory) / "gateway.json"
        self.credentials = credential_store if credential_store is not None else CredentialStore(directory)
        self.pool = FreeModelPool(directory)
        try:
            self.settings = validate_settings(json.loads(self.path.read_text()))
        except (OSError, ValueError, TypeError):
            self.settings = dict(DEFAULT_SETTINGS)
        if 'connection_revision' not in self.settings:
            self.settings.update(connection_revision=uuid.uuid4().hex, included_models=[])
            write_json(self.path, self.settings)
        self.api_key = os.environ.get("CHEAPOS_GATEWAY_API_KEY", "") if use_environment else ""
        self.key_source = 'environment' if self.api_key else 'none'
        self.key_error = None
        self._restore_key()
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.process = None
        self.thread = None
        self.models = []
        self.revision = 0
        self.checked_at = 0
        self.state = "unchecked"
        self.message = "Checking your local model gateway"
        self.diagnostic_code = None

    def _restore_key(self):
        if self.api_key or not self.settings['remember_key']:
            return
        try:
            key = self.credentials.get(self.settings['base_url'])
            validate_settings({'api_key':key or ''})
            self.api_key = key or ''
            self.key_source = 'saved' if key else 'none'
            self.key_error = None if key else 'The saved gateway key was not found. Enter it again and save it on this computer.'
        except ValueError:
            self.key_error = 'The saved gateway key could not be loaded. Unlock your credential store, then refresh the connection. CHEAPOS_GATEWAY_API_KEY can also supply a key at launch.'

    def key_storage(self):
        return {'available':bool(self.credentials.backend), 'backend':self.credentials.backend,
                'saved':self.settings['remember_key'], 'source':self.key_source, 'error':self.key_error}

    def matches(self, url):
        def identity(value):
            parsed = urlsplit(value)
            return (parsed.scheme, "loopback" if parsed.hostname in {"localhost", "127.0.0.1"} else parsed.hostname, parsed.port or 80, parsed.path.rstrip("/"))
        return identity(url) == identity(self.settings["base_url"])

    def snapshot(self):
        # The UI polls this endpoint. Refresh metadata only; never run inference here.
        if not self.closed.is_set() and self.state == "ready" and time.monotonic() - self.checked_at >= 300 and not (self.thread and self.thread.is_alive()):
            self.refresh()
        with self.lock:
            owned = self.process is not None and self.process.poll() is None
            return {"settings": dict(self.settings), "status": self.state, "message": self.message,
                    "busy": self.thread is not None and self.thread.is_alive(), "owned": owned,
                    "pid": self.process.pid if owned else None, "model_count": len(self.models),
                    "revision": self.revision + self.pool.revision, "key_configured": bool(self.api_key),
                    "key_storage": self.key_storage(),
                    "free_count": sum(m.get("free") and m.get("tool_calling") is True and not m.get("local") for m in self.models),
                    "dashboard_url": self.settings["base_url"][:-3], "diagnostic_code": self.diagnostic_code,
                    "gateway_types": gateway_types_catalog()}

    def configure(self, values):
        with self.lock:
            if not isinstance(values, dict):
                raise ValueError("Gateway settings must be an object")
            if 'connection_revision' in values:
                raise ValueError('Connection revision is read-only')
            settings = validate_settings({**self.settings, **values})
            endpoint_changed = (settings['base_url'] != self.settings['base_url']
                                or settings['gateway_type'] != self.settings['gateway_type'])
            if endpoint_changed and 'remember_key' not in values:
                settings['remember_key'] = False
            key = values.get('api_key', '' if endpoint_changed else self.api_key)
            if not key and not (self.settings['remember_key'] and not endpoint_changed and 'api_key' not in values):
                settings['remember_key'] = False
            connection_changed = (endpoint_changed or settings['quota_groups'] != self.settings.get('quota_groups', {})
                                  or ('api_key' in values and values['api_key'] != self.api_key))
            if 'included_models' in values:
                if connection_changed or values.get('expected_connection_revision') != self.settings['connection_revision']:
                    raise ValueError('Inspect the current connection before authorizing included model access')
                wanted = access_policy.model_ids(values['included_models'])
                if any(m['id'] in wanted and (m.get('local') or m.get('provider') == 'combo') for m in self.models):
                    raise ValueError('Included access requires exact remote model IDs, not local or combined routes')
            if "tool_models" in values and (connection_changed or values.get("expected_connection_revision") != self.settings["connection_revision"]):
                raise ValueError("Inspect the current connection before declaring tool support")
            if connection_changed:
                settings.update(connection_revision=uuid.uuid4().hex, included_models=[], tool_models=[])
            if self.thread and self.thread.is_alive():
                raise ValueError("Wait for the current gateway connection attempt to finish")
            if endpoint_changed:
                if self.process is not None and self.process.poll() is None:
                    raise ValueError("Stop the OmniRoute instance started by cheapoS before changing its endpoint")

            # Validate first, then update the OS store and settings together. Capture only
            # the affected slots so a disk failure can restore their previous values.
            updates = {}
            if self.settings['remember_key'] and (endpoint_changed or not settings['remember_key']):
                updates[self.settings['base_url']] = None
            if settings['remember_key'] and key and ('api_key' in values or not self.settings['remember_key'] or endpoint_changed):
                if self.key_source == 'environment' and 'api_key' not in values:
                    raise ValueError('Environment keys are not saved automatically. Enter a client key to remember it on this computer.')
                updates[settings['base_url']] = key
            previous = {url:self.credentials.get(url) for url in updates}
            changed = []
            try:
                for url, value in updates.items():
                    changed.append(url)  # Also recover an uncertain store operation (e.g. timeout).
                    if value is None: self.credentials.delete(url)
                    else: self.credentials.set(url, value)
                write_json(self.path, settings)
            except (OSError, ValueError):
                for url in reversed(changed):
                    try:
                        if previous[url] is None: self.credentials.delete(url)
                        else: self.credentials.set(url, previous[url])
                    except CredentialError:
                        self.key_error = 'Saving failed and credential recovery needs attention. Re-enter and save the gateway key before restarting.'
                raise
            if endpoint_changed:
                self.models = []
                self.state = "unchecked"
                self.revision += 1
            self.api_key = key
            if 'api_key' in values or endpoint_changed or self.key_source != 'environment':
                self.key_source = ('saved' if settings['remember_key'] else 'session') if key else 'none'
            if updates or 'api_key' in values or endpoint_changed:
                self.key_error = None
            self.settings = settings
            self.revision += 1
            return self.snapshot()

    def refresh(self, start=False):
        with self.lock:
            if self.closed.is_set() or (self.thread and self.thread.is_alive()):
                return self.snapshot()
            self.state, self.message = "checking", "Checking the local " + GATEWAY_TYPES[self.settings["gateway_type"]] + " endpoint"
            self.thread = threading.Thread(target=self._connect, args=(start,), daemon=True)
            self.thread.start()
            return self.snapshot()

    def startup(self):
        return self.refresh(start=self.settings["auto_start"])

    def _probe(self):
        self._restore_key()
        config = {"base_url": self.settings["base_url"], "key_env": "CHEAPOS_GATEWAY_API_KEY", "gateway_type": self.settings["gateway_type"]}
        adapter = OmniRouteGateway if self.settings["gateway_type"] == "omniroute" else OpenAICompatibleGateway
        models = adapter(config, self.api_key).list_models()
        for model in models:
            if model["id"] in self.settings.get("tool_models", []) and model.get("tool_calling") is None:
                model.update(tool_calling=True, tool_support_source="operator")
        return models

    def _port_open(self):
        parsed = urlsplit(self.settings["base_url"])
        try:
            with socket.create_connection((parsed.hostname, parsed.port or 80), timeout=1):
                return True
        except OSError:
            return False

    def _set_state(self, state, message, models=None, code=None):
        with self.lock:
            if self.closed.is_set():
                return
            self.state, self.message = state, message
            self.diagnostic_code = code
            if models is not None:
                self.models = route_health.metadata_facts(models, self.models, time.time())
            elif state != "starting":
                self.models = []
            self.revision += 1
            self.checked_at = time.monotonic()

    def _connect(self, start):
        if self.closed.is_set():
            return
        try:
            try:
                models = self._probe()
                self._set_state("ready", GATEWAY_TYPES[self.settings["gateway_type"]] + " is connected. Model availability is checked when a task runs.", models)
                return
            except ProviderError as error:
                if self.closed.is_set():
                    return
                detail = str(error)
                if self._port_open():
                    state = "auth_required" if error.code == "client_key_rejected" else "unavailable"
                    self._set_state(state, detail, code=error.code)
                    return
            if self.settings["gateway_type"] != "omniroute":
                self._set_state("offline", "Start " + GATEWAY_TYPES[self.settings["gateway_type"]] + " separately, then refresh this connection.")
                return
            if not start:
                self._set_state("offline", "OmniRoute is offline. Start it here or connect to another model endpoint.")
                return
            executable = find_executable()
            if not executable:
                self._set_state("not_installed", "OmniRoute was not found. Install it separately, or use a direct connection below.")
                return
            with self.lock:
                if self.closed.is_set():
                    return
                if self.process is not None and self.process.poll() is None:
                    self._set_state("unavailable", "The OmniRoute process is running but its API is unavailable. Open its dashboard to inspect it.")
                    return
                parsed = urlsplit(self.settings["base_url"])
                env = dict(os.environ)
                # Keep credentials in their owning process. OmniRoute loads its own provider configuration.
                for name in list(env):
                    if name.startswith("CHEAPOS_"):
                        env.pop(name)
                env.update({"OMNIROUTE_SERVER_HOST": "::1" if parsed.hostname == "::1" else "127.0.0.1",
                            "OMNIROUTE_NO_UPDATE_NOTIFIER": "1"})
                env["PATH"] = str(Path(executable).parent) + os.pathsep + env.get("PATH", "")
                self._set_state("starting", "Starting OmniRoute locally…")
                self.process = subprocess.Popen(
                    [executable, "serve", "--port", str(parsed.port or 80), "--no-open", "--no-tray", "--no-recovery"],
                    cwd=str(self.path.parent), env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                )
            deadline = time.monotonic() + 40
            while not self.closed.is_set() and time.monotonic() < deadline:
                try:
                    models = self._probe()
                    self._set_state("ready", "OmniRoute started by cheapoS. Ready to select models.", models)
                    return
                except ProviderError as error:
                    if error.code == "client_key_rejected":
                        self._set_state("auth_required", str(error), code=error.code)
                        return
                if self.process.poll() is not None:
                    self._set_state("error", "OmniRoute exited during startup. Run omniroute in a terminal to inspect the error.")
                    return
                self.closed.wait(.5)
            if not self.closed.is_set():
                self._set_state("unavailable", "OmniRoute is taking longer to start. Refresh the connection or open its dashboard.")
        except (OSError, ValueError):
            self._set_state("error", "OmniRoute could not be started. Check that its installed command runs in a terminal.")

    def stop_owned(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError("Wait for gateway startup to finish before stopping it")
            process = self.process
            if process is None or process.poll() is not None:
                raise ValueError("cheapoS can only stop an instance it started in this session")
        self._terminate(process)
        self._set_state("offline", "The OmniRoute instance started by cheapoS has stopped.")
        return self.snapshot()

    @staticmethod
    def _terminate(process):
        if process.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=6)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=2)
        except ProcessLookupError:
            pass

    def shutdown(self):
        self.closed.set()
        # Catalog probes run in a daemon thread and own no task writes. A slow
        # endpoint must not hold up backend restart. _connect checks closed
        # under this lock before spawning; keep owned-process cleanup intact.
        with self.lock:
            process = self.process if not self.settings["keep_running"] else None
        if process is not None:
            self._terminate(process)

    def catalog(self, fresh=False):
        if fresh and (self.state != "ready" or time.monotonic() - self.checked_at >= 300):
            self.refresh()
            if self.thread:
                self.thread.join(9)
        with self.lock:
            models = copy.deepcopy(self.models)
            for model in models:
                model['access_class'] = access_policy.classify(model, access_policy.snapshot(self.settings))
                model['access_source'] = 'operator_statement' if model['access_class'] == 'included' else 'catalog'
                if 'metadata_evidence' in model:
                    model['metadata_evidence']['stale'] = time.monotonic() - self.checked_at >= 300
                model["health"] = self.pool.observation(self.settings["base_url"], model["id"], self.settings.get("connection_revision"))
            return {"models": models, "revision": self.revision + self.pool.revision, "status": self.state}
