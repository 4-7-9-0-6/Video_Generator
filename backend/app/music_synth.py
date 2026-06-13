"""Render symbolic melody notes to a WAV music bed — CPU-only, numpy additive synthesis.

No soundfont / fluidsynth needed: each note is a few sine harmonics with a soft ADSR
envelope, summed onto a buffer. Produces a gentle, child-friendly instrumental bed that the
Composer ducks under the vocals.
"""
from __future__ import annotations

import io
import wave

import numpy as np


def _midi_to_freq(note: int) -> float:
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def _envelope(n: int, sr: int) -> np.ndarray:
    env = np.ones(n, dtype="float64")
    a = min(int(0.01 * sr), n // 4)          # attack
    r = min(int(0.12 * sr), n // 2)          # release
    if a > 0:
        env[:a] = np.linspace(0.0, 1.0, a)
    if r > 0:
        env[-r:] *= np.linspace(1.0, 0.0, r)
    return env * 0.8                          # sustain a touch below 1.0


def synth_wav(notes: list[tuple[int, float, float]], *, total_s: float,
              sample_rate: int = 44100, gain: float = 0.5) -> bytes:
    """notes = [(midi_note, start_s, dur_s)]. Returns 16-bit mono PCM WAV bytes."""
    total = int(total_s * sample_rate) + sample_rate
    buf = np.zeros(total, dtype="float64")
    harmonics = [(1, 1.0), (2, 0.45), (3, 0.2)]

    for note, start, dur in notes:
        if start >= total_s:
            continue
        f = _midi_to_freq(note)
        n = max(1, int(dur * 0.9 * sample_rate))   # slight gap between notes
        t = np.arange(n) / sample_rate
        wave_ = np.zeros(n, dtype="float64")
        for mult, amp in harmonics:
            wave_ += amp * np.sin(2 * np.pi * f * mult * t)
        seg = wave_ * _envelope(n, sample_rate)
        i0 = int(start * sample_rate)
        buf[i0:i0 + n] += seg

    buf = buf[: int(total_s * sample_rate)]
    peak = float(np.max(np.abs(buf))) or 1.0
    pcm = np.clip(buf / peak * gain, -1.0, 1.0)
    samples = (pcm * 32767).astype("<i2")

    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(samples.tobytes())
    return out.getvalue()
