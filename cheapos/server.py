"""Loopback-only HTTP API and static UI. No hosted identity or external dependencies."""

import json
import hashlib
import secrets
import os
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qs

from . import __version__
from .gateways import gateway_for
from .providers import validate_provider, ProviderError
from . import metrics, check_output, branch_runs, branch_pause


def public_task(task, summary=False, store=None):
    from .working_state import project as working_state
    if store is not None:
        task = store.present(task)
    if task.get('branch_run',{}).get('pause_detail'):
        task={**task,'branch_run':dict(task['branch_run'])}
        detail=branch_pause.for_task(task)
        task['branch_run']['pause_detail']=detail
        task['error']=detail['explanation'] if detail else None
    if summary:
        result = {key: task[key] for key in ("id", "title", "source", "status", "created_at", "updated_at", "demo", "usage", "custom_title", "pinned", "archived_at", "trashed_at") if key in task}
        if "branch_run" in task:
            result["branch_run"] = branch_runs.summary(task["branch_run"])
        return result
    from .coordinator_dispatch import reassessment_availability
    return {**{key: value for key, value in task.items() if key not in {"messages", "worker_sessions", "conversation_state", "context_evidence", "fixture_phase", "in_flight", "turn_start_patch", "commit_pending", "request_metrics", "run_metrics"}}, "working_state":working_state(task), "coordinator_reassessment":reassessment_availability(task), "metrics":metrics.aggregate(task), "token_accounting":metrics.token_accounting(task), "commit_pending": bool(task.get("commit_pending")), "patch_digest": hashlib.sha256(task.get("patch", "").encode()).hexdigest()}


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
        return relative in {"index.html", "app.js", "guidance.js", "panels.js", "styles.css", "brand-icon.svg", "branch_ui.js", "branch_ui.css", "lifetime_usage.js", "lifetime_usage.css", "preview.js", "carto.js"} and not target.is_symlink() and target.is_file()

    def do_GET(self):
        if not self.trusted():
            return
        path = urlsplit(self.path).path
        while path.startswith("/api/api/"):
            path = path[4:]
        engine = self.server.engine
        try:
            if path == "/api/bootstrap":
                self.reply({"app": "CheapOS", "version": __version__, "token": self.server.token, "config": engine.configuration(), "gateway": engine.connections.snapshot(), "startup":engine.startup.snapshot(), "tasks": engine.store.visible(), "projects": engine.projects(), "hidden_projects": [p for p in engine.projects(include_hidden=True) if p["path"] in engine.hidden_project_paths()], "preferences": engine.preferences()})
            elif path == "/api/lifetime-usage":
                period=parse_qs(urlsplit(self.path).query).get("days", ["all"])[0]
                if period not in {"all","7","30"}:return self.reply({"error":"Usage period must be all, 7 or 30 days"},400)
                summary = engine.store.lifetime.summary(days=int(period) if period != "all" else "all")
                if hasattr(engine.store, 'club'):
                    summary['club'] = engine.store.club.get_status(summary)
                self.reply(summary)
            elif path == "/api/club/status":
                period=parse_qs(urlsplit(self.path).query).get("days", ["all"])[0]
                summary = engine.store.lifetime.summary(days=int(period) if period != "all" else "all")
                self.reply(engine.store.club.get_status(summary))
            elif path == "/api/admission":
                self.reply(engine.admission.snapshot())
            elif path.startswith('/api/tasks/') and path.endswith('/operator-recovery'):
                task_id=path.split('/')[3]
                task=engine.store.get(task_id)
                if 'branch_run' in task:
                    from .branch_operator import capabilities
                    self.reply(capabilities(engine.branch,task_id))
                else:self.reply(engine.operator_recovery(task_id))
            elif path == "/api/readiness":
                self.reply(engine.readiness.snapshot(refresh=parse_qs(urlsplit(self.path).query).get("refresh") == ["1"]))
            elif path == "/api/startup":
                self.reply({**engine.startup.snapshot(), "config":engine.configuration()})
            elif path == "/api/projects/hidden":
                self.reply([p for p in engine.projects(include_hidden=True) if p["path"] in engine.hidden_project_paths()])
            elif path == "/api/projects":
                self.reply(engine.projects())
            elif path == "/api/gateway":
                self.reply(engine.connections.snapshot())
            elif path == "/api/gateway/catalogs":
                self.reply({identity:{**m.snapshot(), **m.catalog()} for identity,m in engine.connections.managers.items()})
            elif path == "/api/gateway/models":
                self.reply(engine.gateway.catalog())
            elif path == "/api/role-mappings":
                self.reply(engine.role_mappings())
            elif path == "/api/role-mappings/effective":
                query_params = parse_qs(urlsplit(self.path).query)
                project = query_params.get("project", [None])[0]
                self.reply(engine.effective_role_mapping(project))
            elif path == "/api/tasks":
                self.reply(engine.store.visible(parse_qs(urlsplit(self.path).query).get("view", ["active"])[0]))
            elif path.startswith("/api/tasks/"):
                parts = path.strip("/").split("/")
                task = engine.store.get(parts[2])
                if len(parts) == 3:
                    self.reply(public_task(task, store=engine.store))
                elif len(parts) == 6 and parts[3] == "checks" and parts[5] == "raw":
                    data=check_output.raw(engine.store,task["id"],parts[4])
                    self.send_response(200)
                    self.send_header("Content-Type","text/plain; charset=utf-8")
                    self.send_header("Content-Length",str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                elif len(parts) == 4 and parts[3] == "permissions":
                    self.reply(engine.session_permissions(task["id"]))
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
        except Exception:
            # Return a usable response rather than dropping the recovery request.
            import traceback
            traceback.print_exc()
            self.reply({"error": "Could not load saved task details. Retry this action; saved work is unchanged."}, 500)

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
            while path.startswith("/api/api/"):
                path = path[4:]
            if path == "/api/restart":
                self.trusted(mutation=True)
                self.server.engine.shutdown()
                result = {"status": "restarting"}
                def restart_backend():
                    time.sleep(0.4)
                    self.server.server_close()
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                threading.Thread(target=restart_backend, daemon=True).start()
            elif path == "/api/role-mappings":
                result = engine.save_role_mappings(values)
            elif path == "/api/role-mappings/effective":
                query_params = parse_qs(urlsplit(self.path).query)
                project = query_params.get("project", [None])[0]
                result = engine.effective_role_mapping(project)
            elif path == "/api/config":
                result = engine.configure(values)
            elif path == "/api/startup/config":
                result = engine.startup.configure(values)
            elif path == "/api/startup/start":
                result = engine.startup.start()
            elif path == "/api/startup/stop":
                result = engine.startup.stop()
            elif path == "/api/projects/carto":
                from .workspace import Workspace
                source = str(Workspace.project_root(values.get('repository', '')))
                if source not in {p['path'] for p in engine.projects(include_hidden=True)}:
                    raise ValueError('Choose a registered project')
                if 'enabled' in values: engine.carto.configure(source, values['enabled'])
                result = {**engine.carto.status(source), 'index':engine.carto.context(source,source,rebuild=values.get('rebuild') is True)}
            elif path == "/api/projects/preview":
                result = engine.previews.settings(values)
            elif path == "/api/projects/hide":
                result = engine.hide_project(values)
            elif path == "/api/projects":
                result = engine.open_project(values)
            elif path == "/api/preferences":
                result = engine.save_preferences(values)
            elif path == "/api/club/pair":
                self.trusted(mutation=True)
                result = engine.store.club.start_pairing(engine.store.lifetime)
            elif path == "/api/club/check":
                self.trusted(mutation=True)
                result = engine.store.club.check_pairing()
            elif path == "/api/club/link":
                self.trusted(mutation=True)
                result = engine.store.club.link(values)
            elif path == "/api/club/sync":
                self.trusted(mutation=True)
                if "enabled" in values:
                    result = engine.store.club.set_sync(values["enabled"],values.get("share_models"))
                else:
                    result = engine.store.club.sync_now(engine.store.lifetime, values.get("period", "all"))
            elif path == "/api/club/disconnect":
                self.trusted(mutation=True)
                result = engine.store.club.disconnect()
            elif path == "/api/gateway/select":
                with engine.lock:
                    engine.gateway = engine.connections.select(values.get('connection_id'))
                    result = engine.connections.snapshot()
            elif path == "/api/gateway/add":
                with engine.lock:
                    identity = engine.connections.add(values)
                    engine.gateway = engine.connections.select(identity)
                    result = engine.connections.snapshot()
            elif path == "/api/gateway/config":
                with engine.lock:
                    if engine.startup.busy():
                        raise ValueError("Stop the startup connection check before changing its gateway")
                    if engine.admission.snapshot()['active']:
                        raise ValueError("Pause the active task before changing its gateway connection")
                    engine.gateway.configure(values)
                    result = engine.connections.snapshot()
            elif path in {"/api/gateway/start", "/api/gateway/refresh"}:
                result = engine.gateway.refresh(start=path.endswith("/start"))
            elif path == "/api/gateway/stop":
                with engine.lock:
                    if engine.startup.busy():
                        raise ValueError("Stop the startup connection check before stopping its gateway")
                    if engine.admission.snapshot()['active']:
                        raise ValueError("Pause the active task before stopping OmniRoute")
                    result = engine.gateway.stop_owned()
            elif path == "/api/models":
                role = values.get("role")
                if role not in {"worker", "reviewer", "planner"}:
                    raise ValueError("Choose a worker, reviewer or planner connection")
                config = validate_provider(values.get("config"), role)
                engine.guard_route(config)
                result = {"models": gateway_for(engine.gateway_config(config), engine.provider_key(role, config)).list_models()}
            elif path == "/api/branch-runs/project":
                result = engine.branch.project(values)
            elif path == "/api/branch-runs/plan":
                result = engine.branch.plan(values)
            elif path == "/api/branch-runs/plan-start":
                result = engine.branch.plan(values, background=True)
            elif path == "/api/branch-runs/plan-stop":
                result = engine.branch.stop_plan(values)
            elif path == "/api/branch-runs/prepare":
                result = engine.branch.prepare(values)
            elif path == "/api/tasks":
                result = public_task(engine.create(values))
            elif path == "/api/trash/empty":
                if values:
                    raise ValueError("This action does not accept fields")
                engine.empty_trash()
                result = {"status": "ok"}
            elif path == "/api/demo":
                result = public_task(engine.create_demo())
            elif path == "/api/sample":
                result = public_task(engine.create_sample())
            elif path.startswith("/api/tasks/"):
                parts = path.strip("/").split("/")
                if len(parts) != 4:
                    raise ValueError("Unknown task action")
                task_id, action = parts[2:]
                if action in {"preview-start", "preview-stop", "preview-status"}:
                    result = engine.previews.action(task_id, action, values)
                elif action in {"trash", "restore"}:
                    if values:
                        raise ValueError("This action does not accept fields")
                    result = public_task(engine.trash_task(task_id) if action == "trash" else engine.restore_task(task_id))
                elif action == "metadata":
                    result = public_task(engine.update_task_metadata(task_id, values))
                elif action == "branch-start":
                    result = public_task(engine.branch.authorize(task_id, values, background=True))
                elif action in {"branch-final-preview", "branch-final-diff", "branch-merge", "branch-revise", "branch-final-recheck", "branch-update"}:
                    from . import branch_completion
                    operation = {"branch-final-preview":"preview", "branch-final-diff":"diff", "branch-merge":"merge", "branch-revise":"revise", "branch-final-recheck":"recheck", "branch-update":"update_branch"}[action]
                    result = getattr(branch_completion, operation)(engine.branch, task_id, values, **({'background': True} if operation == 'merge' else {}))
                    if isinstance(result, dict) and "branch_run" in result: result = public_task(result)
                elif action == "branch-resolve-conflicts":
                    from .branch_conflicts import start
                    result = start(engine.branch, task_id, values)
                elif action == "branch-proposal-edit":
                    result = engine.branch.reprepare(task_id, values)
                elif action == "branch-proposal":
                    result = engine.branch.proposal(task_id)
                elif action == "operator-recovery":
                    if 'branch_run' in engine.store.get(task_id):
                        from .branch_operator import recover
                        task=recover(engine.branch,task_id,values)
                        result={'task':public_task(task),'operator_continue':task.get('operator_continue')}
                    else:
                        result=engine.operator_recovery(task_id,values)
                        result['task']=public_task(result['task'])
                elif action == "branch-operator-control":
                    from .branch_operator import control
                    result = public_task(control(engine.branch, task_id, values))
                elif action == "branch-message":
                    result = public_task(engine.branch.message(task_id, values))
                elif action == "branch-resume":
                    result = engine.branch.resume(task_id, values)
                elif action == "branch-leave":
                    if values: raise ValueError("Leave accepts no fields")
                    result = public_task(engine.branch.revoke(task_id))
                elif action == "start":
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
                    result = engine.approve_check(task_id, values["approved"], values.get("remember", False), values.get("approval_id"), values.get("scope"))
                elif action == "permissions":
                    if set(values) == {"revoke_project_grant"} and isinstance(values["revoke_project_grant"], str):
                        result = engine.revoke_project_permission(task_id, values["revoke_project_grant"])
                    elif values == {"clear": True}:
                        result = engine.clear_session_permissions(task_id)
                    else:
                        raise ValueError("Choose a grant to revoke or clear task commands")
                elif action == "commit-preview":
                    result = engine.prepare_commit(task_id)
                elif action == "reconcile":
                    result = public_task(engine.reconcile_project(task_id, values))
                elif action == "environment-recheck":
                    result = public_task(engine.recheck_environment(task_id))
                elif action == "commit-decision":
                    result = public_task(engine.commit_decision(task_id, values))
                elif action == "commit":
                    result = engine.apply_commit(task_id, values)
                elif action == "rollback":
                    checkpoint = values.get("checkpoint")
                    if not isinstance(checkpoint, int):
                        raise ValueError("Provide a checkpoint number to rollback to")
                    result = public_task(engine.rollback_checkpoint(task_id, checkpoint))
                elif action == "steer":
                    message = values.get("message")
                    if not message or not isinstance(message, str):
                        raise ValueError("Provide a steering message")
                    result = engine.steer(task_id, message)
                    if isinstance(result, dict) and "task" in result:
                        result["task"] = public_task(result["task"])
                elif action == "headroom":
                    additional_tokens = values.get("reviewer_tokens", 100000)
                    additional_turns = values.get("worker_turns", 10)
                    result = public_task(engine.boost_headroom(task_id, additional_tokens=additional_tokens, additional_turns=additional_turns))
                else:
                    raise ValueError("Unknown task action")
            else:
                self.reply({"error": "Route not found"}, 404)
                return
            if isinstance(result, dict) and "id" in result and "title" in result:
                result = engine.store.present(result)
            if isinstance(result, dict) and isinstance(result.get("task"), dict):
                result["task"] = engine.store.present(result["task"])
            self.reply(result)
        except (ValueError, TypeError, KeyError, OSError, ProviderError) as error:
            self.reply({"error": str(error)[:1000], "code": getattr(error, "code", None), "files": getattr(error, "files", [])}, 400)
        except Exception:
            self.reply({"error": "The local server could not complete this action"}, 500)
