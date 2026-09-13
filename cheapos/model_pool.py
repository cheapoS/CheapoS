"""Local observations of free routes; never stores credentials or model output."""

import copy
import hashlib
import json
import threading
import time
from pathlib import Path

from .storage import write_json


RECOVERABLE_CODES = {"stream_error", "stream_interrupted", "stream_timeout", "model_timeout",
                     "model_connection", "invalid_response_json", "invalid_stream_json",
                     "invalid_response_shape", "invalid_tool_envelope", "empty_response", "unsupported_tool",
                     "http_408", "http_429", "http_500", "http_502", "http_503", "http_504"}
MAX_HANDOFFS = 2


def automatic(task, role):
    return (not task.get("demo") and task.get("execution", {}).get("mode") in {"delegate", "remote"}
            and bool(task.get("route")) and role in {"worker", "reviewer"})


class FreeModelPool:
    def __init__(self, directory):
        self.path = Path(directory) / "model-health.json"
        self.lock = threading.RLock()
        self.revision = 0
        try:
            self.records = json.loads(self.path.read_text())
            if not isinstance(self.records, dict):
                self.records = {}
        except (OSError, ValueError):
            self.records = {}

    @staticmethod
    def key(endpoint, model):
        return hashlib.sha256((endpoint.replace("localhost", "127.0.0.1").rstrip("/") + "\n" + model).encode()).hexdigest()

    def observation(self, endpoint, model):
        with self.lock:
            record = copy.deepcopy(self.records.get(self.key(endpoint, model), {}))
            provider = self.records.get(self.key(endpoint, self.provider_key(model)), {})
            if provider.get("retry_at", 0) > time.time():
                record.update(retry_at=max(record.get("retry_at", 0), provider["retry_at"]),
                              cooldown_scope="provider", last_error=provider.get("last_error", ""))
        record["cooling_down"] = record.get("retry_at", 0) > time.time()
        return record

    @staticmethod
    def provider_key(model):
        return "\0provider/" + model.split("/", 1)[0]

    def record(self, endpoint, model, role, *, error=None, seconds=None, probe=False):
        with self.lock:
            cooldown = getattr(error, "code", None) == "gateway_cooldown"
            scope = getattr(error, "scope", None)
            key = self.key(endpoint, self.provider_key(model) if cooldown and scope == "provider" else model)
            record = self.records.setdefault(key, {})
            record["updated_at"] = time.time()
            if cooldown:
                record.update(retry_at=time.time() + min(86400, max(1, error.retry_after or 120)),
                              cooldown_scope=scope, last_error=str(error)[:500])
            elif error is not None:
                failures = record.get("failures", 0) + 1
                record.update(failures=failures, retry_at=time.time() + min(3600, 900 * 2 ** min(failures - 1, 2)),
                              last_error=str(error)[:500])
            else:
                record.update(retry_at=0, last_error="")
                record.pop("cooldown_scope", None)
                if probe:
                    record["tool_check_passed"] = True
                else:
                    record["failures"] = 0
                    field = role + "_responses"
                    record[field] = record.get(field, 0) + 1
                    if seconds is not None:
                        field = role + "_seconds"
                        record[field] = round(record.get(field, seconds) * .7 + seconds * .3, 3)
            # Retain a bounded history; missing catalog entries never become candidates.
            if len(self.records) > 2000:
                self.records = dict(sorted(self.records.items(), key=lambda item: item[1].get("updated_at", 0))[-2000:])
            write_json(self.path, self.records)
            self.revision += 1

    def rank(self, endpoint, model, role, preferred=None):
        health = self.observation(endpoint, model["id"])
        # Observed compatibility first. Metadata only breaks ties; it is not a quality rating.
        return (model["id"] != preferred, -min(health.get(role + "_responses", 0), 1),
                health.get("failures", 0),
                -(health.get("tool_check_passed") is True),
                -(model.get("reasoning") is True) if role == "reviewer" else 0,
                -min(model.get("context_length") or 0, 65536) if role == "reviewer" else 0,
                health.get(role + "_seconds", float("inf")), model["id"])
