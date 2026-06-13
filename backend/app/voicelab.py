"""VoiceLab domain helpers (spec Module B)."""
from __future__ import annotations

import io
import wave


def wav_duration(data: bytes) -> float:
    """Duration in seconds of a PCM WAV byte string (0.0 if not parseable)."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            rate = w.getframerate()
            return w.getnframes() / rate if rate else 0.0
    except (wave.Error, EOFError):
        return 0.0
