import io
import sys
import unittest
from unittest.mock import patch

from scripts.csv_to_md import column_widths, format_row, format_separator, read_rows, to_markdown


class TestColumnWidths(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(column_widths([]), [])

    def test_single_row(self):
        self.assertEqual(column_widths([['a', 'bb', 'ccc']]), [1, 2, 3])

    def test_multiple_rows(self):
        rows = [['a', 'bb'], ['ccc', 'd']]
        self.assertEqual(column_widths(rows), [3, 2])


class TestFormatRow(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(format_row(['a', 'bb'], [3, 2]), '| a   | bb |')

    def test_single_column(self):
        self.assertEqual(format_row(['x'], [3]), '| x   |')


class TestFormatSeparator(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(format_separator([3, 2]), '| --- | --- |')


class TestReadRows(unittest.TestCase):
    def test_from_string(self):
        f = io.StringIO('a,b\nc,d\n')
        with patch.object(sys, 'stdin', f):
            rows = read_rows('-', ',')
        self.assertEqual(rows, [['a', 'b'], ['c', 'd']])

    def test_from_file(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
            tmp.write('x,y\n1,2\n')
            path = tmp.name
        try:
            rows = read_rows(path, ',')
            self.assertEqual(rows, [['x', 'y'], ['1', '2']])
        finally:
            os.unlink(path)


class TestToMarkdown(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(to_markdown([]), '')

    def test_with_header(self):
        rows = [['Name', 'Age'], ['Alice', '30'], ['Bob', '25']]
        expected = '| Name  | Age |\n| --- | --- |\n| Alice | 30  |\n| Bob   | 25  |'
        self.assertEqual(to_markdown(rows, has_header=True), expected)

    def test_no_header(self):
        rows = [['Alice', '30'], ['Bob', '25']]
        expected = '| Alice | 30 |\n| Bob   | 25 |'
        self.assertEqual(to_markdown(rows, has_header=False), expected)


class TestMain(unittest.TestCase):
    def test_stdin_with_header(self):
        with patch.object(sys, 'stdin', io.StringIO('a,b\n1,2\n')):
            with patch('sys.argv', ['csv_to_md.py']):
                with patch('sys.stdout', new_callable=io.StringIO) as out:
                    from scripts.csv_to_md import main
                    main()
        self.assertIn('| a | b |', out.getvalue())
        self.assertIn('| --- | --- |', out.getvalue())

    def test_no_header_flag(self):
        with patch.object(sys, 'stdin', io.StringIO('a,b\n1,2\n')):
            with patch('sys.argv', ['csv_to_md.py', '--no-header']):
                with patch('sys.stdout', new_callable=io.StringIO) as out:
                    from scripts.csv_to_md import main
                    main()
        self.assertNotIn('| --- | --- |', out.getvalue())

    def test_delimiter(self):
        with patch.object(sys, 'stdin', io.StringIO('a;b\n1;2\n')):
            with patch('sys.argv', ['csv_to_md.py', '--delimiter', ';']):
                with patch('sys.stdout', new_callable=io.StringIO) as out:
                    from scripts.csv_to_md import main
                    main()
        self.assertIn('| a | b |', out.getvalue())


if __name__ == '__main__':
    unittest.main()