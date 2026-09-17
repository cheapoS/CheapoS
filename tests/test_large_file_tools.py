"""Bounded inspection of snapshot-sized files; no Git, models or waiting."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cheapos import edit_history
from cheapos.engine import Engine, READ_TOOLS
from cheapos.workspace import Workspace, FileVersionError, MAX_FILE_BYTES, MAX_EDIT_BYTES


class LargeFileToolsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workspace = Workspace(self.root)

    def write(self, name, text):
        data = text.encode('utf-8')
        (self.root / name).write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def test_large_python_outline_pages_lead_to_read_search_and_versioned_edit(self):
        text = '# project context padding\n' * 11000 + 'class Example:\n'
        text += ''.join(f'    def method_{n}(self):\n        return {n}\n' for n in range(120))
        original_hash = self.write('large.py', text)
        self.assertGreater(len(text.encode()), 256_000)
        first = self.workspace.outline_file('large.py')
        second = self.workspace.outline_file('large.py', first['next_start_line'])
        self.assertEqual(first['symbols_returned'] + second['symbols_returned'], 121)
        self.assertTrue(first['has_more']); self.assertFalse(second['has_more'])
        self.assertIn('method_119', second['outline'])
        self.assertEqual(first['hash'], original_hash)
        self.assertLessEqual(len(first['outline']), 20000)
        with patch.object(Workspace, 'list_files', return_value=['large.py']):
            matches = self.workspace.search('def method_119')
        self.assertEqual(len(matches), 1)
        line = matches[0]['line']
        excerpt = self.workspace.read_file('large.py', line, line + 1)
        self.assertIn('return 119', excerpt['content'])
        self.assertEqual(excerpt['hash'], original_hash)
        task = {'workspace': str(self.root)}
        result = edit_history.apply(task, self.workspace, 'replace_lines', {
            'path': 'large.py', 'start_line': line + 1, 'end_line': line + 1,
            'new_text': '        return 120\n', 'expected_hash': excerpt['hash']}, self.workspace.replace_lines)
        self.assertTrue(result['updated'])
        self.assertEqual((self.root / 'large.py').read_text(), text.replace('return 119\n', 'return 120\n'))
        with self.assertRaises(FileVersionError):
            self.workspace.replace_lines('large.py', line + 1, line + 1, '        return 121\n', original_hash)
        edit_history.undo(task, self.workspace, 'large.py', result['edit_id'])
        self.assertEqual((self.root / 'large.py').read_text(), text)

    def test_large_javascript_outline_does_not_silently_stop_at_100_symbols(self):
        self.write('app.js', '// padding\n' * 25000 + ''.join(f'async function f{n}() {{}}\n' for n in range(130)))
        first = self.workspace.outline_file('app.js')
        second = self.workspace.outline_file('app.js', first['next_start_line'])
        self.assertEqual(first['symbols_returned'], 100)
        self.assertEqual(second['symbols_returned'], 30)
        self.assertIn('f129', second['outline']); self.assertFalse(second['has_more'])

    def test_long_unicode_lines_can_be_read_completely_in_bounded_pages(self):
        lines = ['one', 'é' * 140000, '', 'last']
        digest = self.write('long.js', '\r\n'.join(lines) + '\r\n')
        line, column, recovered = 1, 1, {}
        while line is not None:
            page = self.workspace.read_file('long.js', line, start_column=column)
            self.assertLessEqual(len(page['content']), 20000)
            self.assertEqual(page['hash'], digest)
            for numbered in page['content'].split('\n'):
                number, content = numbered.split(': ', 1)
                recovered[int(number)] = recovered.get(int(number), '') + content
            following = page['next_line'], page['next_column']
            self.assertNotEqual((line, column), following)
            line, column = following
        self.assertEqual([recovered[n] for n in sorted(recovered)], lines)

    def test_output_paging_and_new_file_and_edit_bounds_are_separate(self):
        digest = self.write('large.txt', 'unchanged\n' * 30000)
        page = self.workspace.read_file('large.txt', 29999)
        self.assertIn('30000: unchanged', page['content'])
        self.assertIsNone(page['next_line'])
        self.assertFalse(page['complete'])
        with self.assertRaisesRegex(ValueError, '256 KB'):
            self.workspace.write_file('new.txt', 'x' * 256001)
        with self.assertRaisesRegex(ValueError, 'Edit is too large'):
            self.workspace.replace_lines('large.txt', 1, 1, 'x' * (MAX_EDIT_BYTES + 1), digest)
        with self.assertRaisesRegex(ValueError, 'Edit is too large'):
            self.workspace.replace_lines('large.txt', 1, 81, 'small', digest)
        self.assertEqual(hashlib.sha256((self.root / 'large.txt').read_bytes()).hexdigest(), digest)

    def test_path_binary_and_snapshot_size_guards_still_apply(self):
        self.write('source.py', 'def ok(): pass\n')
        self.write('.env', 'private')
        (self.root / 'link.py').symlink_to(self.root / 'source.py')
        (self.root / 'oversized').write_bytes(b'x' * (MAX_FILE_BYTES + 1))
        (self.root / 'binary').write_bytes(b'a\0b')
        (self.root / 'invalid').write_bytes(b'\xff')
        for name in ('.env', 'link.py', '../source.py', str(self.root / 'source.py'), 'oversized', 'binary', 'invalid'):
            for inspect in (self.workspace.outline_file, self.workspace.read_file):
                with self.subTest(name=name, tool=inspect.__name__), self.assertRaises(ValueError):
                    inspect(name)
        for arguments in ({'start_column': 0}, {'start_column': 100}, {'start_line': True}):
            with self.assertRaises(ValueError): self.workspace.read_file('source.py', **arguments)
        with self.assertRaises(ValueError): self.workspace.outline_file('source.py', start_line=0)

    def test_worker_and_reviewer_dispatch_accept_continuation_arguments(self):
        self.write('app.js', ''.join(f'function f{n}() {{}}\n' for n in range(110)))
        engine = SimpleNamespace(runtimes={}, event=Mock())
        task = {'id': 'task', 'workspace': str(self.root), 'tool_actions': 0,
                'active_role': 'worker', 'status': 'running', 'providers': {}}
        for role in ('worker', 'reviewer'):
            task['active_role'] = role
            first = Engine.file_tool(engine, task, 'outline_file', {'path': 'app.js'})
            last = Engine.file_tool(engine, task, 'outline_file', {
                'path': 'app.js', 'start_line': first['next_start_line']})
            self.assertIn('f109', last['outline'])
            excerpt = Engine.file_tool(engine, task, 'read_file', {'path': 'app.js', 'start_line': 110, 'start_column': 10})
            self.assertIn('f109', excerpt['content'])
        schemas = {t['function']['name']: t['function']['parameters']['properties'] for t in READ_TOOLS}
        self.assertIn('start_line', schemas['outline_file'])
        self.assertIn('start_column', schemas['read_file'])
