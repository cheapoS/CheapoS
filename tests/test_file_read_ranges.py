"""Read-range defaults with tiny local files; no Git or model calls."""
import tempfile
import unittest
from pathlib import Path
from cheapos.workspace import Workspace


class FileReadRangeTests(unittest.TestCase):
    def test_omitted_end_tracks_start_and_keeps_bounded_numbered_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'app.js').write_text(''.join(f'line {i}\n' for i in range(1, 1951)))
            workspace = Workspace(directory)
            for start, end in ((1, 200), (900, 1099), (1900, 1950), (1910, 1950)):
                with self.subTest(start=start):
                    result = workspace.read_file('app.js', start)
                    self.assertEqual(result['start_line'], start)
                    self.assertEqual(result['end_line'], end)
                    self.assertEqual(result['total_lines'], 1950)
                    self.assertEqual(result['content'].splitlines()[0], f'{start}: line {start}')
                    self.assertEqual(len(result['content'].splitlines()), end-start+1)
                    self.assertTrue(result['hash'])
            self.assertEqual(workspace.read_file('app.js', 400, 900)['end_line'], 699)
            for start, end in ((0, None), (5, 2), ('5', None), (True, None), (5, '9')):
                with self.subTest(start=start,end=end), self.assertRaisesRegex(ValueError, 'Omit end_line'):
                    workspace.read_file('app.js', start, end)
