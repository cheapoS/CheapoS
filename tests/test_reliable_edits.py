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


if __name__ == "__main__":
    unittest.main()
