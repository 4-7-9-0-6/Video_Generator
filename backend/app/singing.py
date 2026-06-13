"""Local CPU 'singing' — pitch-warp Piper speech to follow an auto-composed melody.

This is NOT neural SVS (that's GPU/DiffSinger). It's a pragmatic, fully local + free + CPU
pipeline that makes the voice actually carry a tune:

  Piper speaks the line -> faster-whisper word timings -> for each word, detect its pitch
  (numpy autocorrelation) and shift it to a melody note (FFmpeg asetrate+atempo) -> concat.

The melody is transposed to sit near the voice's own median pitch so the shifts stay small
(less "chipmunk"). Honest quality: a recognizable robotic sing-song — fun for nursery-style
content, not a studio vocal. No torch; uses Piper + Whisper + FFmpeg (already installed).
"""
from __future__ import annotations

import asyncio
import io
import math
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .ffmpeg_util import ffmpeg_exe, has_ffmpeg
from .providers.base import Capability
from .providers.music.symbolic import _CONTOUR, _MAJOR, _MINOR, _root_midi
from .providers.registry import get_provider


def _read_wav(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}[sw]
    arr = np.frombuffer(raw, dtype=dtype).astype("float64")
    if ch > 1:
        arr = arr.reshape(-1, ch).mean(axis=1)
    return arr / float(2 ** (8 * sw - 1)), sr


def _write_wav(samples: np.ndarray, sr: int) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _f0(seg: np.ndarray, sr: int, fmin: float = 70.0, fmax: float = 400.0) -> float | None:
    """Crude autocorrelation pitch (Hz); None if unvoiced/too quiet."""
    if len(seg) < int(sr / fmin):
        return None
    x = seg - seg.mean()
    if math.sqrt(float(np.mean(x * x))) < 0.01:
        return None
    corr = np.correlate(x, x, "full")[len(x) - 1:]
    lag_min, lag_max = int(sr / fmax), int(sr / fmin)
    window = corr[lag_min:lag_max]
    if len(window) == 0 or window.max() <= 0:
        return None
    lag = lag_min + int(np.argmax(window))
    return sr / lag if lag else None


def _hz_to_midi(hz: float) -> float:
    return 69.0 + 12.0 * math.log2(hz / 440.0)


def _midi_to_hz(m: float) -> float:
    return 440.0 * (2.0 ** ((m - 69.0) / 12.0))


def _sing_notes(n: int, key: str, center_midi: float, minor: bool) -> list[int]:
    scale = _MINOR if minor else _MAJOR
    root = _root_midi(key)
    while root - center_midi > 6:    # transpose to the octave nearest the voice
        root -= 12
    while center_midi - root > 6:
        root += 12
    notes = []
    for i in range(n):
        deg = _CONTOUR[i % len(_CONTOUR)]
        octv = -12 if deg < 0 else 0
        notes.append(int(root + scale[abs(deg) % 7] + octv))
    return notes


_VIB_RATE = 5.2          # Hz — natural singing vibrato
_rubberband: bool | None = None


def _has_rubberband() -> bool:
    """rubberband does FORMANT-PRESERVING pitch shift — the fix for the chipmunk/robotic
    timbre. Fall back to asetrate+atempo (formants shift) when the build lacks it."""
    global _rubberband
    if _rubberband is None:
        try:
            out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-filters"],
                                 capture_output=True, text=True)
            _rubberband = "rubberband" in (out.stdout or "")
        except Exception:  # noqa: BLE001
            _rubberband = False
    return _rubberband


def _ffmpeg_af(seg: np.ndarray, sr: int, af: str) -> np.ndarray:
    with tempfile.TemporaryDirectory() as tmp:
        ip, op = Path(tmp) / "i.wav", Path(tmp) / "o.wav"
        ip.write_bytes(_write_wav(seg, sr))
        proc = subprocess.run([ffmpeg_exe(), "-y", "-i", str(ip), "-af", af, str(op)],
                              capture_output=True)
        if proc.returncode != 0 or not op.exists():
            return seg
        out, _ = _read_wav(op.read_bytes())
        return out


def _shift(seg: np.ndarray, sr: int, ratio: float) -> np.ndarray:
    """Pitch-shift a segment by `ratio` (duration preserved). Formant-preserving via
    rubberband when available, so the voice keeps its timbre instead of going chipmunk."""
    ratio = max(0.5, min(2.0, ratio))
    if abs(ratio - 1.0) < 0.03:
        return seg
    if _has_rubberband():
        af = f"rubberband=pitch={ratio:.5f}:formant=preserved:pitchq=quality"
    else:
        af = f"asetrate={int(sr * ratio)},atempo={1.0 / ratio:.5f},aresample={sr}"
    return _ffmpeg_af(seg, sr, af)


def _edge_fade(seg: np.ndarray, sr: int, ms: float = 3.0) -> np.ndarray:
    """Raised-cosine micro-fade at the edges so word-to-word joins don't click."""
    n = int(sr * ms / 1000)
    if n <= 0 or len(seg) < 2 * n:
        return seg
    ramp = 0.5 * (1 - np.cos(np.linspace(0.0, np.pi, n)))
    seg = seg.copy()
    seg[:n] *= ramp
    seg[-n:] *= ramp[::-1]
    return seg


def _vibrato(audio: np.ndarray, sr: int, depth: float) -> np.ndarray:
    """One continuous vibrato pass over the whole sung line (musical, not seasick)."""
    d = max(0.0, min(1.0, depth))
    if d <= 0:
        return audio
    return _ffmpeg_af(audio, sr, f"vibrato=f={_VIB_RATE}:d={d:.3f}")


def _chunks(stamps: list[tuple[str, float, float]], total: int, sr: int) -> list[tuple[int, int]]:
    """Contiguous sample ranges (one per word), split at midpoints so no audio is dropped."""
    bounds = [0]
    for i in range(1, len(stamps)):
        mid = (stamps[i - 1][2] + stamps[i][1]) / 2.0
        bounds.append(min(total, max(bounds[-1], int(mid * sr))))
    bounds.append(total)
    return [(bounds[i], bounds[i + 1]) for i in range(len(stamps))]


async def synthesize_singing(lyrics: str, *, language: str = "en", key: str = "C",
                             tempo: int = 100, vibrato: float = 0.3,
                             minor: bool | None = None) -> tuple[bytes, int]:
    if not has_ffmpeg():
        raise RuntimeError("singing needs ffmpeg — run: python scripts/install_ffmpeg.py")
    tts = get_provider(Capability.TTS)
    align = get_provider(Capability.ALIGN, required=False)

    spoken = await tts.synthesize(lyrics, language=language)
    audio, sr = _read_wav(spoken.data)

    words = lyrics.split()
    stamps: list[tuple[str, float, float]] = []
    if align is not None:
        try:
            stamps = [(w.word, w.start, w.end) for w in
                      await align.align(spoken.data, text=lyrics, language=language)]
        except Exception:  # noqa: BLE001 — alignment is best-effort
            stamps = []
    if len(stamps) != len(words):                 # fallback: even split across words
        dur = len(audio) / sr
        step = dur / max(1, len(words))
        stamps = [(w, i * step, (i + 1) * step) for i, w in enumerate(words)]
    if not stamps:
        return spoken.data, sr

    ranges = _chunks(stamps, len(audio), sr)
    f0s = [_f0(audio[a:b], sr) for a, b in ranges]
    voiced = [f for f in f0s if f]
    center = _hz_to_midi(float(np.median(voiced))) if voiced else 60.0
    if minor is None:
        minor = "minor" in key.lower()
    notes = _sing_notes(len(ranges), key, center, minor)

    pieces: list[np.ndarray] = []
    for (a, b), src, note in zip(ranges, f0s, notes):
        seg = audio[a:b]
        if src and len(seg) > 64:
            seg = await asyncio.to_thread(_shift, seg, sr, _midi_to_hz(note) / src)
            seg = _edge_fade(seg, sr)            # de-click the word join
        pieces.append(seg)
    sung = np.concatenate(pieces)
    # final continuous vibrato pass for a more natural, less robotic vocal
    sung = await asyncio.to_thread(_vibrato, sung, sr, vibrato * 0.5)
    return _write_wav(sung, sr), sr
