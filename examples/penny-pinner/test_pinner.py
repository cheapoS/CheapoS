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
        content = "One sentence. Two sentences. Three sentences. Four sentences."
        digest = self.pinner.generate_digest(content)
        self.assertEqual(len(digest), 3)

if __name__ == '__main__':
    unittest.main()
