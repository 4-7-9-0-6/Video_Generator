"""Piper TTS — real local CPU text-to-speech, EN + FR voices (piper-tts 1.4.x API).

Outputs 16-bit PCM WAV. Voice models (.onnx + .onnx.json) live in PIPER_MODELS_DIR
(get them with scripts/download_voices.py). espeak-ng phonemizer data ships inside the
piper-tts wheel, so no extra system install is needed. Degrades gracefully: if piper or
the voice files are missing, availability() says exactly what to do.
"""
from __future__ import annotations

import asyncio
import io
import wave

from ...config import settings
from ..base import Availability, Capability, Cost, GenResult, ProviderInfo, TTSProvider

_voice_cache: dict[str, object] = {}


class PiperTTSProvider(TTSProvider):
    info = ProviderInfo(
        name="piper", capability=Capability.TTS, kind="local",
        free=True, requires_gpu=False, languages=("en", "fr"),
    )

    def _voice_name(self, language: str) -> str:
        return settings.piper_voice_fr if language.startswith("fr") else settings.piper_voice_en

    def _model_path(self, language: str):
        return settings.piper_models_dir / f"{self._voice_name(language)}.onnx"

    def availability(self) -> Availability:
        try:
            import piper  # noqa: F401
        except ImportError as e:
            return Availability(False, reason=str(e),
                                install_hint="pip install -r requirements-ml.txt (piper-tts)")
        missing = [lang for lang in ("en", "fr") if not self._model_path(lang).exists()]
        if missing:
            return Availability(
                False,
                reason=f"voice model(s) missing for: {', '.join(missing)}",
                install_hint="python scripts/download_voices.py",
            )
        return Availability(True)

    def _get_voice(self, language: str):
        path = str(self._model_path(language))
        if path not in _voice_cache:
            from piper import PiperVoice
            _voice_cache[path] = PiperVoice.load(path)
        return _voice_cache[path]

    async def synthesize(self, text: str, *, language: str = "en", voice: str = "",
                         speed: float = 1.0, pitch: float = 0.0,
                         emotion: str = "neutral", **kw: object) -> GenResult:
        return await asyncio.to_thread(self._synth_blocking, text, language, speed)

    def _synth_blocking(self, text: str, language: str, speed: float) -> GenResult:
        from piper import SynthesisConfig
        voice = self._get_voice(language)
        # length_scale > 1 slows speech; invert so the `speed` arg is intuitive
        syn = SynthesisConfig(length_scale=(1.0 / speed) if speed else 1.0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file, syn_config=syn)
        return GenResult(data=buf.getvalue(), mime="audio/wav", cost=Cost(),
                         meta={"provider": "piper", "language": language,
                               "voice": self._voice_name(language)})
