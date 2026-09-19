# RetroArcadeSynth

A procedural 8-bit sound effects synthesizer and generator written in pure
Python (standard library only). Produces classic retro arcade sound effects —
laser shots, jumps, coin pickups, power-ups, explosions, and hits — using
algorithmic waveform synthesis (square, triangle, sawtooth, noise, frequency
slides, and pitch envelopes) and exports valid uncompressed PCM WAV audio files.

## Features

- **Waveform synthesis**: square, triangle, sawtooth, and white noise.
- **Frequency slides**: smooth pitch ramps between two frequencies.
- **ADSR envelopes**: attack, decay, sustain, release amplitude shaping.
- **Presets**: six classic arcade sound effects ready to use.
- **WAV export**: standard 16-bit mono PCM WAV files readable by any tool.
- **Zero dependencies**: runs on Python 3.9+ with no external packages.

## Installation

No installation required. Just Python 3.9 or later.

```bash
python3 --version
```

## Usage

### Command-line interface

The `synth.py` script provides two subcommands: `list` and `generate`.

```bash
# List available preset names
python3 examples/retro-arcade-synth/synth.py list

# Generate a preset sound effect as a WAV file
python3 examples/retro-arcade-synth/synth.py generate laser-shot
python3 examples/retro-arcade-synth/synth.py generate coin-pickup --output coin.wav
```

#### Generate options

- `preset` (required): one of `laser-shot`, `jump`, `coin-pickup`, `powerup`,
  `explosion`, `hit`.
- `--output`, `-o`: output WAV file path. Defaults to `<preset>.wav`.
- `--params`, `-p`: JSON file with synthesis parameter overrides (e.g.
  `sample_rate`).
- `--sample-rate`: sample rate in Hz. Defaults to 44100.

```bash
# Override the sample rate via JSON
echo '{"sample_rate": 22050}' > params.json
python3 examples/retro-arcade-synth/synth.py generate jump --params params.json --output jump-22k.wav
```

### Library use

```python
from examples.retro_arcade_synth import synth

# Generate a laser shot
samples = synth.make_laser_shot()
synth.write_wav(samples, 'laser.wav')

# Custom synthesis with a frequency slide and envelope
samples = synth.generate_samples(
    duration_s=0.2,
    freq_start=880,
    freq_end=110,
    waveform='sawtooth',
)
samples = synth.apply_envelope(samples, synth.SAMPLE_RATE, attack=0.005, decay=0.12)
synth.write_wav(samples, 'custom.wav')
```

## Presets

| Preset        | Waveform     | Description                                  |
| ------------- | ------------ | -------------------------------------------- |
| `laser-shot`  | sawtooth     | Descending pitch sweep, quick decay.         |
| `jump`        | square       | Ascending pitch sweep, short sustain.        |
| `coin-pickup` | triangle     | Two stacked triangle tones (1200 + 1600 Hz). |
| `powerup`     | square       | Rising arpeggio-like sweep with sustain.     |
| `explosion`   | noise        | Seeded white noise with fast decay.          |
| `hit`         | sawtooth     | Low, punchy impact with quick decay.         |

All presets are deterministic: `make_explosion()` uses a fixed seed so it
produces the same samples every time.

## Waveform synthesis

The core generator (`generate_samples`) produces a signed 16-bit PCM buffer by
walking a phase accumulator through one of three periodic waveforms:

- **Square**: hard-clamped to `±MAX_AMP` with a 50 % duty cycle.
- **Triangle**: linear ramp up and down, producing a softer tone.
- **Sawtooth**: linear ramp up then instant drop, classic arcade texture.

When `freq_end` is provided, the frequency ramps linearly from `freq_start` to
`freq_end` across the duration, creating pitch slides. White noise is produced
by seeding `random.Random(42)` and filling the buffer with random 16-bit
values, which makes explosions reproducible.

## Envelopes

`apply_envelope` applies a linear ADSR (attack, decay, sustain, release)
amplitude envelope to a sample buffer. Each segment is computed as a fraction
of the total sample count, and the result is clamped to the 16-bit range.

## WAV output

`write_wav` writes standard uncompressed PCM WAV files using Python's `wave`
module: mono, 16-bit samples, `NONE` compression. Files are readable by any
audio player, editor, or the standard library `wave` module.

`read_wav_info` reads back the RIFF header fields (`nchannels`, `sampwidth`,
`framerate`, `nframes`, `comptype`) without decoding the audio data.

## Testing

Run the unit tests with:

```bash
python3 -m unittest examples/retro-arcade-synth/test_synth.py -v
```

The test suite verifies:

- Module import and `__version__` attribute.
- `generate_samples` type, length, and clamping.
- Envelope first-sample behavior.
- Sample mixing and clamping.
- Sample repetition.
- WAV header bytes (`RIFF`), file round-trip, and `read_wav_info`.
- Preset existence, count, valid output arrays, and determinism.
- CLI `list` output, `generate` WAV creation, JSON parameter overrides, and
  invalid preset error handling.

## License

MIT — see [LICENSE](../../LICENSE).