import unittest
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__)))
from whisperer import tokenize, parse_log_line, process_file

class TestLogWhisperer(unittest.TestCase):
    def test_tokenize(self):
        line = '192.168.1.1 - - [2026-09-13T10:00:00] "GET /api/user/123 HTTP/1.1" 200 1024'
        expected = '<IP> - - [<TIMESTAMP>] "GET /api/user/<NUM> HTTP/<NUM>.<NUM>" <NUM> <NUM>'
        self.assertEqual(tokenize(line), expected)
    def test_parse_log_line(self):
        line = '{"message": "User 123 logged in", "level": "INFO"}'
        self.assertEqual(parse_log_line(line), "User 123 logged in")
        line = 'plain text log'
        self.assertEqual(parse_log_line(line), "plain text log")
    def test_cluster(self):
        import io, sys, os
        captured = io.StringIO()
        sys_stdout = sys.stdout
        sys.stdout = captured
        try:
            process_file(os.path.join(os.path.dirname(__file__), 'sample.log'), 'cluster')
        finally:
            sys.stdout = sys_stdout
        output = captured.getvalue()
        self.assertIn(':', output)

    def test_detect(self):
        import io, sys, os
        captured = io.StringIO()
        sys_stdout = sys.stdout
        sys.stdout = captured
        try:
            process_file(os.path.join(os.path.dirname(__file__), 'sample.log'), 'detect')
        finally:
            sys.stdout = sys_stdout
        output = captured.getvalue()
        self.assertIsInstance(output, str)

if __name__ == '__main__':
    unittest.main()