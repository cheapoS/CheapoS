"""Packaged persistence and restart contracts without launching processes."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from cheapos.launch import default_data_directory, restart_arguments


class LaunchTests(unittest.TestCase):
    def test_source_install_retains_its_data_directory(self):
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(default_data_directory('/tmp/source/run.py'),
                             Path('/tmp/source/run.py').resolve().parent / '.cheapos')

    def test_native_app_replacement_keeps_the_same_user_data(self):
        with patch.object(sys, 'platform', 'darwin'), patch.object(sys, 'frozen', False, create=True):
            for app in ('/Applications/cheapoS.app', '/tmp/New/cheapoS.app'):
                self.assertEqual(default_data_directory(app + '/Contents/Resources/run.py'),
                                 Path.home() / 'Library/Application Support/cheapoS')

    def test_frozen_app_keeps_data_outside_extracted_resources(self):
        with patch.object(sys, 'platform', 'darwin'), patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(default_data_directory('/tmp/_MEI123/run.py'),
                             Path.home() / 'Library/Application Support/cheapoS')

    def test_restart_preserves_options_without_duplicating_frozen_entrypoint(self):
        options = ['--port', '5203', '--no-open', '--data-dir', '/tmp/my data']
        with patch.object(sys, 'argv', ['run.py', *options]), patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(restart_arguments(), [sys.executable, 'run.py', *options])
        with patch.object(sys, 'argv', [sys.executable, *options]), patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(restart_arguments(), [sys.executable, *options])
