"""Unit tests for the PromptDiet core library."""

import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from prompt_diet import (
    estimate_tokens,
    detect_fluff,
    analyze,
    minify,
    diff,
)

class TestPromptDiet(unittest.TestCase):
    def test_estimate_tokens(self):
        # Empty string
        self.assertEqual(estimate_tokens(""), 0)
        # 8 characters => 2 tokens
        self.assertEqual(estimate_tokens("abcdefgh"), 2)
        # Mixed spaces
        self.assertEqual(estimate_tokens("hello world!"), 3)  # 13 chars -> 3

    def test_detect_fluff(self):
        text = "I hope you are doing well. Please let me know if you need anything."
        fluff = detect_fluff(text)
        # Both phrases should be detected (case-insensitive)
        self.assertIn("I hope you are doing well", fluff)
        self.assertIn("please let me know", fluff)

    def test_minify(self):
        original = (
            "**Hello**, I hope you are doing well.\n\n"
            "Please let me know if you need anything.\n\n"
            "Thank you for your time."
        )
        expected = (
            "Hello,\n\n\n\n\nThank you for your time."
        )
        result = minify(original)
        # We expect bold markers removed, fluff removed, and newlines collapsed
        self.assertIn("Hello,", result)
        self.assertNotIn("**", result)
        self.assertNotIn("I hope you are doing well", result)
        self.assertNotIn("please let me know", result)
        # Ensure no consecutive blank lines
        self.assertNotIn("\n\n\n", result)

    def test_diff(self):
        original = "Line 1\nLine 2\nLine 3\n"
        minified = "Line 1\nLine 3\n"
        d = diff(original, minified)
        # Diff should start with file identifiers
        self.assertTrue(d.startswith("--- original\n+++ minified"))
        # Should contain the removed line
        self.assertIn("-Line 2", d)
        # Should contain the context line (present in both)
        self.assertIn(" Line 3", d)

    def test_analyze(self):
        text = "**Hello**, I hope you are doing well.\n\nPlease let me know."
        analysis = analyze(text)
        # Tokens estimate
        self.assertIn("tokens", analysis)
        self.assertIn("fluff", analysis)
        self.assertIn("savings", analysis)
        # Ensure savings positive if fluff removed
        self.assertGreater(analysis["savings"], 0)


class TestCLI(unittest.TestCase):
    """Tests for the diet.py CLI subcommands."""

    def _run_cli(self, subcommand, prompt_text):
        """Run diet.py <subcommand> with prompt_text via stdin, return (exit_code, stdout)."""
        import subprocess
        import os
        diet_path = os.path.join(os.path.dirname(__file__), "diet.py")
        result = subprocess.run(
            ["python3", diet_path, subcommand],
            input=prompt_text,
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout

    def test_cli_analyze(self):
        prompt = "I hope you are doing well. Summarize this document."
        code, out = self._run_cli("analyze", prompt)
        self.assertEqual(code, 0)
        import json
        data = json.loads(out)
        self.assertIn("tokens", data)
        self.assertIn("fluff", data)
        self.assertIn("savings", data)

    def test_cli_minify(self):
        prompt = "**Hello**, I hope you are doing well. Please minify this."
        code, out = self._run_cli("minify", prompt)
        self.assertEqual(code, 0)
        self.assertIn("Hello,", out)
        self.assertNotIn("**", out)
        self.assertNotIn("I hope you are doing well", out)

    def test_cli_diff(self):
        prompt = "Line 1\nI hope you are doing well.\nLine 3\n"
        code, out = self._run_cli("diff", prompt)
        self.assertEqual(code, 0)
        # Unified diff header must be present
        self.assertIn("--- original", out)
        self.assertIn("+++ minified", out)


if __name__ == "__main__":
    unittest.main()
