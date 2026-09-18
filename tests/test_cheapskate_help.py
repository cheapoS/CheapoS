import subprocess
import unittest

class TestCheapskateHelp(unittest.TestCase):
    def test_help_output(self):
        result = subprocess.run(["python3", "-B", "examples/cheapskate-status/status.py", "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertGreater(len(result.stdout), 0, "Help output should not be empty")

if __name__ == "__main__":
    unittest.main()
