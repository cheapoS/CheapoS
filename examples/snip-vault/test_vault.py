import unittest
import os
import sys
import json
import subprocess
import tempfile

# Insert snip-vault directory so vault can be imported directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vault import SnipVault, detect_language

VAULT_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vault.py")


class TestLanguageDetection(unittest.TestCase):
    """5 test methods covering detect_language heuristics."""

    def test_python_detected(self):
        self.assertEqual(detect_language("def foo(): pass"), "python")

    def test_javascript_detected(self):
        self.assertEqual(detect_language("console.log('hi');"), "javascript")

    def test_sql_detected(self):
        self.assertEqual(detect_language("SELECT * FROM users;"), "sql")

    def test_bash_detected(self):
        self.assertEqual(detect_language("echo 'hello'"), "bash")

    def test_text_fallback(self):
        self.assertEqual(detect_language("Just some plain text"), "text")


class TestSnipVaultCore(unittest.TestCase):
    """At least 16 test methods covering SnipVault API."""

    def setUp(self):
        self.vault = SnipVault(":memory:")

    def tearDown(self):
        self.vault.close()

    def test_add_returns_integer_id(self):
        id_ = self.vault.add("T", "D", "print('x')", "python", "t")
        self.assertIsInstance(id_, int)

    def test_add_first_id_is_one(self):
        id_ = self.vault.add("T", "D", "x = 1", "python", "")
        self.assertEqual(id_, 1)

    def test_add_increments_ids(self):
        id1 = self.vault.add("A", "", "a=1", "python", "")
        id2 = self.vault.add("B", "", "b=2", "python", "")
        self.assertEqual(id2, id1 + 1)

    def test_add_auto_detects_language(self):
        id_ = self.vault.add("T", "D", "def foo(): pass", None, "")
        row = self.vault.get(id_)
        self.assertEqual(row["language"], "python")

    def test_add_stores_title(self):
        id_ = self.vault.add("MyTitle", "D", "x=1", "python", "")
        self.assertEqual(self.vault.get(id_)["title"], "MyTitle")

    def test_add_stores_code(self):
        id_ = self.vault.add("T", "D", "unique_xyz_code", "text", "")
        self.assertEqual(self.vault.get(id_)["code"], "unique_xyz_code")

    def test_add_stores_description(self):
        id_ = self.vault.add("T", "My desc", "x=1", "python", "")
        self.assertEqual(self.vault.get(id_)["description"], "My desc")

    def test_add_stores_tags(self):
        id_ = self.vault.add("T", "D", "x=1", "python", "alpha,beta")
        self.assertEqual(self.vault.get(id_)["tags"], "alpha,beta")

    def test_search_finds_by_code(self):
        self.vault.add("T", "D", "unique_token_abc", "text", "")
        self.assertEqual(len(self.vault.search("unique_token_abc")), 1)


    def test_search_empty_query(self):
        self.vault.add("Test1", "Desc", "code one", "python", "")
        self.vault.add("Test2", "Desc", "code two", "python", "")
        results = self.vault.search("")
        self.assertEqual(len(results), 2, f"Expected 2 snippets, got {len(results)}")

    def test_search_fts_operators(self):
        self.vault.add("Hello World", "Desc", "hello world", "python", "")
        self.vault.add("Hello Python", "Desc", "hello python", "python", "")
        results = self.vault.search("hello AND world")
        self.assertEqual(len(results), 1, f"Expected 1 result, got {len(results)}")

    def test_copy_and_seed(self):
        snippet_id = self.vault.add("T", "D", "MyCode", "text", "tag1")
        copied = self.vault.copy(snippet_id)
        self.assertIn("MyCode", copied)
        seed_path = tempfile.mktemp(suffix=".json")
        with open(seed_path, "w") as f:
            json.dump([{
                "title": "S", "description": "Seed", "code": "seed code",
                "language": "text", "tags": ["s"]
            }], f)
        count = self.vault.seed(seed_path)
        self.assertEqual(count, 1)
        os.remove(seed_path)
    def test_search_finds_by_title(self):
        self.vault.add("AlphaTitle", "D", "x=1", "python", "")
        results = self.vault.search("AlphaTitle")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "AlphaTitle")

    def test_search_finds_by_description(self):
        self.vault.add("T", "BetaDesc", "x=1", "python", "")
        self.assertEqual(len(self.vault.search("BetaDesc")), 1)

    def test_search_empty_returns_all(self):
        self.vault.add("A", "D", "code a", "text", "")
        self.vault.add("B", "D", "code b", "text", "")
        self.assertEqual(len(self.vault.search("")), 2)

    def test_search_fts_and_operator(self):
        self.vault.add("Hello World", "D", "hello world", "text", "")
        self.vault.add("Hello Python", "D", "hello python", "text", "")
        results = self.vault.search("hello AND world")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Hello World")

class TestCLI(unittest.TestCase):
    """At least 4 CLI integration tests using subprocess."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _run(self, *args):
        return subprocess.run(
            ["python3", VAULT_PY, "--db", self.db_path] + list(args),
            capture_output=True, text=True
        )

    def test_cli_add_exits_zero(self):
        result = self._run("add", "--title", "CLI", "--code", "print('x')", "--language", "python")
        self.assertEqual(result.returncode, 0)

    def test_cli_add_prints_added(self):
        result = self._run("add", "--title", "CLI", "--code", "print('x')", "--language", "python")
        self.assertIn("Added snippet", result.stdout)

    def test_cli_search_finds_snippet(self):
        self._run("add", "--title", "SearchTarget", "--code", "console.log('find');", "--language", "javascript")
        result = self._run("search", "SearchTarget")
        self.assertEqual(result.returncode, 0)
        self.assertIn("SearchTarget", result.stdout)

    def test_cli_add_with_tags(self):
        result = self._run(
            "add", "--title", "Tagged", "--code", "x=1",
            "--language", "python", "--tags", "foo,bar"
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Added snippet", result.stdout)

if __name__ == "__main__":
    unittest.main()