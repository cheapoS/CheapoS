import subprocess
import unittest
import os
import sys

class TestCheapskateLoadEndpoints(unittest.TestCase):
    def test_load_endpoints_missing(self):
        # We can call the status script with a missing config
        result = subprocess.run(["python3", "-B", "examples/cheapskate-status/status.py", "probe", "nonexistent.json"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Error loading config", result.stderr if result.stderr else result.stdout)

if __name__ == "__main__":
    unittest.main()
