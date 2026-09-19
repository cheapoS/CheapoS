import unittest
import importlib.util
import os
import array
import io
import json
import tempfile
import wave
from contextlib import redirect_stdout, redirect_stderr

# Load the synth module
dir_path = os.path.dirname(__file__)
synth_path = os.path.join(dir_path, "synth.py")
spec = importlib.util.spec_from_file_location("synth", synth_path)
synth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(synth)

class TestGenerateSamples(unittest.TestCase):
    def test_length(self):
        samples = synth.generate_samples(0.1, 440)
        self.assertEqual(len(samples), round(0.1 * synth.SAMPLE_RATE))

    def test_typecode(self):
        samples = synth.generate_samples(0.1, 440)
        self.assertEqual(samples.typecode, 'h')

    def test_square_range(self):
        samples = synth.generate_samples(0.01, 100, waveform='square')
        for s in samples:
            self.assertIn(s, [synth.MAX_AMP, -synth.MAX_AMP])

    def test_triangle_range(self):
        samples = synth.generate_samples(0.01, 100, waveform='triangle')
        for s in samples:
            self.assertGreaterEqual(s, -synth.MAX_AMP)
            self.assertLessEqual(s, synth.MAX_AMP)

    def test_sawtooth_range(self):
        samples = synth.generate_samples(0.01, 100, waveform='sawtooth')
        for s in samples:
            self.assertGreaterEqual(s, -synth.MAX_AMP)
            self.assertLessEqual(s, synth.MAX_AMP)

    def test_freq_slide_nocrash(self):
        samples = synth.generate_samples(0.1, 440, 880)
        self.assertGreater(len(samples), 0)

class TestEnvelope(unittest.TestCase):
    def test_attack_first_sample_zero(self):
        samples = synth.generate_samples(0.1, 440)
        env = synth.apply_envelope(samples, synth.SAMPLE_RATE, attack=0.5)
        # Check that the first sample is close to zero
        self.assertLessEqual(abs(env[0]), 1)

    def test_sustain_level(self):
        samples = array.array('h', [synth.MAX_AMP] * 100)
        env = synth.apply_envelope(samples, synth.SAMPLE_RATE, attack=0.0, decay=0.0, sustain=0.5, release=0.0)
        # env[10] should be around 50% of MAX_AMP
        self.assertLessEqual(abs(env[10] - synth.MAX_AMP * 0.5), 2)

    def test_clamp(self):
        # input is MAX_AMP, sustain is 2.0 (should be clamped to 1.0)
        samples = array.array('h', [synth.MAX_AMP] * 10)
        env = synth.apply_envelope(samples, synth.SAMPLE_RATE, attack=0.0, decay=0.0, sustain=2.0)
        for s in env:
            self.assertLessEqual(abs(s), synth.MAX_AMP)

class TestMixAndRepeat(unittest.TestCase):
    def test_mix_clamps(self):
        a = array.array('h', [synth.MAX_AMP] * 5)
        b = array.array('h', [synth.MAX_AMP] * 5)
        mixed = synth.mix_samples(a, b)
        for s in mixed:
            # 2*MAX_AMP would clamp to MAX_AMP
            self.assertEqual(s, synth.MAX_AMP)

    def test_mix_length(self):
        a = array.array('h', [0] * 10)
        b = array.array('h', [0] * 5)
        mixed = synth.mix_samples(a, b)
        self.assertEqual(len(mixed), 5)

    def test_repeat_length(self):
        samples = array.array('h', [1, 2, 3])
        repeated = synth.repeat_sample(samples, 4)
        self.assertEqual(len(repeated), 12)

class TestWavExport(unittest.TestCase):
    def test_riff_magic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = os.path.join(tmpdir, "test.wav")
            synth.write_wav(array.array('h', [0]*100), wav_path)
            with open(wav_path, 'rb') as f:
                self.assertEqual(f.read(4), b'RIFF')

    def test_nchannels(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = os.path.join(tmpdir, "test.wav")
            synth.write_wav(array.array('h', [0]*100), wav_path)
            self.assertEqual(synth.read_wav_info(wav_path)['nchannels'], 1)

    def test_sampwidth(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = os.path.join(tmpdir, "test.wav")
            synth.write_wav(array.array('h', [0]*100), wav_path)
            self.assertEqual(synth.read_wav_info(wav_path)['sampwidth'], 2)

    def test_framerate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = os.path.join(tmpdir, "test.wav")
            synth.write_wav(array.array('h', [0]*100), wav_path)
            self.assertEqual(synth.read_wav_info(wav_path)['framerate'], 44100)

    def test_comptype(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = os.path.join(tmpdir, "test.wav")
            synth.write_wav(array.array('h', [0]*100), wav_path)
            self.assertEqual(synth.read_wav_info(wav_path)['comptype'], 'NONE')

    def test_nframes(self):
        samples = array.array('h', [0]*100)
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = os.path.join(tmpdir, "test.wav")
            synth.write_wav(samples, wav_path)
            self.assertEqual(synth.read_wav_info(wav_path)['nframes'], 100)

    def test_file_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = os.path.join(tmpdir, "test.wav")
            synth.write_wav(array.array('h', [0]*100), wav_path)
            self.assertTrue(os.path.exists(wav_path))

class TestPresets(unittest.TestCase):
    def test_laser_shot_typecode(self):
        self.assertEqual(synth.make_laser_shot().typecode, 'h')

    def test_laser_shot_nonempty(self):
        self.assertGreater(len(synth.make_laser_shot()), 0)

    def test_jump_typecode(self):
        self.assertEqual(synth.make_jump().typecode, 'h')

    def test_coin_pickup_length(self):
        samples = synth.make_coin_pickup()
        # Coin pickup is sum of two segments, ensure it generated something
        self.assertGreater(len(samples), 0)

    def test_powerup_nonempty(self):
        self.assertGreater(len(synth.make_powerup()), 0)

    def test_explosion_deterministic(self):
        a = synth.make_explosion().tobytes()
        b = synth.make_explosion().tobytes()
        self.assertEqual(a, b)

    def test_hit_range(self):
        samples = synth.make_hit()
        for s in samples:
            self.assertGreaterEqual(s, -synth.MAX_AMP)
            self.assertLessEqual(s, synth.MAX_AMP)

    def test_presets_dict_keys(self):
        self.assertEqual(len(synth.PRESETS), 6)
        expected = {'laser-shot', 'jump', 'coin-pickup', 'powerup', 'explosion', 'hit'}
        self.assertEqual(set(synth.PRESETS.keys()), expected)

    def test_all_presets_run(self):
        for name, func in synth.PRESETS.items():
            samples = func()
            self.assertEqual(samples.typecode, 'h')
            self.assertGreater(len(samples), 0)

class TestCLI(unittest.TestCase):
    def test_list_output(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            synth.main(['list'])
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 6)

    def test_generate_creates_wav(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'out.wav')
            synth.main(['generate', 'laser-shot', '--output', out])
            self.assertTrue(os.path.exists(out))

    def test_generate_with_params_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            params = os.path.join(tmpdir, 'params.json')
            with open(params, 'w') as f:
                json.dump({'sample_rate': 22050}, f)
            out = os.path.join(tmpdir, 'out.wav')
            synth.main(['generate', 'jump', '--params', params, '--output', out])
            self.assertTrue(os.path.exists(out))

    def test_help_exits_zero(self):
        with self.assertRaises(SystemExit) as cm:
            with redirect_stdout(io.StringIO()):
                synth.main(['--help'])
        self.assertEqual(cm.exception.code, 0)

    def test_unknown_preset_exits_nonzero(self):
        with self.assertRaises(SystemExit) as cm:
            with redirect_stderr(io.StringIO()):
                synth.main(['generate', 'invalid'])
        # argparse default error exit code is 2
        self.assertEqual(cm.exception.code, 2)

    def test_generate_default_filename(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                synth.main(['generate', 'hit'])
                self.assertTrue(os.path.exists('hit.wav'))
            finally:
                os.chdir(cwd)

if __name__ == '__main__':
    unittest.main()
