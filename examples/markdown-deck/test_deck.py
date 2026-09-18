import pathlib
import tempfile
import sys, os
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deck import MarkdownDeck

class TestMarkdownDeck(unittest.TestCase):
    def test_split_and_notes(self):
        md = """# Title\nContent\n<!-- note: First slide note -->\n---\n## Second\nMore content\n<!-- note: Second note -->\n"""
        deck = MarkdownDeck(md)
        self.assertEqual(len(deck.slides), 2)
        self.assertEqual(deck.notes[0], "First slide note")
        self.assertEqual(deck.notes[1], "Second note")

    def test_render_contains_navigation(self):
        md = "# One\n---\n# Two"
        deck = MarkdownDeck(md)
        html = deck.render()
        # navigation JS should be present
        self.assertIn('document.addEventListener', html)
        self.assertIn('ArrowRight', html)
        self.assertIn('fullscreen', html.lower())
        # theme toggle via 'T' key
        self.assertIn('toggleTheme', html)
        # No external link tags
        self.assertNotIn('<link', html)
        self.assertNotIn('<script src', html)

    def test_build_creates_file(self):
        md = "# Hello"
        with tempfile.TemporaryDirectory() as tmp:
            src = pathlib.Path(tmp) / "src.md"
            dst = pathlib.Path(tmp) / "out.html"
            src.write_text(md, encoding="utf-8")
            MarkdownDeck.build(str(src), str(dst))
            self.assertTrue(dst.is_file())
            content = dst.read_text(encoding="utf-8")
            self.assertIn('<!DOCTYPE html>', content)
            self.assertIn('<h1>Hello</h1>', content)

if __name__ == '__main__':
    unittest.main()
