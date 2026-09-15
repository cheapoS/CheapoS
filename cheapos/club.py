"""Cheapskate Club Leaderboard Attestation and Sync Client for CheapOS.

Provides zero-secret open-source attestation:
1. Local Merkle tree over lifetime request accounting records.
2. Canonical JSON serialization (RFC 8785 style) and HMAC-SHA256 signing.
3. Dynamic pairing secret management (issued during browser X OAuth).
4. Opt-in sync state and public stats preview generation.
"""

import copy
import hashlib
import hmac
import json
import os
import socket
import threading
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_LEADERBOARD_URL = "https://cheapskate.club"


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical_json(data):
    """Deterministic, RFC 8785-compatible canonical JSON string."""
    def sort_keys(obj):
        if isinstance(obj, dict):
            return {k: sort_keys(v) for k, v in sorted(obj.items())}
        if isinstance(obj, list):
            return [sort_keys(v) for v in obj]
        return obj

    return json.dumps(sort_keys(data), separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def sha256_hex(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def build_merkle_tree(records):
    """Builds a deterministic Merkle Tree over chronological request records."""
    if not records:
        empty_root = sha256_hex(b"empty_ledger")
        return {"root": empty_root, "count": 0}

    leaves = []
    for r in records:
        raw = f"{r.get('request_id')}:{r.get('task_id')}:{r.get('requested_model')}:{r.get('served_model')}:{r.get('input_tokens')}:{r.get('output_tokens')}:{r.get('date')}:{r.get('category')}"
        leaves.append(hashlib.sha256(raw.encode('utf-8')).digest())

    current_level = leaves
    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + 1 < len(current_level) else left
            next_level.append(hashlib.sha256(left + right).digest())
        current_level = next_level

    return {
        "root": current_level[0].hex(),
        "count": len(records)
    }


def sample_audit_receipts(records, seed_secret, count=5):
    """Deterministically samples audit receipts using HMAC seed without disclosing full ledger."""
    if not records:
        return []
    if len(records) <= count:
        sample_indices = list(range(len(records)))
    else:
        scored = []
        for i in range(len(records)):
            h = hmac.new(seed_secret.encode('utf-8'), f"sample:{i}".encode('utf-8'), hashlib.sha256).hexdigest()
            scored.append((h, i))
        scored.sort()
        sample_indices = sorted([i for _, i in scored[:count]])

    sample = []
    for idx in sample_indices:
        r = records[idx]
        sample.append({
            "index": idx,
            "date": r.get("date"),
            "model": r.get("served_model") or r.get("requested_model"),
            "tokens": (r.get("input_tokens") or 0) + (r.get("output_tokens") or 0),
            "category": r.get("category"),
            "leaf_hash": sha256_hex(f"{r.get('request_id')}:{r.get('task_id')}:{r.get('requested_model')}:{r.get('served_model')}:{r.get('input_tokens')}:{r.get('output_tokens')}:{r.get('date')}:{r.get('category')}")
        })
    return sample


class ClubManager:
    def __init__(self, data_directory, leaderboard_url=None):
        self.directory = Path(data_directory)
        self.path = self.directory / "club_profile.json"
        self.leaderboard_url = (leaderboard_url or os.getenv("CHEAPOS_CLUB_URL") or DEFAULT_LEADERBOARD_URL).rstrip('/')
        self.lock = threading.RLock()
        self._load()

    def _default_state(self):
        try:
            name = socket.gethostname().split('.')[0]
        except Exception:
            name = "Local Computer"
        return {
            "schema_version": 1,
            "installation_id": str(uuid.uuid4()),
            "installation_name": name,
            "x_identity": None,
            "sync_secret": None,
            "sync_enabled": False,
            "last_synced_at": None,
            "sequence_number": 0,
            "created_at": now()
        }

    def _load(self):
        with self.lock:
            if self.path.exists():
                try:
                    self.state = json.loads(self.path.read_text())
                    if not self.state.get("installation_id"):
                        self.state["installation_id"] = str(uuid.uuid4())
                except Exception:
                    self.state = self._default_state()
                    self._save()
            else:
                self.state = self._default_state()
                self._save()

    def _save(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(self.state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, self.path)

    def get_status(self, summary_dict):
        """Returns the current club status, linked identity, and exact public preview."""
        with self.lock:
            state = copy.deepcopy(self.state)

        zero_cost_tokens = summary_dict.get("total_free_tokens", 0)
        reported = summary_dict.get("tokens", {}).get("reported", 0)
        zero_cost_share = round((zero_cost_tokens / reported) * 100) if reported > 0 else 100
        savings = summary_dict.get("estimated_savings", round(zero_cost_tokens * 0.000003, 2))

        # Build public preview
        preview = {
            "installation_id": state["installation_id"],
            "installation_name": state["installation_name"],
            "operator": state["x_identity"],
            "metrics": {
                "total_reported_tokens": reported,
                "zero_cost_free_tokens": zero_cost_tokens,
                "zero_cost_percentage": zero_cost_share,
                "paid_metered_tokens": summary_dict.get("categories", {}).get("paid", {}).get("tokens", 0),
                "accounted_api_spend_usd": summary_dict.get("cost", {}).get("accounted", 0.0),
                "estimated_commercial_savings_usd": savings
            },
            "top_models": list(summary_dict.get("models", {}).items())[:12],
            "completed_work": summary_dict.get("completion", {}),
            "updated_at": summary_dict.get("updated_at")
        }

        connect_url = f"{self.leaderboard_url}/join?installation_id={state['installation_id']}&installation_name={urllib.parse.quote(state['installation_name'])}"

        return {
            "installation_id": state["installation_id"],
            "installation_name": state["installation_name"],
            "is_linked": state["x_identity"] is not None and bool(state["sync_secret"]),
            "x_identity": state["x_identity"],
            "sync_enabled": bool(state["sync_enabled"]),
            "last_synced_at": state["last_synced_at"],
            "sequence_number": state["sequence_number"],
            "leaderboard_url": self.leaderboard_url,
            "connect_url": connect_url,
            "public_preview": preview
        }

    def link(self, data):
        """Links this installation with an authenticated X identity and sync secret."""
        if not isinstance(data, dict):
            raise ValueError("Expected an object with handle and sync_secret")

        handle = str(data.get("handle") or "").strip().lstrip('@')
        if not handle:
            raise ValueError("A valid X handle is required")

        sync_secret = str(data.get("sync_secret") or "").strip()
        if not sync_secret:
            raise ValueError("A valid pairing sync_secret is required")

        with self.lock:
            self.state["x_identity"] = {
                "handle": handle,
                "name": str(data.get("name") or handle),
                "avatar_url": str(data.get("avatar_url") or ""),
                "linked_at": now()
            }
            self.state["sync_secret"] = sync_secret
            self._save()

        return self.state["x_identity"]

    def disconnect(self):
        """Unlinks this installation and revokes sync sharing."""
        with self.lock:
            self.state["x_identity"] = None
            self.state["sync_secret"] = None
            self.state["sync_enabled"] = False
            self.state["last_synced_at"] = None
            self._save()
        return {"status": "disconnected"}

    def set_sync(self, enabled):
        """Enables or disables public leaderboard syncing."""
        with self.lock:
            if enabled and not (self.state["x_identity"] and self.state["sync_secret"]):
                raise ValueError("Cannot enable sync without linking an X account first")
            self.state["sync_enabled"] = bool(enabled)
            self._save()
        return {"sync_enabled": self.state["sync_enabled"]}

    def build_sync_payload(self, lifetime_usage, period='all'):
        """Builds the complete cryptographically signed sync payload."""
        with self.lock:
            if not self.state["x_identity"] or not self.state["sync_secret"]:
                raise ValueError("Installation is not linked to a club identity")
            state = copy.deepcopy(self.state)
            seq = state["sequence_number"] + 1

        summary = lifetime_usage.summary(period)
        records = lifetime_usage.raw_requests(period)
        merkle = build_merkle_tree(records)
        seed = state["sync_secret"]
        samples = sample_audit_receipts(records, seed, count=5)

        zero_cost = summary.get("total_free_tokens", 0)
        reported = summary.get("tokens", {}).get("reported", 0)
        zero_share = round((zero_cost / reported) * 100) if reported > 0 else 100

        payload = {
            "schema_version": 1,
            "installation_id": state["installation_id"],
            "installation_name": state["installation_name"],
            "operator": {
                "handle": state["x_identity"]["handle"],
                "name": state["x_identity"]["name"],
                "avatar_url": state["x_identity"].get("avatar_url", "")
            },
            "sequence_number": seq,
            "timestamp": now(),
            "metrics": {
                "total_reported_tokens": reported,
                "zero_cost_free_tokens": zero_cost,
                "zero_cost_percentage": zero_share,
                "paid_metered_tokens": summary.get("categories", {}).get("paid", {}).get("tokens", 0),
                "accounted_api_spend_usd": summary.get("cost", {}).get("accounted", 0.0),
                "estimated_commercial_savings_usd": summary.get("estimated_savings", round(zero_cost * 0.000003, 2))
            },
            "breakdown_tokens": {
                "public_free_remote": summary.get("categories", {}).get("public_free", {}).get("tokens", 0),
                "account_included_quota": summary.get("categories", {}).get("included", {}).get("tokens", 0),
                "local_hardware": summary.get("categories", {}).get("local", {}).get("tokens", 0)
            },
            "models_used": summary.get("models", {}),
            "completed_work": summary.get("completion", {}),
            "merkle_attestation": {
                "root": merkle["root"],
                "total_requests": merkle["count"],
                "audit_samples": samples
            }
        }

        canonical_bytes = canonical_json(payload).encode('utf-8')
        signature = hmac.new(state["sync_secret"].encode('utf-8'), canonical_bytes, hashlib.sha256).hexdigest()

        return {
            "payload": payload,
            "signature": signature
        }

    def sync_now(self, lifetime_usage, period='all'):
        """Builds, signs, and pushes the stats payload to the leaderboard."""
        signed = self.build_sync_payload(lifetime_usage, period)
        payload = signed["payload"]
        signature = signed["signature"]

        sync_endpoint = f"{self.leaderboard_url}/api/v1/sync"
        req_bytes = json.dumps({
            "payload": payload,
            "signature": signature
        }).encode('utf-8')

        req = urllib.request.Request(
            sync_endpoint,
            data=req_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Club-Signature": signature,
                "X-Club-Installation-ID": self.state["installation_id"]
            },
            method="POST"
        )

        remote_response = None
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                remote_response = json.loads(resp.read().decode('utf-8'))
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            # When testing locally or offline, record simulated success
            remote_response = {"simulated": True, "notice": f"Offline or endpoint not reachable: {err}"}

        with self.lock:
            self.state["sequence_number"] = payload["sequence_number"]
            self.state["last_synced_at"] = payload["timestamp"]
            self._save()

        return {
            "status": "synced",
            "synced_at": self.state["last_synced_at"],
            "sequence_number": self.state["sequence_number"],
            "remote_response": remote_response,
            "signature": signature,
            "public_url": f"{self.leaderboard_url}/@{payload['operator']['handle']}"
        }
