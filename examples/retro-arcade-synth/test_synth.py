"""Tests for the Retro Arcade Synth example.

Ensures the synth module can be imported and has a __version__ attribute.
"""

import unittest
import importlib.util
import os

class TestStub(unittest.TestCase):
    def test_stub(self):
        # Determine the path to the synth.py file relative to this test file.
        dir_path = os.path.dirname(__file__)
        synth_path = os.path.join(dir_path, "synth.py")
        spec = importlib.util.spec_from_file_location("synth", synth_path)
        self.assertIsNotNone(spec, "synth module spec should be found")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # Verify version attribute exists and is a string.
        self.assertTrue(hasattr(module, "__version__"))
        self.assertIsInstance(module.__version__, str)

if __name__ == "__main__":
    unittest.main()
