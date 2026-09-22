"""Loopback-only HTTP API and static UI. No hosted identity or external dependencies."""

import json
import hashlib
import secrets
import os
import shutil
import socket
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Union
from urllib.parse import unquote, urlsplit, parse_qs

from . import __version__
from .gateways import gateway_for
from .providers import validate_provider, ProviderError
from . import metrics, check_output, branch_runs, branch_pause

BLOCKED_SYSTEM_ROOTS = {
    Path("/bin"),
    Path("/sbin"),
    Path("/usr"),
    Path("/System"),
    Path("/Library"),
    Path("/dev"),
    Path("/proc"),
    Path("/sys"),
    Path("/etc"),
    Path("/private/etc"),
    Path("/var"),
    Path("/private/var"),
}

ALLOWED_TEMP_ROOTS = {
    Path("/tmp"),
    Path("/private/tmp"),
    Path("/var/tmp"),
    Path("/private/var/tmp"),
    Path("/var/folders"),
    Path("/private/var/folders"),
}


def is_blocked_system_directory(target: Union[str, Path]) -> bool:
    """Component-aware check to ensure a path is not a system directory or descendant of one."""
    try:
        cand = Path(target).expanduser().resolve()
    except (ValueError, OSError):
        return True

    if cand == Path("/"):
        return True

    for allowed in ALLOWED_TEMP_ROOTS:
        try:
            res_allowed = allowed.resolve()
            if cand == allowed or cand == res_allowed or cand.is_relative_to(allowed) or cand.is_relative_to(res_allowed):
                return False
        except (ValueError, OSError):
            continue

    for blocked in BLOCKED_SYSTEM_ROOTS:
        try:
            res_blocked = blocked.resolve()
            if cand == blocked or cand == res_blocked or cand.is_relative_to(blocked) or cand.is_relative_to(res_blocked):
                return True
        except (ValueError, OSError):
            continue

    return False


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
    if task.get('follow_up'):
        task = {**task, 'follow_up': {k: v for k, v in task['follow_up'].items() if k not in {'context', 'retained_patch'}}}
    from .coordinator_dispatch import reassessment_availability
    reference = task.get('diagnostics_ref') or {}
    diagnostics = {'revision': task.get('updated_at') if 'routing_traces' in task else reference.get('digest'),
                   'available': bool(reference or task.get('routing_traces'))}
    return {**{key: value for key, value in task.items() if key not in {"messages", "worker_sessions", "conversation_state", "context_evidence", "edit_history", "fixture_phase", "in_flight", "turn_start_patch", "commit_pending", "request_metrics", "run_metrics", "routing_traces", "routing_traces_truncated", "diagnostics_ref"}}, "diagnostics": diagnostics, "working_state":working_state(task), "coordinator_reassessment":reassessment_availability(task), "metrics":metrics.aggregate(task), "token_accounting":metrics.token_accounting(task), "commit_pending": bool(task.get("commit_pending")), "patch_digest": hashlib.sha256(task.get("patch", "").encode()).hexdigest()}


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    # Each browser refresh fans out into several API requests. Python's older
    # five-connection default can reset that burst before a handler accepts it.
    request_queue_size = socket.SOMAXCONN

    def __init__(self, address, directory, engine):
        self.directory = Path(directory).resolve()
        self.engine = engine
        self.token = secrets.token_urlsafe(32)
        self.restart_lock = threading.Lock()
        self.restart_pending = False
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
        if not getattr(self, "_custom_csp", False):
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
            # This rejection happens before dispatch, so the same-origin client
            # may renew its local token and safely retry the unchanged request.
            self.reply({"error": "Local request token expired. Refresh the app.", "code": "local_token_expired"}, 403)
            return False
        return True

    def reply(self, value, status=200, etag=None):
        data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if etag:
            self.send_header("ETag", etag)
        try:
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            # Refreshing or cancelling a browser request can close its socket.
            # The action already ran; do not retry or send a 500 on that socket.
            # Catch only response writes, so backend failures stay visible.
            self.close_connection = True

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
        return relative in {"index.html", "app.js", "guidance.js", "panels.js", "styles.css", "brand-icon.svg", "branch_ui.js", "branch_ui.css", "lifetime_usage.js", "lifetime_usage.css", "preview.js", "carto.js", "integration.js", "settings.js", "settings.css", "storage.js", "git_workflow.js"} and not target.is_symlink() and target.is_file()

    def do_GET(self):
        if not self.trusted():
            return
        path = urlsplit(self.path).path
        while path.startswith("/api/api/"):
            path = path[4:]
        engine = self.server.engine
        try:
            if path == "/api/connection":
                # Restart polling must not wait on task/project restoration or
                # configuration discovery. The token identifies this process.
                self.reply({"app": "CheapOS", "token": self.server.token})
            elif path == "/api/bootstrap":
                self.reply({"app": "CheapOS", "version": __version__, "token": self.server.token, "config": engine.configuration(), "gateway": engine.connections.snapshot(), "startup":engine.startup.snapshot(), "tasks": engine.store.visible(), "projects": engine.projects(), "hidden_projects": [p for p in engine.projects(include_hidden=True) if p["path"] in engine.hidden_project_paths()], "preferences": engine.preferences()})
            elif path == "/api/job-evidence":
                self.reply({"version": 1, "cohort": "unattended_coding", "jobs": engine.store.lifetime.job_export()})
            elif path == "/api/lifetime-usage":
                period=parse_qs(urlsplit(self.path).query).get("days", ["all"])[0]
                if period not in {"all","7","30"}:return self.reply({"error":"Usage period must be all, 7 or 30 days"},400)
                summary = engine.store.lifetime.summary(days=int(period) if period != "all" else "all")
                if hasattr(engine.store, 'club'):
                    summary['club'] = engine.store.club.get_status(summary, include_remote=True)
                self.reply(summary)
            elif path == "/api/club/status":
                period=parse_qs(urlsplit(self.path).query).get("days", ["all"])[0]
                summary = engine.store.lifetime.summary(days=int(period) if period != "all" else "all")
                self.reply(engine.store.club.get_status(summary, include_remote=True))
            elif path == "/api/storage":
                self.reply(engine.storage_maintenance.view())
            elif path in {"/api/settings/defaults", "/api/projects/settings"}:
                project = engine.settings_project(parse_qs(urlsplit(self.path).query).get('project', [None])[0]) if path == '/api/projects/settings' else None
                self.reply(engine.settings_store.view(project))
            elif path.startswith('/api/tasks/') and path.endswith('/settings'):
                from .task_settings import view
                self.reply(view(engine, path.split('/')[3]))
            elif path == "/api/admission":
                self.reply(engine.admission.snapshot())
            elif path.startswith('/api/tasks/') and path.rsplit('/',1)[-1] in {'integration-readiness','integration-local-changes','integration-resolution-changes'}:
                from . import integration_preparation
                task_id=path.split('/')[3]
                action=path.rsplit('/',1)[-1]
                self.reply(getattr(integration_preparation, {'integration-readiness':'readiness','integration-local-changes':'local_changes','integration-resolution-changes':'resolution_changes'}[action])(engine,task_id))
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
            elif path == "/api/list-directories":
                query_params = parse_qs(urlsplit(self.path).query)
                requested_path = query_params.get("path", [""])[0]
                try:
                    if requested_path and requested_path.strip():
                        target_path = Path(unquote(requested_path.strip())).expanduser().resolve()
                    else:
                        target_path = self.server.directory if not (self.server.directory / "index.html").is_file() else Path.home()
                    if not target_path.exists():
                        self.reply({"error": "Directory not found"}, 404)
                        return
                    if is_blocked_system_directory(target_path):
                        self.reply({"error": "Access denied"}, 403)
                        return
                    if not target_path.is_dir():
                        self.reply({"error": "Not a directory"}, 400)
                        return
                    items = []
                    try:
                        for item in target_path.iterdir():
                            if item.name.startswith("."):
                                continue
                            try:
                                is_dir = item.is_dir()
                                is_git = (item / ".git").is_dir() if is_dir else False
                            except (PermissionError, OSError):
                                is_dir = False
                                is_git = False
                            items.append({"name": item.name, "path": str(item), "is_dir": is_dir, "is_git": is_git})
                    except PermissionError:
                        self.reply({"error": "Permission denied accessing directory"}, 403)
                        return
                    except OSError:
                        self.reply({"error": "Could not read directory"}, 400)
                        return
                    items.sort(key=lambda x: (not x["is_dir"], not x.get("is_git", False), x["name"].lower()))
                    parent_path = "" if target_path.parent in {Path("/"), target_path} else str(target_path.parent)
                    self.reply({
                        "current_path": str(target_path),
                        "parent_path": parent_path,
                        "is_git": (target_path / ".git").is_dir(),
                        "items": items,
                    })
                except Exception as e:
                    self.reply({"error": str(e)}, 500)
            elif path == "/api/role-mappings/effective":
                query_params = parse_qs(urlsplit(self.path).query)
                project = query_params.get("project", [None])[0]
                self.reply(engine.effective_role_mapping(project))
            elif path == "/api/tasks":
                self.reply(engine.store.visible(parse_qs(urlsplit(self.path).query).get("view", ["active"])[0]))
            elif path.startswith("/api/uploads/"):
                parts = path.strip("/").split("/")
                if len(parts) >= 3:
                    upload_id = parts[2]
                    filename = parts[3] if len(parts) > 3 else None
                    from .uploads import get_upload_path, detect_mime_type
                    file_path = get_upload_path(engine.store.root, upload_id, filename)
                    if file_path and file_path.is_file():
                        data = file_path.read_bytes()
                        mime = detect_mime_type(file_path.name, data)
                        safe_name = file_path.name
                        safe_raster = {"image/png", "image/jpeg", "image/webp", "image/gif"}
                        disposition = "inline" if mime in safe_raster else "attachment"
                        self.send_response(200)
                        self.send_header("Content-Type", mime)
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Content-Disposition", f'{disposition}; filename="{safe_name}"')
                        self._custom_csp = True
                        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; sandbox")
                        self.end_headers()
                        self.wfile.write(data)
                        return
                self.reply({"error": "File not found"}, 404)
                return
            elif path.startswith("/api/tasks/"):
                parts = path.strip("/").split("/")
                if len(parts) == 4 and parts[3] == 'diagnostics':
                    query = parse_qs(urlsplit(self.path).query)
                    self.reply(engine.store.diagnostics(parts[2], offset=int(query.get('offset', ['0'])[0]),
                                                        export=query.get('export') == ['1']))
                    return
                if len(parts) == 4 and parts[3] == 'export':
                    from .task_export import summary as task_summary
                    task, _ = engine.store.poll(parts[2])
                    self.reply(task_summary(public_task(task)))
                    return
                if len(parts) == 3:
                    task, etag = engine.store.poll(parts[2], self.headers.get("If-None-Match"))
                    if task is None:
                        self.send_response(304)
                        self.send_header("ETag", etag)
                        self.end_headers()
                    else:
                        self.reply(public_task(task), etag=etag)
                    return
                task = engine.store.get(parts[2])
                if len(parts) == 6 and parts[3] == "checks" and parts[5] == "raw":
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
            path = urlsplit(self.path).path
            while path.startswith("/api/api/"):
                path = path[4:]
            max_bytes = 35_000_000 if path == "/api/upload" else 1_000_000
            if not 0 < length <= max_bytes:
                raise ValueError(f"Request body must be under {max_bytes // (1024 * 1024)} MB")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Expected JSON")
            values = json.loads(self.rfile.read(length))
            if not isinstance(values, dict):
                raise ValueError("Expected a JSON object")
            engine = self.server.engine
            if path == "/api/restart":
                with self.server.restart_lock:
                    start_restart = not self.server.restart_pending
                    self.server.restart_pending = True
                # Acknowledge before waiting on background services to shut down.
                try:
                    self.reply({"status": "restarting"})
                finally:
                    # A disconnected browser must not cancel an accepted restart.
                    if start_restart:
                        def restart_backend():
                            try:
                                time.sleep(0.4)
                                started = time.monotonic()
                                print('cheapoS restart: stopping background services.', flush=True)
                                try:
                                    self.server.engine.shutdown()
                                except Exception as err:
                                    print(f'cheapoS restart: engine shutdown error: {err}', file=sys.stderr)
                                try:
                                    self.server.server_close()
                                except Exception as err:
                                    print(f'cheapoS restart: server_close error: {err}', file=sys.stderr)
                                if hasattr(self.server, 'data_lock') and self.server.data_lock:
                                    try:
                                        self.server.data_lock.close()
                                    except Exception as err:
                                        print(f'cheapoS restart: data_lock close error: {err}', file=sys.stderr)
                                print(f'cheapoS restart: shutdown completed in {time.monotonic()-started:.2f}s.', flush=True)
                                from .launch import restart_arguments
                                args = restart_arguments()
                                os.execv(sys.executable, args)
                            except Exception as err:
                                import traceback
                                traceback.print_exc()
                            finally:
                                with self.server.restart_lock:
                                    self.server.restart_pending = False
                        threading.Thread(target=restart_backend, daemon=True, name='backend-restart').start()
                return
            elif path in {"/api/settings/defaults", "/api/projects/settings"}:
                allowed = {'patch','expected_revision','operation_id'}
                if path == '/api/projects/settings': allowed |= {'project','expected_parent_revision','remove'}
                if set(values) - allowed: raise ValueError('Unknown scoped settings fields')
                project = engine.settings_project(values.get('project')) if path == '/api/projects/settings' else None
                result = engine.settings_store.save(values.get('patch'), expected_revision=values.get('expected_revision'), operation_id=values.get('operation_id'), project=project, expected_parent_revision=values.get('expected_parent_revision'), remove=values.get('remove', ()))
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
            elif path == "/api/upload":
                from .uploads import save_upload
                filename = values.get("filename", "")
                raw_data = values.get("data") or values.get("data_base64")
                if not raw_data:
                    raise ValueError("Provide upload data")
                mime_type = values.get("mime_type")
                result = save_upload(engine.store.root, filename, raw_data, mime_type=mime_type)
            elif path == "/api/projects/git-sync":
                from .git_sync import project_sync
                result = project_sync(engine, values)
            elif path == "/api/projects/carto":
                from .workspace import Workspace
                source = str(Workspace.project_root(values.get('repository', '')))
                if source not in {p['path'] for p in engine.projects(include_hidden=True)}:
                    raise ValueError('Choose a registered project')
                if 'enabled' in values: engine.carto.configure(source, values['enabled'])
                result = {**engine.carto.status(source), 'index':engine.carto.context(source,source,rebuild=values.get('rebuild') is True)}
            elif path == "/api/projects/create":
                name = values.get("name") or values.get("new_project_name")
                parent = values.get("parent") or values.get("new_project_parent", "")
                if not name or not isinstance(name, str) or not name.strip():
                    raise ValueError("Provide a project name")
                safe_name = name.strip()
                if safe_name in {".", ".."} or any(char in safe_name for char in ("/", "\\", "\0")):
                    raise ValueError("Use a project name without path separators")
                parent_str = str(parent).strip() if parent else ""
                parent_path = Path(unquote(parent_str)).expanduser().resolve() if parent_str and parent_str != "." else (
                    self.server.directory if not (self.server.directory / "index.html").is_file() else Path.home()
                )
                if not parent_path.is_dir() or is_blocked_system_directory(parent_path):
                    raise ValueError(f"Invalid parent directory: {parent_path}")
                target_dir = (parent_path / safe_name).resolve()
                if is_blocked_system_directory(target_dir):
                    raise ValueError(f"Invalid project location: {target_dir}")
                if target_dir.exists():
                    raise ValueError(f"Directory already exists: {target_dir}")
                created_dir = False
                try:
                    target_dir.mkdir(parents=True, exist_ok=False)
                    created_dir = True
                    init_git = values.get("init_git", True)
                    if init_git:
                        from .workspace import git
                        git(target_dir, "init", "-q")
                        git(target_dir, "-c", "user.name=cheapoS", "-c", "user.email=local@cheapos.invalid", "commit", "--allow-empty", "-qm", "Initial commit")
                        result = engine.open_project({"repository": str(target_dir)})
                    else:
                        result = {
                            "path": str(target_dir),
                            "name": safe_name,
                            "git": False,
                            "repository": str(target_dir),
                        }
                except Exception:
                    if created_dir and target_dir.exists():
                        shutil.rmtree(target_dir, ignore_errors=True)
                    raise
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
                    result = engine.store.club.set_sync(values["enabled"],values.get("share_models"),values.get("share_jobs"))
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
            elif path == "/api/storage/settings":
                result = engine.storage_maintenance.configure(values)
            elif path == "/api/storage/cleanup":
                if values: raise ValueError('Storage cleanup accepts no fields')
                result = engine.storage_maintenance.sweep()
            elif path == "/api/trash/empty":
                if values:
                    raise ValueError("This action does not accept fields")
                result = engine.empty_trash()
            elif path == "/api/demo":
                result = public_task(engine.create_demo())
            elif path == "/api/sample":
                result = public_task(engine.create_sample())
            elif path.startswith("/api/tasks/"):
                parts = path.strip("/").split("/")
                if len(parts) != 4:
                    raise ValueError("Unknown task action")
                task_id, action = parts[2:]
                if action in {'branch-start', 'branch-revise', 'branch-final-recheck', 'branch-update',
                              'branch-resolve-conflicts', 'branch-operator-control', 'integration-prepare', 'reconcile', 'operator-recovery'}:
                    from .pr_followup import check_before_work
                    check_before_work(engine, task_id)
                if action in {"preview-start", "preview-stop", "preview-status"}:
                    result = engine.previews.action(task_id, action, values)
                elif action in {"trash", "restore"}:
                    if values:
                        raise ValueError("This action does not accept fields")
                    result = public_task(engine.trash_task(task_id) if action == "trash" else engine.restore_task(task_id))
                elif action == "metadata":
                    result = public_task(engine.update_task_metadata(task_id, values))
                elif action == "settings":
                    from .task_settings import save
                    self.reply(save(engine,task_id,values))
                elif action == "integration-defer":
                    from .integration_preparation import cancel
                    self.reply(public_task(cancel(engine,task_id)))
                elif action == "integration-prepare":
                    from .integration_preparation import start
                    result = public_task(start(engine,task_id,values))
                elif action == "branch-start":
                    result = public_task(engine.branch.authorize(task_id, values, background=True))
                elif action in {"branch-final-preview", "branch-final-diff", "branch-merge", "branch-revise", "branch-final-recheck", "branch-update"}:
                    from . import branch_completion
                    operation = {"branch-final-preview":"preview", "branch-final-diff":"diff", "branch-merge":"merge", "branch-revise":"revise", "branch-final-recheck":"recheck", "branch-update":"update_branch"}[action]
                    result = getattr(branch_completion, operation)(engine.branch, task_id, values, **({'background': True} if operation == 'merge' else {}))
                    if isinstance(result, dict) and "branch_run" in result: result = public_task(result)
                    elif isinstance(result, dict) and isinstance(result.get("task"), dict): result = {**result, "task":public_task(result["task"])}
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
                    result = engine.branch.resume(task_id, values, source_actor='api')
                elif action == "branch-leave":
                    if values: raise ValueError("Leave accepts no fields")
                    result = public_task(engine.branch.revoke(task_id))
                elif action == "start":
                    result = public_task(engine.start(task_id, values))
                elif action == "message":
                    msg = values.get("message", "")
                    attachments = values.get("attachments", [])
                    if not isinstance(msg, str):
                        raise ValueError("Provide a message")
                    if not msg.strip() and not attachments:
                        raise ValueError("Provide a message")
                    result = public_task(engine.start(task_id, {"message": msg, "attachments": attachments}))
                elif action == "chat-message":
                    result = public_task(engine.chat_message(task_id, values))
                elif action == "limits":
                    result = public_task(engine.update_limits(task_id, values))
                elif action == "stop":
                    result = engine.stop(task_id)
                elif action == "approval":
                    if not isinstance(values.get("approved"), bool):
                        raise ValueError("Provide an approval decision")
                    result = engine.approve_check(task_id, values["approved"], values.get("remember", False), values.get("approval_id"), values.get("scope"))
                elif action == "task-commands":
                    result = engine.set_task_command_permission(task_id, values)
                elif action == "permissions":
                    if set(values) == {"revoke_project_grant"} and isinstance(values["revoke_project_grant"], str):
                        result = engine.revoke_project_permission(task_id, values["revoke_project_grant"])
                    elif values == {"clear": True}:
                        result = engine.clear_session_permissions(task_id)
                    else:
                        raise ValueError("Choose a grant to revoke or clear task commands")
                elif action == "commit-preview":
                    result = engine.prepare_commit(task_id)
                elif action == "pull-request-follow-up":
                    from . import pr_followup
                    result = public_task(pr_followup.create(engine, task_id, values))
                elif action in {"pull-request-preview", "pull-request-publish", "pull-request-status"}:
                    from . import git_workflow
                    if action == "pull-request-publish":
                        result = git_workflow.publish(engine, task_id, values)
                    else:
                        if values: raise ValueError('This request accepts no fields')
                        result = (git_workflow.preview if action == "pull-request-preview" else git_workflow.status)(engine, task_id)
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
                    message = values.get("message", "")
                    attachments = values.get("attachments", [])
                    if not isinstance(message, str):
                        raise ValueError("Provide a steering guidance message")
                    if not message.strip() and not attachments:
                        raise ValueError("Provide a steering guidance message")
                    result = engine.steer(task_id, message, attachments=attachments)
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
            if isinstance(result, dict) and all(key in result for key in ("id", "title", "workspace")):
                result = engine.store.present(result)
            if isinstance(result, dict) and isinstance(result.get("task"), dict):
                result["task"] = engine.store.present(result["task"])
            self.reply(result)
        except (ValueError, TypeError, KeyError, OSError, ProviderError) as error:
            body = {"error": str(error)[:1000], "code": getattr(error, "code", None), "files": getattr(error, "files", [])}
            if hasattr(error, 'current'):
                body.update(code='settings_conflict', current=error.current)
            self.reply(body, 409 if hasattr(error, 'current') else 400)
        except Exception:
            self.reply({"error": "The local server could not complete this action"}, 500)
