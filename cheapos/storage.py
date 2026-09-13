"""Atomic, private, device-local task storage."""

import copy
import json
import os
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


class Store:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.tasks = {}
        for path in self.root.glob("tasks/*/task.json"):
            try:
                task = json.loads(path.read_text(encoding="utf-8"))
                if task["status"] in {"running", "reviewing", "waiting_approval", "stopping"}:
                    task["status"] = "interrupted"
                    task["error"] = "The server stopped. Review the saved work before resuming."
                    task["pending_approval"] = None
                    task["stream"] = None
                    task["check_stream"] = None
                    task["web_read"] = None
                    write_json(path, task)
                self.tasks[task["id"]] = task
            except (OSError, ValueError, KeyError):
                # A damaged record cannot prevent other tasks from opening.
                continue

    def save(self, task):
        with self.lock:
            write_json(self.root / "tasks" / task["id"] / "task.json", task)
            self.tasks[task["id"]] = copy.deepcopy(task)

    def get(self, task_id):
        with self.lock:
            if task_id not in self.tasks:
                raise ValueError("Task not found")
            return copy.deepcopy(self.tasks[task_id])

    def publish(self, task):
        """Publish live output without fsyncing the entire task for each token."""
        with self.lock:
            self.tasks[task["id"]] = copy.deepcopy(task)

    def list(self, summary=False):
        with self.lock:
            tasks = sorted(self.tasks.values(), key=lambda t: t["created_at"], reverse=True)
            if summary:
                keys = ("id", "title", "source", "status", "created_at", "updated_at", "demo", "usage")
                return [{key: copy.deepcopy(t[key]) for key in keys} for t in tasks]
            return [copy.deepcopy(t) for t in tasks]

    def metadata(self, task_id):
        """UI state is independent of worker-owned execution records."""
        with self.lock:
            self.get(task_id)
            defaults = dict(custom_title=None, pinned=False, archived_at=None, trashed_at=None)
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
        metadata = self.metadata(task["id"])
        return {**task, **metadata, "title": metadata["custom_title"] or task["title"]}

    def visible(self, view="active"):
        if view not in {"active", "archived", "trash"}:
            raise ValueError("Choose active, archived, or trash history")
        with self.lock:
            tasks = [self.present(task) for task in self.list(summary=True)]
            return [task for task in tasks if (
                bool(task["trashed_at"]) if view == "trash" else
                not task["trashed_at"] and bool(task["archived_at"]) == (view == "archived"))]
