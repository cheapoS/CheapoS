"""Atomic, private, device-local task storage."""

import copy
import hashlib
import json
import time
import os
import threading
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .titles import automatic_title
from . import branch_runs


def _snapshot(value, memo=None):
    """Detach JSON containers before storage I/O yields to a live worker.

    The store lock serializes saves, not every worker mutation. Copy each
    container before walking its children so a concurrent insertion/removal
    cannot invalidate an iterator. Reuse this one snapshot for disk, views and
    accounting; none of those should reread the live task after writing it.
    """
    if not isinstance(value, (dict, list, tuple)):
        return value
    memo = {} if memo is None else memo
    if id(value) in memo:
        return memo[id(value)]
    if isinstance(value, dict):
        result = {}
        memo[id(value)] = result
        for key, item in value.copy().items():
            result[key] = _snapshot(item, memo)
    else:
        result = []
        memo[id(value)] = result
        result.extend(_snapshot(item, memo) for item in list(value))
    return result


def write_json(path, value, *, compact=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=None if compact else 2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


class Store:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.tasks = {}
        self._view_versions = {}
        from .lifetime_usage import LifetimeUsage
        self.lifetime = LifetimeUsage(self.root)
        from .club import ClubManager
        self.club = ClubManager(self.root)
        self.club.start_background(self.lifetime)
        for path in self.root.glob("tasks/*/task.json"):
            try:
                task = json.loads(path.read_text(encoding="utf-8"))
                changed = False
                for turn in task.get('discussion', []):
                    if turn.get('status') in {'queued', 'answering', 'work_queued'}:
                        turn.update(status='interrupted', answer='The app restarted before this reply finished. Your work is saved; send your question again to continue the conversation.')
                        changed = True
                if task.pop('chat_work_queue', None): changed = True
                if task["status"] in {"running", "reviewing", "waiting_approval", "waiting_retry", "stopping"}:
                    if task['status'] == 'waiting_retry' and task.get('retry_wait_enabled'):
                        task['route_resume_on_start'] = True
                    if task['status'] == 'waiting_retry' and task.get('route_wait'):
                        info = task.get('route_unavailable') or {}
                        remaining = info.get('remaining_seconds', 0)
                        if remaining is not None:
                            info['remaining_seconds'] = max(0, remaining - max(0, time.time()-task['route_wait']['started_at']))
                        info['can_wait'] = bool(info.get('can_wait') and (remaining is None or info['remaining_seconds'] > 0))
                    task['retry_wait_enabled'] = False
                    task['route_wait'] = None
                    task["status"] = "interrupted"
                    task["error"] = "The server stopped. Review the saved work before resuming."
                    task["pending_approval"] = None
                    task["stream"] = None
                    task["check_stream"] = None
                    task["web_read"] = None
                    changed = True
                if "branch_run" in task:
                    run = task["branch_run"]
                    # Restart recovery only changes a run when its execution or
                    # startup status changes; do not copy/serialize old histories.
                    before = (run.get("status"), (run.get("startup") or {}).get("status"), task["status"], task.get("error"))
                    branch_runs.recover_restart(task["branch_run"])
                    task["status"] = branch_runs.task_status(task["branch_run"])
                    if not branch_runs.compatibility(task["branch_run"])["supported"]:
                        task["error"] = branch_runs.compatibility(task["branch_run"])["message"]
                    after = (run.get("status"), (run.get("startup") or {}).get("status"), task["status"], task.get("error"))
                    changed = changed or before != after
                if changed:
                    write_json(path, task, compact=True)
                self.tasks[task["id"]] = task
                self.lifetime.ingest_task(task)
            except (OSError, ValueError, KeyError):
                # A damaged record cannot prevent other tasks from opening.
                continue

    def save(self, task):
        with self.lock:
            from .job_evidence import prepare
            prepare(task, self.tasks.get(task["id"]))
            saved = _snapshot(task)
            write_json(self.root / "tasks" / saved["id"] / "task.json", saved, compact=True)
            self.tasks[saved["id"]] = saved
            self._view_versions[saved["id"]] = uuid.uuid4().hex
            self.lifetime.ingest_task(saved)

    def get(self, task_id):
        with self.lock:
            if task_id not in self.tasks:
                raise ValueError("Task not found")
            return copy.deepcopy(self.tasks[task_id])

    def publish(self, task):
        """Publish live output without fsyncing the entire task for each token."""
        with self.lock:
            # All four publisher call sites update live fields only, following
            # a durable event/save. Preserve the immutable saved history snapshot.
            saved = self.tasks.get(task['id'])
            if saved is None:
                self.tasks[task['id']] = _snapshot(task)
            else:
                for key in ('stream','check_stream','web_read','updated_at','status'):
                    if key in task: saved[key] = _snapshot(task[key])
                    else: saved.pop(key,None)
            self._view_versions[task["id"]] = uuid.uuid4().hex

    def poll(self, task_id, previous=None):
        """Skip the full snapshot when this browser already has the current view.

        Versions are process-local, independent of worker timestamps, and change
        on every save/publish. Metadata participates without copying task history.
        The version and snapshot are captured under the same lock.
        """
        with self.lock:
            metadata = self.metadata(task_id)
            version = self._view_versions.setdefault(task_id, uuid.uuid4().hex)
            digest = hashlib.sha256(json.dumps([version, metadata], sort_keys=True).encode()).hexdigest()
            etag = '"' + digest + '"'
            if previous == etag:
                return None, etag
            task = copy.deepcopy(self.tasks[task_id])
            return self._present(task, metadata, task), etag

    def list(self, summary=False, *, fields=None):
        with self.lock:
            tasks = sorted(self.tasks.values(), key=lambda t: t["created_at"], reverse=True)
            if fields is not None:
                # Startup registries need metadata, not copies of every saved
                # conversation, patch, edit receipt and check output.
                return [{key: copy.deepcopy(t[key]) for key in fields if key in t} for t in tasks]
            if summary:
                keys = ("id", "title", "source", "status", "created_at", "updated_at", "demo", "usage")
                return [{**{key: copy.deepcopy(t.get(key)) for key in keys if key in t},
                         **({"branch_run": branch_runs.summary(t["branch_run"])} if "branch_run" in t else {})} for t in tasks]
            return [copy.deepcopy(t) for t in tasks]

    def metadata(self, task_id):
        """UI state is independent of worker-owned execution records."""
        with self.lock:
            if task_id not in self.tasks:
                raise ValueError("Task not found")
            defaults = dict(custom_title=None, pinned=False, archived_at=None, trashed_at=None, trash_archived_at=None)
            try:
                value = json.loads((self.root / "tasks" / task_id / "metadata.json").read_text())
                if not isinstance(value, dict):
                    return defaults
                for key, default in defaults.items():
                    item = value.get(key, default)
                    if key == "pinned":
                        if isinstance(item, bool):
                            defaults[key] = item
                    elif item is None or isinstance(item, str):
                        defaults[key] = item
            except (OSError, ValueError):
                pass
            return defaults

    def update_metadata(self, task_id, values):
        with self.lock:
            current = self.metadata(task_id)
            if not isinstance(values, dict) or set(values) - {"custom_title", "pinned", "archived"}:
                raise ValueError("Unknown task metadata field")
            if "custom_title" in values:
                title = values["custom_title"]
                if title is not None:
                    if not isinstance(title, str) or any(unicodedata.category(c) == "Cc" for c in title):
                        raise ValueError("Use a plain text title without control characters")
                    title = title.strip()
                    if not 1 <= len(title) <= 120:
                        raise ValueError("Enter a title of 1–120 characters")
                current["custom_title"] = title
            for key in ("pinned", "archived"):
                if key in values and not isinstance(values[key], bool):
                    raise ValueError(key + " must be true or false")
            if "pinned" in values:
                current["pinned"] = values["pinned"]
            if "archived" in values:
                current["archived_at"] = (current["archived_at"] or datetime.now(timezone.utc).isoformat()) if values["archived"] else None
            write_json(self.root / "tasks" / task_id / "metadata.json", current)
            return current

    def present(self, task):
        with self.lock:
            metadata = self.metadata(task["id"])
            return self._present(task, metadata, self.tasks[task["id"]])

    @staticmethod
    def _present(task, metadata, saved):
        # Only scalar presentation fields are read from the worker-owned record.
        # Copying the whole history here made even the sidebar scale with it.
        return {**task, **metadata, "saved_change_count": len(saved.get("changes", [])),
                "title": metadata["custom_title"] or automatic_title(saved)}

    def visible(self, view="active"):
        if view not in {"active", "archived", "trash"}:
            raise ValueError("Choose active, archived, or trash history")
        with self.lock:
            tasks = [self.present(task) for task in self.list(summary=True)]
            return [task for task in tasks if (
                bool(task["trashed_at"]) if view == "trash" else
                not task["trashed_at"] and bool(task["archived_at"]) == (view == "archived"))]

    def set_trashed(self, task_id, trashed):
        with self.lock:
            metadata = self.metadata(task_id)
            if trashed and not metadata["trashed_at"]:
                metadata["trashed_at"] = datetime.now(timezone.utc).isoformat()
                metadata["trash_archived_at"] = metadata["archived_at"]
            elif not trashed and metadata["trashed_at"]:
                metadata["archived_at"] = metadata["trash_archived_at"]
                metadata["trashed_at"] = None
                metadata["trash_archived_at"] = None
            write_json(self.root / "tasks" / task_id / "metadata.json", metadata)
            return metadata

    def delete_task(self, task_id):
        from .storage_maintenance import remove_task_files
        with self.lock:
            task = self.get(task_id)
            if not self.metadata(task_id)['trashed_at']:
                raise ValueError('Move this task to Trash before permanent deletion')
        # Engine admission prevents edits/restores during deletion. Keep reads
        # of other chats responsive while removing potentially large copies.
        remove_task_files(self, task)
        with self.lock:
            self.tasks.pop(task_id, None)
            self._view_versions.pop(task_id, None)

    def empty_trash(self):
        for task in self.visible(view="trash"):
            self.delete_task(task['id'])
