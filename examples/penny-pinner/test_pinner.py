import unittest
from .pinner import PennyPinner

class TestPennyPinner(unittest.TestCase):
    def setUp(self):
        self.pinner = PennyPinner(":memory:")

    def test_add_and_search(self):
        self.pinner.add("https://example.com", "Example", "This is an example content.")
        self.pinner.add("https://test.com", "Test", "This is a test content.")
        
        results = self.pinner.search("example")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Example")

    def test_digest(self):
        url = "https://example.com"
        content = "One sentence. Two sentences. Three sentences. Four sentences."
        self.pinner.add(url, "Title", content)
        digest = self.pinner.generate_digest(url)
        lines = digest.split("\n")
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("- One sentence."))
        self.assertTrue(lines[1].startswith("- Two sentences."))
        self.assertTrue(lines[2].startswith("- Three sentences."))

    def test_get_bookmark(self):
        rowid = self.pinner.add("https://test.com", "Title", "Content")
        bookmark = self.pinner.get_bookmark(rowid)
        self.assertEqual(bookmark["title"], "Title")

if __name__ == '__main__':
    unittest.main()
