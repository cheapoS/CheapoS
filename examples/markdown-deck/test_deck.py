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

class TestMarkdownDeckExtended(unittest.TestCase):
    def test_empty_file(self):
        md = ""
        deck = MarkdownDeck(md)
        # An empty deck should result in zero slides
        self.assertEqual(len(deck.slides), 0)
        self.assertEqual(deck.notes, [])

    def test_no_separator(self):
        md = "# Only one slide\nContent\n<!-- note: single note -->"
        deck = MarkdownDeck(md)
        self.assertEqual(len(deck.slides), 1)
        self.assertEqual(deck.notes[0], "single note")

    def test_malformed_note(self):
        # Note comment without closing tags
        md = "# Slide\nSome content\n<!-- note: broken note\n---\n# Next\nMore\n<!-- note: next note -->"
        deck = MarkdownDeck(md)
        # First slide note should be empty because pattern not matched
        self.assertEqual(deck.notes[0], "")
        # Second slide note extracted correctly
        self.assertEqual(deck.notes[1], "next note")

    def test_deterministic_output(self):
        md = "# Title\n---\n# Second"
        deck1 = MarkdownDeck(md)
        deck2 = MarkdownDeck(md)
        self.assertEqual(deck1.render(), deck2.render())
        # Bytes comparison
        self.assertEqual(deck1.render().encode('utf-8'), deck2.render().encode('utf-8'))

    def test_note_extraction_multiple_notes(self):
        # Only the first note per slide should be captured
        md = "# Slide\nContent\n<!-- note: first note -->\n<!-- note: second note -->\n---\n# Next\n<!-- note: next note -->"
        deck = MarkdownDeck(md)
        self.assertEqual(deck.notes[0], "first note")
        self.assertEqual(deck.notes[1], "next note")

    def test_note_removed_from_render(self):
        md = "# Slide\nNote content\n<!-- note: this note should not appear in slide -->"
        deck = MarkdownDeck(md)
        html = deck.render()
        # The note comment should not be present in rendered HTML
        self.assertNotIn("note:", html)

if __name__ == '__main__':
    unittest.main()
