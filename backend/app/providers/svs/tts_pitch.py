"""tts_pitch — local CPU Singing Voice Synthesis (spec §B.2) by pitch-warping Piper speech.

The free/CPU SVS baseline: it makes the existing Piper voice follow an auto-composed melody
(see app/singing.py). Not studio quality like neural DiffSinger (which needs a GPU), but it's
real *sung* (pitched) vocals — fully local, free, no torch. Select with PROVIDER_SVS=tts_pitch.
"""
from __future__ import annotations

from ...ffmpeg_util import has_ffmpeg
from ..base import Availability, Capability, Cost, GenResult, ProviderInfo, SVSProvider
from ..registry import get_provider


class TTSPitchSVSProvider(SVSProvider):
    info = ProviderInfo(
        name="tts_pitch", capability=Capability.SVS, kind="local",
        free=True, requires_gpu=False, languages=("en", "fr"),
    )

    def availability(self) -> Availability:
        if not has_ffmpeg():
            return Availability(False, reason="ffmpeg not found (needed for pitch shifting)",
                                install_hint="python scripts/install_ffmpeg.py")
        tts = get_provider(Capability.TTS, required=False)
        if tts is None or not tts.availability().available:
            return Availability(False, reason="needs a TTS voice (piper)",
                                install_hint="python scripts/download_voices.py")
        return Availability(True, reason="local CPU melody-pitched vocals (novelty quality; "
                                         "GPU DiffSinger is the studio-quality upgrade)")

    async def sing(self, lyrics: str, *, melody_midi: bytes | None = None,
                   language: str = "en", voice: str = "", key: str = "C",
                   tempo: int = 100, vibrato: float = 0.3, breathiness: float = 0.2,
                   **kw: object) -> GenResult:
        from ... import singing
        wav, sr = await singing.synthesize_singing(lyrics, language=language, key=key,
                                                   tempo=tempo, vibrato=vibrato)
        return GenResult(data=wav, mime="audio/wav", cost=Cost(),
                         meta={"provider": "tts_pitch", "key": key, "tempo": tempo,
                               "sample_rate": sr, "vibrato": vibrato,
                               "formant_preserved": singing._has_rubberband(),
                               "method": "melody-pitched-tts"})
