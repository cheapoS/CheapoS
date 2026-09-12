"""Atomic, private, device-local task storage."""

import copy
import json
import os
import threading
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
