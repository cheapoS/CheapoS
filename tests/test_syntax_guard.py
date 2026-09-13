"""Tests for syntax pre-validation and outline_file symbol navigation."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cheapos.workspace import Workspace
from test_engine import LocalCase


class SyntaxGuardTests(LocalCase):
    def test_validate_syntax_python_and_json(self):
        task = self.fixture()
        ws = Workspace(task['workspace'])

        # Valid Python
        ws.write_file('valid.py', 'def add(a, b):\n    return a + b\n')
        self.assertIsNone(ws.validate_syntax('valid.py'))

        # Invalid Python - SyntaxError
        res = ws.write_file('broken_syntax.py', 'def bad(:\n    pass\n')
        self.assertIn('syntax_warning', res)
        self.assertIn('SyntaxError', res['syntax_warning'])
        self.assertIn('line 1', res['syntax_warning'])

        # Invalid Python - IndentationError
        res = ws.write_file('broken_indent.py', 'def bad():\npass\n')
        self.assertIn('syntax_warning', res)
        self.assertIn('line 2', res['syntax_warning'])

        # Valid JSON
        res = ws.write_file('valid.json', '{"key": "value", "count": 42}')
        self.assertNotIn('syntax_warning', res)
        self.assertIsNone(ws.validate_syntax('valid.json'))

        # Invalid JSON
        res = ws.write_file('broken.json', '{"key": "value", trailing}')
        self.assertIn('syntax_warning', res)
        self.assertIn('FormatError', res['syntax_warning'])

        # Other file types do not trigger warnings
        res = ws.write_file('notes.txt', 'This is plain text with { broken syntax')
        self.assertNotIn('syntax_warning', res)
        self.assertIsNone(ws.validate_syntax('notes.txt'))

    def test_replace_text_and_replace_lines_syntax_warnings(self):
        task = self.fixture()
        ws = Workspace(task['workspace'])

        # Start with valid python
        ws.write_file('calculator.py', 'def calc():\n    return 10\n')

        # Replace text with syntax error
        res = ws.replace_text('calculator.py', 'return 10', 'return (10 +')
        self.assertIn('syntax_warning', res)
        self.assertIn('SyntaxError', res['syntax_warning'])

        # Fix syntax with replace_text
        res = ws.replace_text('calculator.py', 'return (10 +', 'return 10 + 5')
        self.assertNotIn('syntax_warning', res)

        # Replace lines with indentation error
        digest = ws.read_file('calculator.py')['hash']
        res = ws.replace_lines('calculator.py', 2, 2, 'return 20', digest)
        self.assertIn('syntax_warning', res)
        self.assertIn('line 2', res['syntax_warning'])

        # Fix lines
        digest = ws.read_file('calculator.py')['hash']
        res = ws.replace_lines('calculator.py', 2, 2, '    return 20', digest)
        self.assertNotIn('syntax_warning', res)

    def test_outline_file_python_symbols(self):
        task = self.fixture()
        ws = Workspace(task['workspace'])

        py_content = (
            'import os\n\n'
            'class MathHelper:\n'
            '    def add(self, a, b):\n'
            '        return a + b\n\n'
            '    def multiply(self, x, y):\n'
            '        return x * y\n\n'
            'def standalone_func(data):\n'
            '    return len(data)\n'
        )
        ws.write_file('helper.py', py_content)

        outline = ws.outline_file('helper.py')
        self.assertEqual(outline['path'], 'helper.py')
        self.assertIn('class MathHelper (lines 3–8)', outline['outline'])
        self.assertIn('  def add(self, a, b) (lines 4–5)', outline['outline'])
        self.assertIn('  def multiply(self, x, y) (lines 7–8)', outline['outline'])
        self.assertIn('def standalone_func(data) (lines 10–11)', outline['outline'])
        self.assertEqual(outline['total_lines'], 11)

    def test_outline_file_non_python(self):
        task = self.fixture()
        ws = Workspace(task['workspace'])

        js_content = (
            '// Module header\n'
            'class UIController {\n'
            '  constructor() {}\n'
            '}\n'
            'function helper() {\n'
            '  return 1;\n'
            '}\n'
        )
        ws.write_file('ui.js', js_content)

        outline = ws.outline_file('ui.js')
        self.assertEqual(outline['path'], 'ui.js')
        self.assertIn('line 2: class UIController', outline['outline'])
        self.assertIn('line 5: function helper', outline['outline'])

    def test_engine_outline_file_tool_dispatch(self):
        task = self.fixture()
        ws = Workspace(task['workspace'])
        ws.write_file('example.py', 'def greet(name):\n    return "hello " + name\n')

        res = self.engine.file_tool(task, 'outline_file', {'path': 'example.py'})
        self.assertIn('def greet(name)', res['outline'])
        self.assertEqual(res['total_lines'], 2)


if __name__ == '__main__':
    unittest.main()
