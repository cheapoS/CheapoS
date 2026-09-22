"""Offline directory discovery, without Git setup, model calls or waits."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cheapos.workspace import Workspace


class BuildArtifactDiscoveryTests(unittest.TestCase):
    def test_explicit_build_directory_is_discoverable_without_expanding_root_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('dist/articles/one/index.html', 'dist/articles/two/index.html', 'src/page.html',
                         'dist/.env', 'dist/nested/.env.production', 'dist/server.key',
                         'dist/node_modules/package/index.js', 'dist/.git/config'):
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('fixture')
            (root / 'dist/linked').symlink_to(root / 'src', target_is_directory=True)
            (root / 'dist/link.html').symlink_to(root / 'src/page.html')
            workspace = Workspace(root)
            with patch('cheapos.workspace.git', return_value='src/page.html\0') as git:
                self.assertEqual(workspace.list_files(), ['src/page.html'])
                git.reset_mock()
                self.assertEqual(workspace.list_files('dist'), ['dist/articles/one/index.html', 'dist/articles/two/index.html'])
                self.assertEqual(workspace.list_files('dist/articles/one'), ['dist/articles/one/index.html'])
                git.assert_not_called()
            self.assertEqual(workspace.read_file('dist/articles/one/index.html')['content'], '1: fixture')
            for path in ('../', str(root / 'dist'), 'dist/linked', 'dist/.git', 'dist/node_modules', 'dist/.env'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    workspace.list_files(path)
