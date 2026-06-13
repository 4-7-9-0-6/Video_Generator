"""XTTS-v2 local TTS + voice cloning (spec §B.1) — Coqui TTS.

Clones a voice from a short reference clip (XTTS_SPEAKER_WAV, or a per-call `speaker_wav`)
and speaks EN/FR with far more natural prosody than Piper. Runs **locally and free on CPU**
(slower) and auto-uses a GPU if present. Drop-in: PROVIDER_TTS=xtts_local; Piper stays the
fast default. Enable on CPU with `pip install -r requirements-ml-cpu.txt`.

License note: the XTTS-v2 *model* is under the Coqui Public Model License (NON-COMMERCIAL).
Free to use; do not ship commercial output with it. Code via the maintained `coqui-tts` fork.
"""
from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

from ... import gpu_util
from ...config import settings
from ..base import Availability, Capability, GenResult, ProviderInfo, TTSProvider

_tts = None


class XTTSLocalProvider(TTSProvider):
    info = ProviderInfo(
        name="xtts_local", capability=Capability.TTS, kind="local",
        free=True, requires_gpu=False, languages=("en", "fr"),   # CPU-capable (slow)
    )

    def availability(self) -> Availability:
        av = gpu_util.require_torch("TTS")
        if not av.available:
            return av
        if not settings.xtts_speaker_wav:
            return Availability(
                True, reason=av.reason + " — no XTTS_SPEAKER_WAV set; using a built-in speaker",
            )
        if not Path(settings.xtts_speaker_wav).exists():
            return Availability(False, reason=f"XTTS_SPEAKER_WAV not found: {settings.xtts_speaker_wav}",
                                install_hint="point XTTS_SPEAKER_WAV at a 6-30s reference .wav")
        return av

    def _load(self):
        global _tts
        if _tts is None:
            from TTS.api import TTS
            _tts = TTS(settings.xtts_model).to(gpu_util.torch_device())
        return _tts

    async def synthesize(self, text: str, *, language: str = "en", voice: str = "",
                         speed: float = 1.0, pitch: float = 0.0,
                         emotion: str = "neutral", **kw: object) -> GenResult:
        return await asyncio.to_thread(self._run, text, language, speed, kw)

    def _run(self, text: str, language: str, speed: float, kw: dict) -> GenResult:
        tts = self._load()
        lang = "fr" if language.startswith("fr") else "en"
        speaker_wav = kw.get("speaker_wav") or settings.xtts_speaker_wav or None
        t0 = time.monotonic()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "speech.wav"
            extra: dict = {"speaker_wav": speaker_wav} if speaker_wav else {"speaker": "Ana Florence"}
            tts.tts_to_file(text=text, language=lang, speed=speed,
                            file_path=str(out), **extra)
            data = out.read_bytes()
        elapsed = time.monotonic() - t0
        return GenResult(
            data=data, mime="audio/wav", cost=gpu_util.gpu_cost(elapsed),
            meta={"provider": "xtts_local", "language": lang,
                  "cloned": bool(speaker_wav), "elapsed_s": round(elapsed, 1)},
        )
