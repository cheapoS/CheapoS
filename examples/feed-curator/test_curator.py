import unittest
import json
import os
import sys
from unittest import mock

# Ensure the example directory is on the path
example_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, example_dir)

from curator import fetch_all, deduplicate_entries, cluster_entries, render_digest, load_feeds_list

# Sample XML fixtures
RSS_XML = b'''<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Test Article One</title><link>http://example.com/article1</link></item>
<item><title>Test Article Two</title><link>http://example.com/article2</link></item>
</channel></rss>'''

ATOM_XML = b'''<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom Entry One</title><link href="http://example.com/atom1"/></entry>
<entry><title>Atom Entry Two</title><link href="http://example.com/atom2"/></entry>
</feed>'''

class TestFeedCurator(unittest.TestCase):
    def setUp(self):
        # Ensure feeds.json contains the two test URLs
        self.feeds_path = os.path.join(os.path.dirname(__file__), 'feeds.json')
        with open(self.feeds_path, 'w', encoding='utf-8') as f:
            json.dump(["http://example.com/rss", "http://example.com/atom"], f)

    def mock_urlopen(self, url, *args, **kwargs):
        mock_resp = mock.Mock()
        if 'rss' in url:
            mock_resp.read.return_value = RSS_XML
        else:
            mock_resp.read.return_value = ATOM_XML
        # Context manager support
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = mock.Mock()
        return mock_resp

    @mock.patch('urllib.request.urlopen')
    def test_fetch_all(self, mock_urlopen):
        mock_urlopen.side_effect = self.mock_urlopen
        entries = fetch_all()
        titles = [e['title'] for e in entries]
        self.assertCountEqual(titles, [
            'Test Article One', 'Test Article Two',
            'Atom Entry One', 'Atom Entry Two'
        ])
        self.assertEqual(len(entries), 4)

    def test_deduplicate(self):
        # Create entries with duplicate URL and similar titles
        entries = [
            {'title': 'Test Article One', 'link': 'http://example.com/article1'},
            {'title': 'test article one', 'link': 'http://example.com/article1?ref=abc'},
            {'title': 'Unique Story', 'link': 'http://example.com/unique'},
        ]
        deduped = deduplicate_entries(entries)
        # URL duplicate should be removed, title similarity should remove second entry
        self.assertEqual(len(deduped), 2)
        self.assertIn('Test Article One', [e['title'] for e in deduped])
        self.assertIn('Unique Story', [e['title'] for e in deduped])

    def test_cluster_and_render(self):
        entries = [
            {'title': 'Test Article One', 'link': 'http://example.com/article1'},
            {'title': 'Test Article Two', 'link': 'http://example.com/article2'},
            {'title': 'Atom Entry One', 'link': 'http://example.com/atom1'},
            {'title': 'Solo Story', 'link': 'http://example.com/solo'},
        ]
        clusters = cluster_entries(entries)
        # Entries sharing 'article' should be together. 
        # 'atom' entries should be in 'atom' cluster.
        self.assertTrue(any('Article' in e['title'] for c in clusters.values() for e in c))
        self.assertIn('atom', clusters)
        self.assertIn('misc', clusters)
        # Render markdown and check links
        md = render_digest(clusters)
        self.assertIn('[Test Article One](http://example.com/article1)', md)
        self.assertIn('[Solo Story](http://example.com/solo)', md)
if __name__ == '__main__':
    unittest.main()
