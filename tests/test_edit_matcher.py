"""Unit tests for context-anchored block matching and multi-chunk editing."""

import unittest
from cheapos.edit_matcher import (
    apply_chunks,
    match_chunk,
    TargetNotFoundError,
    TargetAmbiguousError,
    OverlappingChunksError,
    SyntaxValidationError,
    EditMatchError,
)

SAMPLE_PYTHON_FILE = """import os
import sys

def calculate_total(items, tax_rate=0.05):
    total = sum(item['price'] for item in items)
    tax = total * tax_rate
    return total + tax

def format_receipt(items, total):
    lines = [f"{i['name']}: ${i['price']:.2f}" for i in items]
    lines.append(f"Total: ${total:.2f}")
    return "\\n".join(lines)

def main():
    items = [{'name': 'Apple', 'price': 1.50}, {'name': 'Banana', 'price': 0.75}]
    total = calculate_total(items)
    print(format_receipt(items, total))

if __name__ == '__main__':
    main()
"""


class TestEditMatcher(unittest.TestCase):

    def test_exact_single_line_replacement(self):
        chunks = [{"target": "tax_rate=0.05", "replacement": "tax_rate=0.10"}]
        result, count = apply_chunks(SAMPLE_PYTHON_FILE, chunks, filename="sample.py")
        self.assertEqual(count, 1)
        self.assertIn("tax_rate=0.10", result)
        self.assertNotIn("tax_rate=0.05", result)

    def test_exact_multi_line_replacement(self):
        target = """def calculate_total(items, tax_rate=0.05):
    total = sum(item['price'] for item in items)
    tax = total * tax_rate
    return total + tax"""

        replacement = """def calculate_total(items, tax_rate=0.08, discount=0.0):
    subtotal = sum(item['price'] for item in items)
    discounted = subtotal * (1 - discount)
    return discounted * (1 + tax_rate)"""

        chunks = [{"target": target, "replacement": replacement}]
        result, count = apply_chunks(SAMPLE_PYTHON_FILE, chunks, filename="sample.py")
        self.assertEqual(count, 1)
        self.assertIn("discount=0.0", result)
        self.assertIn("discounted * (1 + tax_rate)", result)

    def test_multi_chunk_atomic_replacement(self):
        # Chunk 1: top of file (import)
        # Chunk 2: middle of file (function)
        # Chunk 3: bottom of file (main print)
        chunks = [
            {"target": "import sys\n", "replacement": "import sys\nimport math\n"},
            {
                "target": "    tax = total * tax_rate\n    return total + tax",
                "replacement": "    tax = round(total * tax_rate, 2)\n    return round(total + tax, 2)",
            },
            {
                "target": "    print(format_receipt(items, total))",
                "replacement": "    receipt = format_receipt(items, total)\n    print(receipt)",
            },
        ]
        result, count = apply_chunks(SAMPLE_PYTHON_FILE, chunks, filename="sample.py")
        self.assertEqual(count, 3)
        self.assertIn("import math", result)
        self.assertIn("round(total * tax_rate, 2)", result)
        self.assertIn("receipt = format_receipt(items, total)", result)

    def test_whitespace_resilience_trailing_spaces(self):
        # Target with trailing spaces that don't exist in source, or vice-versa
        target = "def calculate_total(items, tax_rate=0.05):   \n    total = sum(item['price'] for item in items)  \n"
        replacement = "def calculate_total(items, tax_rate=0.05):\n    # Optimized sum\n    total = sum(item['price'] for item in items)\n"
        chunks = [{"target": target, "replacement": replacement}]
        result, count = apply_chunks(SAMPLE_PYTHON_FILE, chunks, filename="sample.py")
        self.assertEqual(count, 1)
        self.assertIn("# Optimized sum", result)

    def test_crlf_vs_lf_resilience(self):
        crlf_content = SAMPLE_PYTHON_FILE.replace("\n", "\r\n")
        target = "def format_receipt(items, total):\n    lines = [f\"{i['name']}: ${i['price']:.2f}\" for i in items]"
        replacement = "def format_receipt(items, total):\n    # Format lines\n    lines = [f\"{i['name']}: ${i['price']:.2f}\" for i in items]"
        chunks = [{"target": target, "replacement": replacement}]
        result, count = apply_chunks(crlf_content, chunks, filename="sample.py")
        self.assertEqual(count, 1)
        self.assertIn("# Format lines", result)

    def test_target_ambiguous_error(self):
        # 'items' or 'total' alone appears many times
        chunks = [{"target": "total", "replacement": "grand_total"}]
        with self.assertRaises(TargetAmbiguousError) as ctx:
            apply_chunks(SAMPLE_PYTHON_FILE, chunks, filename="sample.py")
        self.assertIn("matches", str(ctx.exception))
        self.assertIn("Add 1–3 lines of surrounding context", str(ctx.exception))
        self.assertGreater(ctx.exception.details["match_count"], 1)
        self.assertTrue(len(ctx.exception.details["lines"]) > 1)

    def test_target_not_found_with_diff_diagnostic(self):
        # Slight hallucination in the middle of a function
        target = """def calculate_total(items, tax_rate=0.05):
    subtotal = sum(item['price'] for item in items)
    tax = subtotal * tax_rate
    return subtotal + tax"""

        chunks = [{"target": target, "replacement": "pass"}]
        with self.assertRaises(TargetNotFoundError) as ctx:
            apply_chunks(SAMPLE_PYTHON_FILE, chunks, filename="sample.py")
        err_msg = str(ctx.exception)
        self.assertIn("Closest match found", err_msg)
        self.assertIn("Differences:", err_msg)
        self.assertIn("closest_match", ctx.exception.details)
        self.assertGreaterEqual(ctx.exception.details["closest_match"]["similarity"], 50.0)

    def test_overlapping_chunks_rejected(self):
        chunks = [
            {
                "target": "def calculate_total(items, tax_rate=0.05):\n    total = sum(item['price'] for item in items)",
                "replacement": "# Function 1",
            },
            {
                "target": "    total = sum(item['price'] for item in items)\n    tax = total * tax_rate",
                "replacement": "# Function 2",
            },
        ]
        with self.assertRaises(OverlappingChunksError) as ctx:
            apply_chunks(SAMPLE_PYTHON_FILE, chunks, filename="sample.py")
        self.assertIn("overlaps", str(ctx.exception))
        self.assertEqual(ctx.exception.details["chunk_a"], 1)
        self.assertEqual(ctx.exception.details["chunk_b"], 2)

    def test_syntax_validation_rejects_invalid_python(self):
        # Break syntax intentionally
        chunks = [{"target": "return total + tax", "replacement": "return total + "}]
        with self.assertRaises(SyntaxValidationError) as ctx:
            apply_chunks(SAMPLE_PYTHON_FILE, chunks, filename="sample.py")
        self.assertIn("syntax error", str(ctx.exception))
        self.assertEqual(ctx.exception.details["lineno"], 7)

    def test_syntax_validation_skipped_for_non_python(self):
        # Non-python files (e.g. .txt, .md) should not fail python ast parse
        text = "Hello world:\nthis is not valid python def () {"
        chunks = [{"target": "Hello world:", "replacement": "Greetings:"}]
        result, count = apply_chunks(text, chunks, filename="notes.txt")
        self.assertEqual(count, 1)
        self.assertIn("Greetings:", result)

    def test_single_dict_chunk_convenience(self):
        chunk = {"target": "import os", "replacement": "import os, math"}
        result, count = apply_chunks(SAMPLE_PYTHON_FILE, chunk, filename="sample.py")
        self.assertEqual(count, 1)
        self.assertIn("import os, math", result)

    def test_invalid_chunk_arguments(self):
        with self.assertRaises(EditMatchError):
            apply_chunks(SAMPLE_PYTHON_FILE, ["not a dict"])
        with self.assertRaises(EditMatchError):
            apply_chunks(SAMPLE_PYTHON_FILE, [{"target": 123, "replacement": "abc"}])
        with self.assertRaises(TargetNotFoundError):
            apply_chunks(SAMPLE_PYTHON_FILE, [{"target": "", "replacement": "abc"}])


    def test_deletion_of_function(self):
        # Delete format_receipt completely
        target = """def format_receipt(items, total):
    lines = [f"{i['name']}: ${i['price']:.2f}" for i in items]
    lines.append(f"Total: ${total:.2f}")
    return "\\n".join(lines)\n\n"""
        chunks = [{"target": target, "replacement": ""}]
        result, count = apply_chunks(SAMPLE_PYTHON_FILE, chunks, filename="sample.py")
        self.assertEqual(count, 1)
        self.assertNotIn("def format_receipt", result)
        # Should still be valid Python
        self.assertIn("def calculate_total", result)

    def test_insert_at_beginning_of_file(self):
        target = "import os\n"
        replacement = "#!/usr/bin/env python3\n# (C) 2026 cheapoS\nimport os\n"
        result, count = apply_chunks(SAMPLE_PYTHON_FILE, [{"target": target, "replacement": replacement}], filename="sample.py")
        self.assertEqual(count, 1)
        self.assertTrue(result.startswith("#!/usr/bin/env python3\n# (C) 2026 cheapoS\nimport os\n"))

    def test_append_at_end_of_file(self):
        target = "if __name__ == '__main__':\n    main()\n"
        replacement = "if __name__ == '__main__':\n    main()\n\n# End of script\n"
        result, count = apply_chunks(SAMPLE_PYTHON_FILE, [{"target": target, "replacement": replacement}], filename="sample.py")
        self.assertEqual(count, 1)
        self.assertTrue(result.endswith("# End of script\n"))

    def test_crlf_preservation_in_replacement(self):
        crlf_content = "def foo():\r\n    return 1\r\n"
        chunks = [{"target": "    return 1\r\n", "replacement": "    # Add comment\n    return 2\n"}]
        result, count = apply_chunks(crlf_content, chunks, filename="sample.py")
        self.assertEqual(count, 1)
        self.assertIn("\r\n", result)
        self.assertNotIn("return 2\n", result.replace("\r\n", ""))  # All newlines must be CRLF
        self.assertEqual(result, "def foo():\r\n    # Add comment\r\n    return 2\r\n")

    def test_large_file_multi_chunk_edits(self):
        # 1,000 line file with functions at line 10, line 500, line 980
        lines = [f"# Filler line {i}" for i in range(1000)]
        lines[10] = "def func_top():\n    return 'top'"
        lines[500] = "def func_mid():\n    return 'mid'"
        lines[980] = "def func_bot():\n    return 'bot'"
        content = "\n".join(lines) + "\n"

        chunks = [
            {"target": "def func_top():\n    return 'top'", "replacement": "def func_top():\n    return 'top_modified'"},
            {"target": "def func_mid():\n    return 'mid'", "replacement": "def func_mid():\n    return 'mid_modified'"},
            {"target": "def func_bot():\n    return 'bot'", "replacement": "def func_bot():\n    return 'bot_modified'"},
        ]
        result, count = apply_chunks(content, chunks, filename="large.py")
        self.assertEqual(count, 3)
        self.assertIn("top_modified", result)
        self.assertIn("mid_modified", result)
        self.assertIn("bot_modified", result)


class TestWorkspaceReplaceContentIntegration(unittest.TestCase):

    def setUp(self):
        import tempfile, shutil
        from cheapos.workspace import Workspace
        self.tmp_dir = tempfile.mkdtemp()
        self.workspace = Workspace(self.tmp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir)

    def test_workspace_replace_content_single_and_chunks(self):
        file_path = self.workspace.path("module.py")
        file_path.write_text("def a():\n    return 1\n\ndef b():\n    return 2\n", encoding="utf-8")

        # 1. Single target and replacement
        res = self.workspace.replace_content("module.py", target="return 1", replacement="return 10")
        self.assertTrue(res["updated"])
        self.assertEqual(res["chunks_applied"], 1)
        self.assertIn("return 10", file_path.read_text(encoding="utf-8"))

        # 2. Multi-chunk edit
        chunks = [
            {"target": "def a():\n    return 10", "replacement": "def a():\n    return 100"},
            {"target": "def b():\n    return 2", "replacement": "def b():\n    return 200"},
        ]
        res = self.workspace.replace_content("module.py", chunks=chunks)
        self.assertTrue(res["updated"])
        self.assertEqual(res["chunks_applied"], 2)
        content = file_path.read_text(encoding="utf-8")
        self.assertIn("return 100", content)
        self.assertIn("return 200", content)

    def test_workspace_replace_content_undo(self):
        from cheapos import edit_history
        file_path = self.workspace.path("service.py")
        original = "def service():\n    return 'ok'\n"
        file_path.write_text(original, encoding="utf-8")

        task = {"id": "t1", "workspace": self.tmp_dir, "edit_history": [], "active_role": "worker"}
        args = {"path": "service.py", "target": "return 'ok'", "replacement": "return 'modified'"}

        # Apply via edit_history
        result = edit_history.apply(task, self.workspace, "replace_content", args, self.workspace.replace_content)
        self.assertTrue(result["updated"])
        self.assertIn("return 'modified'", file_path.read_text(encoding="utf-8"))
        self.assertTrue(len(task["edit_history"]) > 0)

        # Undo via edit_history
        receipt_id = result["edit_id"]
        undo_res = edit_history.undo(task, self.workspace, path="service.py", edit_id=receipt_id)
        self.assertTrue(undo_res.get("restored", undo_res.get("updated", False)))
        self.assertEqual(file_path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
