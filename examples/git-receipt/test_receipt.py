import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sys
import hashlib

# Allow importing receipt.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import receipt
from receipt import compute_receipt_hash, verify_receipt, generate_receipt, get_commits

class TestGitReceipt(unittest.TestCase):
    def setUp(self):
        self.author = "Test Author"
        self.commits = ["hash1", "hash2", "hash3"]
        self.receipt_file = "test_receipt.json"

    def tearDown(self):
        if os.path.exists(self.receipt_file):
            os.remove(self.receipt_file)
        if os.path.exists("badge.svg"):
            os.remove("badge.svg")
        if os.path.exists("receipt.json"):
            os.remove("receipt.json")

    def test_compute_receipt_hash(self):
        # Deterministic check
        h1 = compute_receipt_hash(self.author, self.commits)
        h2 = compute_receipt_hash(self.author, self.commits)
        self.assertEqual(h1, h2)
        
        # Change in author should change hash
        h3 = compute_receipt_hash("Other Author", self.commits)
        self.assertNotEqual(h1, h3)
        
        # Change in commits should change hash
        h4 = compute_receipt_hash(self.author, ["hash1", "hash2"])
        self.assertNotEqual(h1, h4)
    @patch("receipt.subprocess.run")
    def test_get_commits(self, mock_run):
        mock_run.return_value = MagicMock(stdout="hash2\nhash1\nhash3\n", returncode=0)
        commits = get_commits(self.author)
        self.assertEqual(commits, ["hash1", "hash2", "hash3"])

    @patch("receipt.get_commits")
    def test_generate_and_verify_success(self, mock_get_commits):
        mock_get_commits.return_value = self.commits
        generate_receipt(self.author)
        self.assertTrue(os.path.exists("receipt.json"))
        # Verify using generated file
        self.assertTrue(verify_receipt("receipt.json"))

    def test_verify_failure_mismatch(self):
        # We need to simulate a mismatch, but keep it simple
        receipt_data = {
            "author": self.author,
            "commits": ["hash1", "hash2"],
            "receipt_hash": "wronghash",
            "timestamp": "2023-01-01T00:00:00"
        }
        with open(self.receipt_file, "w") as f:
            json.dump(receipt_data, f)
        self.assertFalse(verify_receipt(self.receipt_file))

    def test_verify_invalid_file(self):
        self.assertFalse(verify_receipt("non_existent.json"))

if __name__ == "__main__":
    unittest.main()