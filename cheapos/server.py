"""Loopback-only HTTP API and static UI. No hosted identity or external dependencies."""

import json
import secrets
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import __version__
from .gateways import gateway_for
from .providers import validate_provider, ProviderError


def public_task(task, summary=False):
    if summary:
        return {key: task[key] for key in ("id", "title", "source", "status", "created_at", "updated_at", "demo", "usage")}
    return {key: value for key, value in task.items() if key not in {"messages", "fixture_phase", "in_flight", "turn_start_patch"}}


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, directory, engine):
        self.directory = Path(directory).resolve()
        self.engine = engine
        self.token = secrets.token_urlsafe(32)
        super().__init__(address, LocalHandler)


class LocalHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(args[2].directory), **kwargs)

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def trusted(self, mutation=False):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if host not in hosts or (origin is not None and origin != "http://" + host):
            self.reply({"error": "Only same-origin localhost requests are allowed"}, 403)
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.reply({"error": "Cross-site requests are not allowed"}, 403)
            return False
        if mutation and not secrets.compare_digest(self.headers.get("X-CheapOS-Token", ""), self.server.token):
            self.reply({"error": "Local request token expired. Refresh the app."}, 403)
            return False
        return True

    def reply(self, value, status=200):
        data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self):
        if not self.trusted():
            return
        if not self.static_allowed():
            self.send_error(404)
            return
        super().do_HEAD()

    def static_allowed(self):
        # The app's own assets are the entire public filesystem surface.
        relative = unquote(urlsplit(self.path).path).lstrip("/") or "index.html"
        target = self.server.directory / relative
        return relative in {"index.html", "app.js", "guidance.js", "styles.css"} and not target.is_symlink() and target.is_file()

    def do_GET(self):
        if not self.trusted():
            return
        path = urlsplit(self.path).path
        engine = self.server.engine
        try:
            if path == "/api/bootstrap":
                self.reply({"app": "CheapOS", "version": __version__, "token": self.server.token, "config": engine.configuration(), "gateway": engine.gateway.snapshot(), "tasks": engine.store.list(summary=True), "projects": engine.projects(), "preferences": engine.preferences()})
            elif path == "/api/projects":
                self.reply(engine.projects())
            elif path == "/api/gateway":
                self.reply(engine.gateway.snapshot())
            elif path == "/api/gateway/models":
                self.reply(engine.gateway.catalog())
            elif path == "/api/tasks":
                self.reply(engine.store.list(summary=True))
            elif path.startswith("/api/tasks/"):
                parts = path.strip("/").split("/")
                task = engine.store.get(parts[2])
                if len(parts) == 3:
                    self.reply(public_task(task))
                elif len(parts) == 4 and parts[3] == "patch":
                    data = task["patch"].encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/x-patch; charset=utf-8")
                    self.send_header("Content-Disposition", f'attachment; filename="cheapos-{task["id"][:8]}.patch"')
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.reply({"error": "Route not found"}, 404)
            elif self.static_allowed():
                super().do_GET()
            else:
                self.reply({"error": "Not found"}, 404)
        except ValueError as error:
            self.reply({"error": str(error)}, 404)

    def do_POST(self):
        if not self.trusted(mutation=True):
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1_000_000:
                raise ValueError("Request body must be under 1 MB")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Expected JSON")
            values = json.loads(self.rfile.read(length))
            if not isinstance(values, dict):
                raise ValueError("Expected a JSON object")
            engine = self.server.engine
            path = urlsplit(self.path).path
            if path == "/api/config":
                result = engine.configure(values)
            elif path == "/api/projects":
                result = engine.open_project(values)
            elif path == "/api/preferences":
                result = engine.save_preferences(values)
            elif path == "/api/gateway/config":
                with engine.lock:
                    if any(r.thread and r.thread.is_alive() for r in engine.runtimes.values()):
                        raise ValueError("Pause the active task before changing its gateway connection")
                    result = engine.gateway.configure(values)
            elif path in {"/api/gateway/start", "/api/gateway/refresh"}:
                result = engine.gateway.refresh(start=path.endswith("/start"))
            elif path == "/api/gateway/stop":
                with engine.lock:
                    if any(r.thread and r.thread.is_alive() for r in engine.runtimes.values()):
                        raise ValueError("Pause the active task before stopping OmniRoute")
                    result = engine.gateway.stop_owned()
            elif path == "/api/models":
                role = values.get("role")
                if role not in {"worker", "reviewer"}:
                    raise ValueError("Choose a worker or reviewer connection")
                config = validate_provider(values.get("config"), role)
                result = {"models": gateway_for(config, engine.provider_key(role, config)).list_models()}
            elif path == "/api/tasks":
                result = public_task(engine.create(values))
            elif path == "/api/demo":
                result = public_task(engine.create_demo())
            elif path.startswith("/api/tasks/"):
                parts = path.strip("/").split("/")
                if len(parts) != 4:
                    raise ValueError("Unknown task action")
                task_id, action = parts[2:]
                if action == "start":
                    result = public_task(engine.start(task_id, values))
                elif action == "message":
                    if not isinstance(values.get("message"), str):
                        raise ValueError("Provide a message")
                    result = public_task(engine.start(task_id, {"message": values["message"]}))
                elif action == "limits":
                    result = public_task(engine.update_limits(task_id, values))
                elif action == "stop":
                    result = engine.stop(task_id)
                elif action == "approval":
                    if not isinstance(values.get("approved"), bool):
                        raise ValueError("Provide an approval decision")
                    result = engine.approve_check(task_id, values["approved"])
                else:
                    raise ValueError("Unknown task action")
            else:
                self.reply({"error": "Route not found"}, 404)
                return
            self.reply(result)
        except (ValueError, TypeError, KeyError, OSError, ProviderError) as error:
            self.reply({"error": str(error)[:1000]}, 400)
        except Exception:
            self.reply({"error": "The local server could not complete this action"}, 500)
