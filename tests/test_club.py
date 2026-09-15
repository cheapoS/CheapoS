"""Tests for Cheapskate Club attestation, canonical JSON, and sync state."""

import hmac
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from cheapos.club import (
    ClubManager,
    canonical_json,
    build_merkle_tree,
    sample_audit_receipts,
    sha256_hex
)
from cheapos.storage import Store


class ClubTests(unittest.TestCase):
    def test_canonical_json_is_strictly_sorted_and_compact(self):
        obj1 = {"z": 1, "a": 2, "m": {"b": 3, "a": 4}}
        obj2 = {"a": 2, "m": {"a": 4, "b": 3}, "z": 1}
        c1 = canonical_json(obj1)
        c2 = canonical_json(obj2)
        self.assertEqual(c1, c2)
        self.assertEqual(c1, '{"a":2,"m":{"a":4,"b":3},"z":1}')

    def test_merkle_tree_is_deterministic_and_empty_safe(self):
        empty = build_merkle_tree([])
        self.assertEqual(empty["count"], 0)
        self.assertTrue(isinstance(empty["root"], str) and len(empty["root"]) == 64)

        records = [
            {"request_id": "r1", "task_id": "t1", "requested_model": "deepseek", "input_tokens": 100, "output_tokens": 50, "date": "2026-09-14", "category": "included"},
            {"request_id": "r2", "task_id": "t1", "requested_model": "haiku", "input_tokens": 200, "output_tokens": 100, "date": "2026-09-15", "category": "public_free"}
        ]
        t1 = build_merkle_tree(records)
        t2 = build_merkle_tree(records)
        self.assertEqual(t1["root"], t2["root"])
        self.assertEqual(t1["count"], 2)

        # Modifying one token count changes root
        tampered = [dict(records[0]), dict(records[1], input_tokens=201)]
        t_tampered = build_merkle_tree(tampered)
        self.assertNotEqual(t1["root"], t_tampered["root"])

    def test_sample_audit_receipts_are_deterministic(self):
        records = [
            {"request_id": f"r{i}", "task_id": "t", "requested_model": "m", "input_tokens": i, "output_tokens": i, "date": "2026-09-15", "category": "public_free"}
            for i in range(20)
        ]
        s1 = sample_audit_receipts(records, "secret_key", count=5)
        s2 = sample_audit_receipts(records, "secret_key", count=5)
        self.assertEqual(s1, s2)
        self.assertEqual(len(s1), 5)
        self.assertTrue(all("leaf_hash" in item for item in s1))

    def test_club_manager_lifecycle(self):
        with tempfile.TemporaryDirectory() as tempdir:
            club = ClubManager(tempdir)
            status = club.get_status({"total_free_tokens": 1000, "tokens": {"reported": 1000}})
            self.assertFalse(status["is_linked"])
            self.assertFalse(status["sync_enabled"])
            self.assertTrue(bool(status["installation_id"]))

            # Link identity
            club.link({
                "handle": "test_operator",
                "name": "Test Operator",
                "avatar_url": "https://example.com/avatar.png",
                "sync_secret": "test_sync_secret_123"
            })
            status = club.get_status({"total_free_tokens": 1000, "tokens": {"reported": 1000}})
            self.assertTrue(status["is_linked"])
            self.assertEqual(status["x_identity"]["handle"], "test_operator")

            # Enable sync
            club.set_sync(True)
            self.assertTrue(club.state["sync_enabled"])

            # Store integration test
            store = Store(tempdir)
            task = {
                'id': 't1', 'status': 'ready', 'created_at': '2026-09-15T00:00:00Z',
                'usage': {'worker': {'tokens': 30, 'cost': 0}, 'cost': 0},
                'request_metrics': [{
                    'id': 'req1', 'dispatched': True, 'role': 'worker',
                    'requested_at': '2026-09-15T00:00:00Z',
                    'requested_model': 'antigravity/gemini-3.1-flash-lite',
                    'served_model': 'gemini-3.1-flash-lite',
                    'input_tokens': 20, 'output_tokens': 10, 'reported_cost': None,
                    'input_rate': 0.0, 'output_rate': 0.0, 'usage_reconciled': True
                }]
            }
            store.save(task)

            # Build signed sync payload
            signed = club.build_sync_payload(store.lifetime)
            payload = signed["payload"]
            signature = signed["signature"]

            # Verify signature with sync_secret
            expected_sig = hmac.new("test_sync_secret_123".encode('utf-8'), canonical_json(payload).encode('utf-8'), hashlib.sha256).hexdigest()
            self.assertEqual(signature, expected_sig)
            self.assertEqual(payload["operator"]["handle"], "test_operator")
            self.assertEqual(payload["metrics"]["total_reported_tokens"], 30)
            self.assertEqual(payload["metrics"]["zero_cost_free_tokens"], 30)
            self.assertEqual(payload["merkle_attestation"]["total_requests"], 1)

            # Disconnect
            club.disconnect()
            status = club.get_status({"total_free_tokens": 1000, "tokens": {"reported": 1000}})
            self.assertFalse(status["is_linked"])
            self.assertFalse(status["sync_enabled"])

    def test_club_http_routes(self):
        from types import SimpleNamespace
        from cheapos.server import LocalHandler as Handler
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            handler = Handler.__new__(Handler)
            handler.server = SimpleNamespace(engine=SimpleNamespace(store=store))
            handler.trusted = lambda mutation=False: True
            replies = []
            handler.reply = lambda body, status=200: replies.append((body, status))

            # Test GET /api/club/status
            handler.path = "/api/club/status"
            handler.do_GET()
            self.assertEqual(replies[-1][1], 200)
            self.assertFalse(replies[-1][0]["is_linked"])

            # Test POST /api/club/link
            import io, email
            link_body = json.dumps({"handle": "carlosa8c", "sync_secret": "test_sec_456"}).encode()
            handler.path = "/api/club/link"
            handler.headers = email.message_from_string(f"Content-Length: {len(link_body)}\nContent-Type: application/json\n\n")
            handler.rfile = io.BytesIO(link_body)
            handler.do_POST()
            self.assertEqual(replies[-1][1], 200)
            self.assertEqual(replies[-1][0]["handle"], "carlosa8c")

            # Check GET reflects linked status
            handler.path = "/api/club/status"
            handler.do_GET()
            self.assertTrue(replies[-1][0]["is_linked"])
            self.assertEqual(replies[-1][0]["x_identity"]["handle"], "carlosa8c")

            # Test POST /api/club/sync enabled toggle
            sync_toggle = json.dumps({"enabled": True}).encode()
            handler.path = "/api/club/sync"
            handler.headers = email.message_from_string(f"Content-Length: {len(sync_toggle)}\nContent-Type: application/json\n\n")
            handler.rfile = io.BytesIO(sync_toggle)
            handler.do_POST()
            self.assertEqual(replies[-1][1], 200)
            self.assertTrue(replies[-1][0]["sync_enabled"])

            # Test POST /api/club/disconnect
            disc_body = json.dumps({}).encode()
            handler.path = "/api/club/disconnect"
            handler.headers = email.message_from_string(f"Content-Length: {len(disc_body)}\nContent-Type: application/json\n\n")
            handler.rfile = io.BytesIO(disc_body)
            handler.do_POST()
            self.assertEqual(replies[-1][1], 200)
            self.assertEqual(replies[-1][0]["status"], "disconnected")


if __name__ == "__main__":
    unittest.main()
