"""Retro Arcade Synthesizer

This module provides a placeholder implementation for the RetroArcadeSynth example.
It defines a version string and can be extended with actual synthesis functionality.
"""

__version__ = "0.1.0"

import array, math, random
import wave, io, builtins

SAMPLE_RATE = 44100
MAX_AMP = 32767

def generate_samples(duration_s, freq_start, freq_end=None, waveform='square', sample_rate=SAMPLE_RATE):
    """Generate a waveform sample array.

    Args:
        duration_s (float): Duration in seconds.
        freq_start (float): Starting frequency in Hz.
        freq_end (float, optional): Ending frequency for a slide. If None, frequency is constant.
        waveform (str): 'square', 'triangle', or 'sawtooth'. Other values produce silence.
        sample_rate (int): Samples per second.
    Returns:
        array.array: Signed 16‑bit PCM samples.
    """
    n = round(duration_s * sample_rate)
    out = array.array('h')
    phase = 0.0
    for i in range(n):
        if freq_end is not None:
            freq = freq_start + (freq_end - freq_start) * i / max(n - 1, 1)
        else:
            freq = freq_start
        period = sample_rate / freq if freq != 0 else 1
        if waveform == 'square':
            val = MAX_AMP if (phase % period) < (period / 2) else -MAX_AMP
        elif waveform == 'triangle':
            p = (phase % period) / period
            val = int(MAX_AMP * (4 * p - 1) if p < 0.5 else MAX_AMP * (3 - 4 * p))
        elif waveform == 'sawtooth':
            val = int(MAX_AMP * (2 * (phase % period) / period - 1))
        else:
            val = 0
        out.append(max(-MAX_AMP, min(MAX_AMP, val)))
        phase += 1
    return out

def apply_envelope(samples, sample_rate, attack=0.01, decay=0.05, sustain=0.8, release=0.1):
    """Apply a simple ADSR envelope to a sample array.

    The envelope is linear and clamped to the sample amplitude limits.
    """
    n = len(samples)
    atk = round(min(attack, 1.0) * n)
    dcy = round(min(decay, max(0.0, 1.0 - attack)) * n)
    rel = round(min(release, max(0.0, 1.0 - attack - decay)) * n)
    out = array.array('h')
    for i, s in enumerate(samples):
        if atk and i < atk:
            gain = i / atk
        elif dcy and i < atk + dcy:
            gain = 1.0 - (1.0 - sustain) * (i - atk) / dcy
        elif rel and i >= n - rel:
            gain = sustain * (n - i) / rel
        else:
            gain = sustain
        out.append(max(-MAX_AMP, min(MAX_AMP, int(s * gain))))
    return out

def mix_samples(*arrays):
    """Mix multiple sample arrays together, clamping to 16‑bit range."""
    if not arrays:
        return array.array('h')
    out = array.array('h')
    length = min(len(a) for a in arrays)
    for i in range(length):
        mixed = sum(a[i] for a in arrays)
        out.append(max(-MAX_AMP, min(MAX_AMP, mixed)))
    return out

def repeat_sample(samples, times):
    """Repeat a sample array ``times`` times."""
    out = array.array('h')
    for _ in range(times):
        out.extend(samples)
    return out
def write_wav(samples, path_or_fileobj, sample_rate=SAMPLE_RATE, channels=1, sampwidth=2):
    open_file = isinstance(path_or_fileobj, str)
    f = builtins.open(path_or_fileobj, 'wb') if open_file else path_or_fileobj
    try:
        with wave.open(f, 'w') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(sample_rate)
            wf.writeframes(samples.tobytes())
    finally:
        if open_file:
            f.close()


def read_wav_info(path_or_fileobj):
    open_file = isinstance(path_or_fileobj, str)
    if open_file:
        f = builtins.open(path_or_fileobj, 'rb')
    else:
        path_or_fileobj.seek(0)
        f = path_or_fileobj
    try:
        with wave.open(f, 'r') as wf:
            return dict(nchannels=wf.getnchannels(), sampwidth=wf.getsampwidth(),
                        framerate=wf.getframerate(), nframes=wf.getnframes(),
                        comptype=wf.getcomptype())
    finally:
        if open_file:
            f.close()
def make_laser_shot(sample_rate=SAMPLE_RATE):
    s = generate_samples(0.18, 880, 110, waveform='sawtooth', sample_rate=sample_rate)
    return apply_envelope(s, sample_rate, attack=0.005, decay=0.12, sustain=0.0, release=0.0)

def make_jump(sample_rate=SAMPLE_RATE):
    s = generate_samples(0.25, 200, 600, waveform='square', sample_rate=sample_rate)
    return apply_envelope(s, sample_rate, attack=0.02, decay=0.0, sustain=1.0, release=0.05)

def make_coin_pickup(sample_rate=SAMPLE_RATE):
    a = apply_envelope(generate_samples(0.07, 1200, waveform='triangle', sample_rate=sample_rate), sample_rate, attack=0.01, decay=0.0, sustain=1.0, release=0.03)
    b = apply_envelope(generate_samples(0.07, 1600, waveform='triangle', sample_rate=sample_rate), sample_rate, attack=0.0, decay=0.0, sustain=1.0, release=0.05)
    out = array.array('h', a)
    out.extend(b)
    return out

def make_powerup(sample_rate=SAMPLE_RATE):
    s = generate_samples(0.4, 200, 1600, waveform='square', sample_rate=sample_rate)
    return apply_envelope(s, sample_rate, attack=0.05, decay=0.05, sustain=0.9, release=0.1)

def make_explosion(sample_rate=SAMPLE_RATE):
    rng = random.Random(42)
    n = round(0.6 * sample_rate)
    s = array.array('h', [rng.randint(-MAX_AMP, MAX_AMP) for _ in range(n)])
    return apply_envelope(s, sample_rate, attack=0.005, decay=0.4, sustain=0.0, release=0.0)

def make_hit(sample_rate=SAMPLE_RATE):
    s = generate_samples(0.15, 120, waveform='sawtooth', sample_rate=sample_rate)
    return apply_envelope(s, sample_rate, attack=0.005, decay=0.1, sustain=0.0, release=0.0)

PRESETS = {
    'laser-shot': make_laser_shot,
    'jump': make_jump,
    'coin-pickup': make_coin_pickup,
    'powerup': make_powerup,
    'explosion': make_explosion,
    'hit': make_hit,
}

import argparse, json, os, sys

def main(argv=None):
    parser = argparse.ArgumentParser(prog='synth', description='RetroArcadeSynth: 8-bit sound effects generator.')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('list', help='List available preset names.')
    gen = sub.add_parser('generate', help='Generate a preset sound effect as a WAV file.')
    gen.add_argument('preset', choices=list(PRESETS.keys()))
    gen.add_argument('--output', '-o', default=None)
    gen.add_argument('--params', '-p', default=None, help='JSON file with synthesis parameter overrides.')
    gen.add_argument('--sample-rate', type=int, default=SAMPLE_RATE)
    args = parser.parse_args(argv)
    if args.command == 'list':
        for name in PRESETS:
            print(name)
        return 0
    if args.command == 'generate':
        kwargs = {'sample_rate': args.sample_rate}
        if args.params:
            with builtins.open(args.params, 'r') as f:
                kwargs.update(json.load(f))
        samples = PRESETS[args.preset](**kwargs)
        out_path = args.output or f'{args.preset}.wav'
        write_wav(samples, out_path, sample_rate=args.sample_rate)
        print(f'Wrote {out_path}: {len(samples)} frames, {len(samples)/args.sample_rate:.3f}s, {args.sample_rate} Hz')
        return 0
    parser.print_help()
    return 1

if __name__ == '__main__':
    sys.exit(main())