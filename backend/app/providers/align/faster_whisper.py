"""faster-whisper forced alignment — real local CPU ASR with word-level timestamps.

Powers subtitles (spec §C.5) and audio→mouth timing. CPU int8 with the 'base' model
is the sweet spot on a machine like this. EN + FR supported.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from ...config import settings
from ..base import AlignProvider, Availability, Capability, ProviderInfo, WordStamp

_model_cache: dict[str, object] = {}


class FasterWhisperAlignProvider(AlignProvider):
    info = ProviderInfo(
        name="faster_whisper", capability=Capability.ALIGN, kind="local",
        free=True, requires_gpu=False, languages=("en", "fr"),
    )

    def availability(self) -> Availability:
        try:
            import faster_whisper  # noqa: F401
            return Availability(True)
        except ImportError as e:
            return Availability(
                False, reason=str(e),
                install_hint="pip install -r requirements-ml.txt (faster-whisper)",
            )

    def _get_model(self):
        name = settings.whisper_model
        if name not in _model_cache:
            from faster_whisper import WhisperModel
            _model_cache[name] = WhisperModel(name, device="cpu", compute_type="int8")
        return _model_cache[name]

    async def align(self, audio: bytes, *, text: str = "",
                    language: str = "en") -> list[WordStamp]:
        return await asyncio.to_thread(self._align_blocking, audio, language)

    def _align_blocking(self, audio: bytes, language: str) -> list[WordStamp]:
        model = self._get_model()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audio.wav"
            path.write_bytes(audio)
            segments, _info = model.transcribe(
                str(path), language=language[:2], word_timestamps=True,
            )
            stamps: list[WordStamp] = []
            for seg in segments:
                for w in (seg.words or []):
                    stamps.append(WordStamp(word=w.word.strip(), start=w.start, end=w.end))
        return stamps
