import unittest
import tempfile
import shutil
from pathlib import Path

from cheapos.workspace import Workspace
from cheapos.continuation_policy import is_continue, decide
from cheapos import work_policy
from cheapos.engine import Engine, WORKER_TOOLS


class ReliableEditsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        import subprocess
        subprocess.run(["git", "init"], cwd=self.temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.temp_dir, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.temp_dir, check=True)
        init_file = Path(self.temp_dir) / ".gitkeep"
        init_file.write_text("", encoding="utf-8")
        subprocess.run(["git", "add", ".gitkeep"], cwd=self.temp_dir, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=self.temp_dir, check=True, capture_output=True)
        self.workspace = Workspace(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_append_text_appends_and_validates(self):
        file_path = Path(self.temp_dir) / "test.txt"
        file_path.write_text("Line 1\n", encoding="utf-8")

        res = self.workspace.append_text("test.txt", "Line 2\n")
        self.assertTrue(res["updated"])
        self.assertTrue(res["appended"])
        self.assertEqual(file_path.read_text(encoding="utf-8"), "Line 1\nLine 2\n")

        with self.assertRaisesRegex(ValueError, "does not exist"):
            self.workspace.append_text("nonexistent.txt", "test")

        with self.assertRaisesRegex(ValueError, "nonempty text string"):
            self.workspace.append_text("test.txt", "")

    def test_replace_text_actionable_errors(self):
        file_path = Path(self.temp_dir) / "README.md"
        file_path.write_text("Intro\n<p>one</p>\nMiddle\n<p>two</p>\nEnd\n", encoding="utf-8")

        # 0 matches
        with self.assertRaisesRegex(ValueError, "was not found in 'README.md'"):
            self.workspace.replace_text("README.md", "Nonexistent text", "replacement")

        # Multiple matches
        with self.assertRaisesRegex(ValueError, r"matched 2 times in 'README.md' \(line 2, line 4\).*append_text"):
            self.workspace.replace_text("README.md", "</p>", "<p>custom</p>\n</p>")

    def test_write_file_existing_file_actionable_error(self):
        file_path = Path(self.temp_dir) / "exists.txt"
        file_path.write_text("Existing content\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, r"File 'exists\.txt' already exists.*replace_text.*append_text.*write_file cannot overwrite"):
            self.workspace.write_file("exists.txt", "New content\n")

    def test_affirmative_continuations(self):
        for word in ["sure", "ok", "okay", "yes", "yep", "yeah", "yup", "fine", "sure go ahead"]:
            self.assertTrue(is_continue(word), f"'{word}' should be recognized as a continuation")
            self.assertTrue(is_continue(word.upper()), f"'{word.upper()}' should be recognized as a continuation")

    def test_attempted_edit_detection(self):
        task_without_edits = {"events": [{"kind": "tool", "title": "read file", "detail": {"arguments": {"path": "a.txt"}}}]}
        self.assertFalse(work_policy.attempted_edit(task_without_edits))

        task_with_failed_edit = {
            "events": [
                {"kind": "tool", "title": "read file", "detail": {"arguments": {"path": "a.txt"}}},
                {"kind": "tool_error", "title": "Action could not finish", "detail": {"tool": "replace_text", "error": "matched 2 times"}},
            ]
        }
        self.assertTrue(work_policy.attempted_edit(task_with_failed_edit))

        task_with_append = {
            "events": [
                {"kind": "tool", "title": "append text", "detail": {"arguments": {"path": "a.txt", "text": "hello"}}},
            ]
        }
        self.assertTrue(work_policy.attempted_edit(task_with_append))

    def test_repeated_evidence_with_attempted_edit_maintains_implementation(self):
        task = {
            "events": [
                {"kind": "tool", "title": "read file", "detail": {"arguments": {"path": "README.md"}}},
                {"kind": "tool_error", "title": "Action could not finish", "detail": {"tool": "replace_text", "error": "matched 7 times"}},
            ],
            "conversational": True,
            "requests": ['add the sentence "Carlos Is testint me" To the readME'],
        }
        decision = decide(task, trigger="repeated_evidence")
        self.assertEqual(decision["kind"], "implementation")
        self.assertEqual(decision["action"], "act")

    def test_append_text_in_worker_tools(self):
        tool_names = [t["function"]["name"] for t in WORKER_TOOLS]
        self.assertIn("append_text", tool_names)

    def test_engine_file_tool_append_text(self):
        file_path = Path(self.temp_dir) / "notes.md"
        file_path.write_text("# Notes\n", encoding="utf-8")

        state_dir = Path(self.temp_dir) / "state"
        engine = Engine(state_dir, fixture_delay=0)
        self.addCleanup(engine.shutdown)

        task = {
            "id": "t1",
            "workspace": self.temp_dir,
            "tool_actions": 0,
            "active_role": "worker",
            "status": "working",
            "providers": {"worker": {"model": "test-model"}},
            "events": [],
        }

        result = engine.file_tool(task, "append_text", {"path": "notes.md", "text": "New note\n"})
        self.assertTrue(result["updated"])
        self.assertTrue(result["appended"])
        self.assertEqual(file_path.read_text(encoding="utf-8"), "# Notes\nNew note\n")
        self.assertEqual(task["tool_actions"], 1)

    def test_provider_reasoning_fallback_flag(self):
        import json
        from cheapos.providers import ChatProvider
        from unittest.mock import patch, MagicMock

        provider = ChatProvider({'base_url': 'http://127.0.0.1:11434/v1', 'model': 'fixture', 'key_env': 'CHEAPOS_TEST_KEY'})

        # Case 1: Reasoning only, no content, no tool calls -> reasoning_fallback is True
        mock_data = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "reasoning": "I need to check README.md first."
                }
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8}
        }
        with patch('cheapos.providers.build_opener') as opener:
            mock_resp = MagicMock()
            mock_resp.headers.get_content_type.return_value = 'application/json'
            mock_resp.read.return_value = json.dumps(mock_data).encode()
            opener.return_value.open.return_value.__enter__.return_value = mock_resp
            msg, usage = provider._complete([], [], 128)
            self.assertTrue(msg.get("reasoning_fallback"))
            self.assertEqual(msg["content"], "I need to check README.md first.")
            self.assertEqual(msg["reasoning"], "I need to check README.md first.")

        # Case 2: Content is present -> reasoning_fallback is False / not set
        mock_data_content = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Here is the answer.",
                    "reasoning": "I am thinking."
                }
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8}
        }
        with patch('cheapos.providers.build_opener') as opener:
            mock_resp = MagicMock()
            mock_resp.headers.get_content_type.return_value = 'application/json'
            mock_resp.read.return_value = json.dumps(mock_data_content).encode()
            opener.return_value.open.return_value.__enter__.return_value = mock_resp
            msg, usage = provider._complete([], [], 128)
            self.assertFalse(msg.get("reasoning_fallback", False))
            self.assertEqual(msg["content"], "Here is the answer.")

    def test_engine_reasoning_fallback_does_not_halt_to_awaiting_reply(self):
        state_dir = Path(self.temp_dir) / "state"
        engine = Engine(state_dir, fixture_delay=0)
        self.addCleanup(engine.shutdown)

        task = engine.create_demo()
        task["demo"] = False
        task["conversational"] = True
        config = {'base_url': 'https://example.invalid/v1', 'model': 'test-model', 'input_rate': 0, 'output_rate': 0, 'key_env': 'CHEAPOS_TEST_KEY'}
        task["providers"] = {"worker": dict(config), "reviewer": dict(config)}
        engine.store.save(task)

        turn = 0
        recorded_messages = []

        class ThinkingModelProvider:
            streams_output = False
            def complete(self, messages, tools, maximum, tool_choice=None):
                nonlocal turn
                turn += 1
                recorded_messages.append(list(messages))
                if turn == 1:
                    return {
                        "role": "assistant",
                        "content": "I should search for project files.",
                        "reasoning": "I should search for project files.",
                        "reasoning_fallback": True,
                        "tool_calls": []
                    }, {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0}
                else:
                    return {
                        "role": "assistant",
                        "content": "Here is the completed response.",
                        "tool_calls": []
                    }, {"prompt_tokens": 15, "completion_tokens": 8, "cost": 0}

        engine.provider_factory = lambda *args: ThinkingModelProvider()
        engine.start(task["id"])
        runtime = engine.runtimes[task["id"]]
        runtime.thread.join(10)
        self.assertFalse(runtime.thread.is_alive())

        result = engine.store.get(task["id"])
        self.assertEqual(turn, 2)
        self.assertEqual(result["status"], "awaiting_reply")

        nudge_message = next((m for m in result["messages"] if "You generated reasoning without executing a tool call" in m.get("content", "")), None)
        self.assertIsNotNone(nudge_message, "Worker should have received prompt to proceed after reasoning-only turn")
        self.assertIn("Proceed with your planned action using the offered tools", nudge_message["content"])

        assistant_events = [e for e in result["events"] if e["kind"] == "assistant"]
        self.assertEqual(len(assistant_events), 1)
        self.assertEqual(assistant_events[0]["detail"], "Here is the completed response.")

    def test_delete_file_in_worker_tools(self):
        tool_names = [t["function"]["name"] for t in WORKER_TOOLS]
        self.assertIn("delete_file", tool_names)

    def test_delete_file_deletes_untracked_and_tracked_files(self):
        # Case 1: Untracked file
        untracked = Path(self.temp_dir) / "untracked.py"
        untracked.write_text("print('abandoned')\n", encoding="utf-8")
        self.assertTrue(untracked.exists())
        res = self.workspace.delete_file("untracked.py")
        self.assertTrue(res["deleted"])
        self.assertFalse(untracked.exists())
        self.assertEqual(len(self.workspace.changes()), 0)

        # Case 2: Tracked file
        tracked = Path(self.temp_dir) / "tracked.py"
        tracked.write_text("def old(): pass\n", encoding="utf-8")
        import subprocess
        subprocess.run(["git", "add", "tracked.py"], cwd=self.temp_dir, check=True)
        subprocess.run(["git", "commit", "-m", "add tracked"], cwd=self.temp_dir, check=True, capture_output=True)
        self.assertTrue(tracked.exists())
        res = self.workspace.delete_file("tracked.py")
        self.assertTrue(res["deleted"])
        self.assertFalse(tracked.exists())
        changes = self.workspace.changes()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["path"], "tracked.py")
        self.assertEqual(changes[0]["after"], "")

    def test_delete_file_validations(self):
        with self.assertRaisesRegex(ValueError, "Provide a file path to delete"):
            self.workspace.delete_file("")

        with self.assertRaisesRegex(ValueError, "does not exist"):
            self.workspace.delete_file("nonexistent.txt")

        sub_dir = Path(self.temp_dir) / "sub_dir"
        sub_dir.mkdir()
        with self.assertRaisesRegex(ValueError, "is a directory"):
            self.workspace.delete_file("sub_dir")

    def test_engine_file_tool_delete_file(self):
        file_path = Path(self.temp_dir) / "to_delete.txt"
        file_path.write_text("temporary content\n", encoding="utf-8")

        state_dir = Path(self.temp_dir) / "state"
        engine = Engine(state_dir, fixture_delay=0)
        self.addCleanup(engine.shutdown)

        task = {
            "id": "t_del",
            "workspace": self.temp_dir,
            "tool_actions": 0,
            "active_role": "worker",
            "status": "working",
            "providers": {},
            "events": [],
            "patch": "",
            "changes": [],
        }
        res = engine.file_tool(task, "delete_file", {"path": "to_delete.txt"})
        self.assertTrue(res["deleted"])
        self.assertIn("File deleted", res["guidance"])
        self.assertFalse(file_path.exists())
        self.assertTrue(any(e["title"] == "delete file" for e in task["events"]))


if __name__ == "__main__":
    unittest.main()
