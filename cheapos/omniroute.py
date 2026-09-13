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

from .gateways import OmniRouteGateway
from .model_pool import FreeModelPool
from .providers import ProviderError
from .storage import write_json
from . import access_policy


DEFAULT_SETTINGS = {"base_url": "http://127.0.0.1:20128/v1", "auto_start": True, "keep_running": True}


def validate_settings(values):
    if not isinstance(values, dict):
        raise ValueError("Gateway settings must be an object")
    settings = {key: values.get(key, default) for key, default in DEFAULT_SETTINGS.items()}
    url = settings["base_url"]
    if not isinstance(url, str):
        raise ValueError("Provide a local OmniRoute API URL")
    parsed = urlsplit(url.rstrip("/"))
    try:
        port = parsed.port if parsed.port is not None else 80
    except ValueError:
        raise ValueError("Invalid OmniRoute port") from None
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path != "/v1" or not 1 <= port <= 65535):
        raise ValueError("Use a loopback OmniRoute URL such as http://127.0.0.1:20128/v1")
    for key in ("auto_start", "keep_running"):
        if not isinstance(settings[key], bool):
            raise ValueError("Gateway startup preferences must be true or false")
    key = values.get("api_key")
    if key is not None and (not isinstance(key, str) or len(key) > 4096 or "\n" in key or "\r" in key):
        raise ValueError("Invalid gateway client API key")
    settings["base_url"] = url.rstrip("/")
    if 'connection_revision' in values:
        revision = values['connection_revision']
        if not isinstance(revision, str) or len(revision) != 32 or any(c not in '0123456789abcdef' for c in revision):
            raise ValueError('Invalid connection revision')
        settings['connection_revision'] = revision
    if 'included_models' in values:
        settings['included_models'] = access_policy.model_ids(values['included_models'])
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
    def __init__(self, directory):
        self.path = Path(directory) / "gateway.json"
        self.pool = FreeModelPool(directory)
        try:
            self.settings = validate_settings(json.loads(self.path.read_text()))
        except (OSError, ValueError, TypeError):
            self.settings = dict(DEFAULT_SETTINGS)
        if 'connection_revision' not in self.settings:
            self.settings.update(connection_revision=uuid.uuid4().hex, included_models=[])
            write_json(self.path, self.settings)
        self.api_key = os.environ.get("CHEAPOS_GATEWAY_API_KEY", "")
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
                    "free_count": sum(m.get("free") and m.get("tool_calling") is True and not m.get("local") for m in self.models),
                    "dashboard_url": self.settings["base_url"][:-3], "diagnostic_code": self.diagnostic_code}

    def configure(self, values):
        with self.lock:
            if not isinstance(values, dict):
                raise ValueError("Gateway settings must be an object")
            if 'connection_revision' in values:
                raise ValueError('Connection revision is read-only')
            settings = validate_settings({**self.settings, **values})
            connection_changed = (settings['base_url'] != self.settings['base_url']
                                  or ('api_key' in values and values['api_key'] != self.api_key))
            if 'included_models' in values:
                if connection_changed or values.get('expected_connection_revision') != self.settings['connection_revision']:
                    raise ValueError('Inspect the current connection before authorizing included model access')
                wanted = access_policy.model_ids(values['included_models'])
                if any(m['id'] in wanted and (m.get('local') or m.get('provider') == 'combo') for m in self.models):
                    raise ValueError('Included access requires exact remote model IDs, not local or combined routes')
            if connection_changed:
                settings.update(connection_revision=uuid.uuid4().hex, included_models=[])
            if self.thread and self.thread.is_alive():
                raise ValueError("Wait for the current gateway connection attempt to finish")
            if settings["base_url"] != self.settings["base_url"]:
                if self.process is not None and self.process.poll() is None:
                    raise ValueError("Stop the OmniRoute instance started by cheapoS before changing its endpoint")
                self.models = []
                self.state = "unchecked"
                self.revision += 1
                # A credential for the previous origin must not follow an endpoint change.
                self.api_key = ""
            if "api_key" in values:
                self.api_key = values["api_key"]
            write_json(self.path, settings)
            self.settings = settings
            self.revision += 1
            return self.snapshot()

    def refresh(self, start=False):
        with self.lock:
            if self.closed.is_set() or (self.thread and self.thread.is_alive()):
                return self.snapshot()
            self.state, self.message = "checking", "Checking the local OmniRoute endpoint"
            self.thread = threading.Thread(target=self._connect, args=(start,), daemon=True)
            self.thread.start()
            return self.snapshot()

    def startup(self):
        return self.refresh(start=self.settings["auto_start"])

    def _probe(self):
        config = {"base_url": self.settings["base_url"], "key_env": "CHEAPOS_GATEWAY_API_KEY"}
        return OmniRouteGateway(config, self.api_key).list_models()

    def _port_open(self):
        parsed = urlsplit(self.settings["base_url"])
        try:
            with socket.create_connection((parsed.hostname, parsed.port or 80), timeout=1):
                return True
        except OSError:
            return False

    def _set_state(self, state, message, models=None, code=None):
        with self.lock:
            self.state, self.message = state, message
            self.diagnostic_code = code
            if models is not None:
                self.models = models
            elif state != "starting":
                self.models = []
            self.revision += 1
            self.checked_at = time.monotonic()

    def _connect(self, start):
        try:
            try:
                models = self._probe()
                self._set_state("ready", "OmniRoute is connected. Model availability is checked when a task runs.", models)
                return
            except ProviderError as error:
                detail = str(error)
                if self._port_open():
                    state = "auth_required" if error.code == "client_key_rejected" else "unavailable"
                    self._set_state(state, detail, code=error.code)
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
        if self.thread:
            self.thread.join(5)
        with self.lock:
            if not self.settings["keep_running"] and self.process is not None:
                self._terminate(self.process)

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
                model["health"] = self.pool.observation(self.settings["base_url"], model["id"])
            return {"models": models, "revision": self.revision + self.pool.revision, "status": self.state}
