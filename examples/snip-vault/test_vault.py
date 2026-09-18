import unittest
import os
import sys
import json
import subprocess
import tempfile

# Add directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from vault import SnipVault, detect_language
class TestSnipVault(unittest.TestCase):
    def setUp(self):
        self.db_path = tempfile.mktemp()
        self.vault = SnipVault(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_detect_language(self):
        self.assertEqual(detect_language("def foo(): print('hi')"), "python")
        self.assertEqual(detect_language("console.log('hi');"), "javascript")
        self.assertEqual(detect_language("SELECT * FROM table;"), "sql")
        self.assertEqual(detect_language("echo 'hi'"), "bash")
        self.assertEqual(detect_language("Just some text"), "text")

    def test_add_and_search(self):
        self.vault.add("Test", "Desc", "print('hi')", "python", "test,tag")
        results = self.vault.search("hi")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Test")

    def test_cli_add(self):
        cmd = [
            "python3", "examples/snip-vault/vault.py", 
            "--db", self.db_path, 
            "add", "--title", "CLI", "--code", "print('cmd')", "--language", "python"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Added snippet", result.stdout)

    def test_cli_search(self):
        self.vault.add("SearchMe", "Desc", "console.log('find me')", "javascript", "")
        cmd = [
            "python3", "examples/snip-vault/vault.py", 
            "--db", self.db_path, 
            "search", "find"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("SearchMe", result.stdout)


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


if __name__ == "__main__":
    unittest.main()
