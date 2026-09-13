import json
import os
import tempfile
import unittest
from unittest.mock import patch
from io import StringIO

from scripts.word_count import count, main


class TestCount(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(count(""), (1, 0, 0))

    def test_single_line_no_newline(self):
        self.assertEqual(count("hello world"), (1, 2, 11))

    def test_single_line_with_newline(self):
        self.assertEqual(count("hello world\n"), (1, 2, 12))

    def test_multiple_lines(self):
        self.assertEqual(count("a b\nc d\ne f\n"), (3, 6, 12))

    def test_multiple_lines_no_trailing_newline(self):
        self.assertEqual(count("a b\nc d\ne f"), (3, 6, 11))

    def test_only_newlines(self):
        self.assertEqual(count("\n\n\n"), (3, 0, 3))


class TestMain(unittest.TestCase):
    def test_stdin_output(self):
        with patch("sys.argv", ["word_count.py"]), \
             patch("sys.stdin", StringIO("hello world\n")), \
             patch("sys.stdout", new_callable=StringIO) as fake_out:
            main()
        self.assertEqual(fake_out.getvalue().strip(), "1 2 12")

    def test_file_output(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write("line one\nline two\n")
            path = tmp.name
        try:
            with patch("sys.argv", ["word_count.py", path]), \
                 patch("sys.stdout", new_callable=StringIO) as fake_out:
                main()
            self.assertEqual(fake_out.getvalue().strip(), "2 4 18")
        finally:
            os.unlink(path)

    def test_json_flag(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write("hello world\n")
            path = tmp.name
        try:
            with patch("sys.argv", ["word_count.py", path, "--json"]), \
                 patch("sys.stdout", new_callable=StringIO) as fake_out:
                main()
            result = json.loads(fake_out.getvalue().strip())
            self.assertEqual(result, {"lines": 1, "words": 2, "characters": 12})
        finally:
            os.unlink(path)

    def test_json_stdin(self):
        with patch("sys.stdin", StringIO("a b c\n")), \
             patch("sys.argv", ["word_count.py", "--json"]), \
             patch("sys.stdout", new_callable=StringIO) as fake_out:
            main()
        result = json.loads(fake_out.getvalue().strip())
        self.assertEqual(result, {"lines": 1, "words": 3, "characters": 6})

    def test_file_not_found(self):
        with patch("sys.argv", ["word_count.py", "nonexistent_file.txt"]), \
             self.assertRaises(SystemExit):
            main()


if __name__ == "__main__":
    unittest.main()
