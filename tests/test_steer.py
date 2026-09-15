"""Tests for mid-flight steering and smart budget headroom recovery."""
import json
import sys
import unittest
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cheapos.engine import Runtime, DEFAULT_LIMITS
from test_engine import LocalCase


class SteerTests(LocalCase):
    def test_steer_while_paused(self):
        task = self.fixture(paid=True)
        task["status"] = "budget_paused"
        task["error_code"] = "worker_turn_limit"
        task["error"] = "Turn limit reached"
        self.engine.store.save(task)

        res = self.engine.steer(task["id"], "Focus strictly on fixing tests/test_calc.py line 12")
        self.assertTrue(res["steered"])
        self.assertFalse(res["running"])

        updated = self.engine.store.get(task["id"])
        self.assertEqual(updated["steer_guidance"], "Focus strictly on fixing tests/test_calc.py line 12")
        self.assertIsNone(updated["error_code"])
        self.assertIsNone(updated["error"])

        # Check that steer event was recorded
        steer_event = next((e for e in updated["events"] if e["kind"] == "steer"), None)
        self.assertIsNotNone(steer_event)
        self.assertEqual(steer_event["detail"], "Focus strictly on fixing tests/test_calc.py line 12")

        # Check that prompt was injected into messages
        last_msg = updated["messages"][-1]
        self.assertEqual(last_msg["role"], "user")
        self.assertIn("USER COURSE CORRECTION", last_msg["content"])
        self.assertIn("tests/test_calc.py", last_msg["content"])

        # The reviewer packet uses requests, not the worker's chat messages.
        self.assertEqual(updated['requests'][-1], updated['steer_guidance'])
        initial = self.engine.initial_messages(updated)
        self.assertEqual(json.loads(initial[1]['content'])['latest_message'], updated['steer_guidance'])
        steer_msg = next((m for m in initial if "User direction:" in m.get("content", "")), None)
        self.assertIsNotNone(steer_msg)
        self.assertIn("Focus strictly on fixing", steer_msg["content"])

    def test_steer_while_running(self):
        task = self.fixture(paid=True)
        old_requests = task.get('requests', [task['prompt']])
        task['requests'] = old_requests
        task['checkpoints'] = [{'user_messages': old_requests}]
        runtime = Runtime(task)
        done = threading.Event()
        def dummy_target():
            done.wait(5)
        runtime.thread = threading.Thread(target=dummy_target)
        runtime.thread.start()
        self.engine.runtimes[task["id"]] = runtime

        try:
            res = self.engine.steer(task["id"], "Do not edit math_utils.py; create a new helper instead")
            self.assertTrue(res["steered"])
            self.assertTrue(res["running"])

            self.assertEqual(task['requests'][-1], 'Do not edit math_utils.py; create a new helper instead')
            self.assertEqual(task['checkpoints'][0]['user_messages'], old_requests)
            self.assertEqual(len(task['requests']), len(old_requests) + 1)
            # Verify queued on runtime
            self.assertIn("Do not edit math_utils.py; create a new helper instead", runtime.steer_queue)

            updated = self.engine.store.get(task["id"])
            self.assertEqual(updated["steer_guidance"], "Do not edit math_utils.py; create a new helper instead")
            steer_event = next((e for e in updated["events"] if e["kind"] == "steer"), None)
            self.assertIsNotNone(steer_event)
        finally:
            done.set()
            runtime.thread.join(2)

    def test_steer_validation(self):
        task = self.fixture()

        # Empty or whitespace
        with self.assertRaises(ValueError):
            self.engine.steer(task["id"], "")
        with self.assertRaises(ValueError):
            self.engine.steer(task["id"], "   \n\t  ")

        # Exceeds max length
        with self.assertRaises(ValueError):
            self.engine.steer(task["id"], "x" * 4001)

        # Demo task check
        demo_task = dict(task)
        demo_task["id"] = "demo_test_task"
        demo_task["demo"] = True
        self.engine.store.save(demo_task)
        with self.assertRaises(ValueError):
            self.engine.steer("demo_test_task", "Test guidance")

    def test_boost_headroom(self):
        task = self.fixture()
        initial_tokens = task["limits"]["reviewer_tokens"]
        initial_turns = task["limits"]["worker_turns"]
        task["status"] = "budget_paused"
        task["error_code"] = "reviewer_token_limit"
        task["error"] = "The next model request does not fit the remaining budget"
        self.engine.store.save(task)

        updated = self.engine.boost_headroom(task["id"], additional_tokens=100000, additional_turns=10)
        self.assertEqual(updated["limits"]["reviewer_tokens"], initial_tokens + 100000)
        self.assertEqual(updated["limits"]["worker_turns"], initial_turns + 10)
        self.assertIsNone(updated["error_code"])
        self.assertIsNone(updated["error"])

        # Check guard event was logged
        guard_event = next((e for e in reversed(updated["events"]) if e["title"] == "Boosted Task Headroom"), None)
        self.assertIsNotNone(guard_event)
        self.assertEqual(guard_event["detail"]["reviewer_tokens"], initial_tokens + 100000)


if __name__ == '__main__':
    unittest.main()
