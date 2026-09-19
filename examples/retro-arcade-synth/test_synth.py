"""Tests for the Retro Arcade Synth example.

Ensures the synth module can be imported and has a __version__ attribute.
"""

import unittest
import importlib.util
import os
import array


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


class TestSynthFunctions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load the synth module for testing functions.
        dir_path = os.path.dirname(__file__)
        synth_path = os.path.join(dir_path, "synth.py")
        spec = importlib.util.spec_from_file_location("synth", synth_path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_generate_samples_type_and_length(self):
        arr = self.module.generate_samples(0.1, 440)
        self.assertIsInstance(arr, array.array)
        self.assertEqual(arr.typecode, 'h')
        expected_len = round(0.1 * self.module.SAMPLE_RATE)
        self.assertEqual(len(arr), expected_len)

    def test_apply_envelope_first_sample_zero(self):
        samples = self.module.generate_samples(0.2, 440)
        env = self.module.apply_envelope(samples, self.module.SAMPLE_RATE, attack=0.5)
        self.assertEqual(env[0], 0)

    def test_mix_samples_clamps(self):
        max_amp = self.module.MAX_AMP
        a = array.array('h', [max_amp] * 5)
        b = array.array('h', [max_amp] * 5)
        mixed = self.module.mix_samples(a, b)
        for v in mixed:
            self.assertEqual(v, max_amp)

    def test_repeat_sample_length(self):
        a = array.array('h', [1, 2, 3])
        repeated = self.module.repeat_sample(a, 3)
        self.assertEqual(len(repeated), len(a) * 3)


if __name__ == "__main__":
    unittest.main()