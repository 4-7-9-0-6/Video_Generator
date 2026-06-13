"""Local CPU lip-sync — envelope + mouth placement (pure), and the GPU provider registration."""
from __future__ import annotations

import io
import wave

import numpy as np
from PIL import Image

from app import lipsync
from app.providers import registry
from app.providers.base import Capability


def _wav(samples: np.ndarray, sr: int = 22050) -> bytes:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def test_envelope_length_and_silence():
    sr = 22050
    silent = _wav(np.zeros(sr))
    env = lipsync.voice_envelope(silent, 24)
    assert len(env) == 24 and max(env) == 0.0


def test_envelope_tracks_loudness():
    sr = 22050
    # first half loud, second half silent -> early frames open, late frames closed
    sig = np.concatenate([0.8 * np.sin(2 * np.pi * 200 * np.arange(sr) / sr), np.zeros(sr)])
    env = lipsync.voice_envelope(_wav(sig), 20)
    assert np.mean(env[:8]) > 0.3 and np.mean(env[-5:]) < 0.1


def test_mouth_box_within_image():
    img = Image.new("RGB", (800, 600), (200, 180, 160))
    cx, cy, mw, mh = lipsync.mouth_box(img)
    assert 0 < cx < 800 and 0 < cy < 600 and mw > 0 and mh > 0


def test_sadtalker_registered_and_gpu_only():
    assert "sadtalker_local" in registry._FACTORIES[Capability.LIPSYNC.value]
    p = registry._FACTORIES[Capability.LIPSYNC.value]["sadtalker_local"]()
    assert p.info.requires_gpu is True
    assert p.availability().available is False        # no GPU here -> graceful


def test_lipsync_in_probe():
    rows = registry.probe_all()
    assert any(r["capability"] == "lipsync" and r["provider"] == "sadtalker_local" for r in rows)
