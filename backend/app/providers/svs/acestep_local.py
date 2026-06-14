"""ACE-Step singing provider (spec §B.2) — REAL sung vocals + music from lyrics, GPU.

ACE-Step (Apache-2.0) is a song-generation model: lyrics + a style/tags prompt -> a full
sung track (vocals AND backing music together). Unlike the CPU `tts_pitch` (which pitch-warps
speech and sounds narrated), this actually *sings*. Used at the EPISODE level by
scripts/gpu_render.py — one call makes the whole song; the visuals are timed to it.

Needs an NVIDIA GPU (~8-12 GB, fits a free T4) + ACE-Step installed from GitHub
(`pip install git+https://github.com/ace-step/ACE-Step.git` — there is no `acestep` package
on PyPI). Checkpoints download from Hugging Face on first use. Select with PROVIDER_SVS=acestep_local.

NOTE: built against the documented ACE-Step API but not runtime-tested on a GPU here — the
first GPU run may need a minor signature tweak (the pipeline's kwargs vary across versions).
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from ... import gpu_util
from ...config import settings
from ..base import Availability, Capability, GenResult, ProviderInfo, SVSProvider

_pipe = None


class ACEStepSVSProvider(SVSProvider):
    info = ProviderInfo(
        name="acestep_local", capability=Capability.SVS, kind="local",
        free=True, requires_gpu=True, languages=("en", "fr"),
    )

    def availability(self) -> Availability:
        return gpu_util.require_gpu("acestep")

    def estimate_cost(self, **kw: object):
        return gpu_util.gpu_cost(float(kw.get("seconds", 60.0)))

    def _load(self):
        global _pipe
        if _pipe is None:
            from acestep.pipeline_ace_step import ACEStepPipeline
            _pipe = ACEStepPipeline(checkpoint_dir=settings.acestep_checkpoint_dir or None,
                                    dtype="bfloat16")
        return _pipe

    @staticmethod
    def _tags(key: str, tempo: int, **kw: object) -> str:
        """Build an ACE-Step style prompt from the song's mood/voice hints."""
        mood = str(kw.get("mood", "cheerful"))
        voice = str(kw.get("voice", "")) or "bright child-friendly female vocals"
        genre = str(kw.get("genre", "")) or "children's nursery rhyme, playful pop"
        return f"{genre}, {mood}, {voice}, {key} key, {tempo} BPM, clean mix, catchy melody"

    async def sing(self, lyrics: str, *, melody_midi: bytes | None = None,
                   language: str = "en", voice: str = "", key: str = "C",
                   tempo: int = 100, vibrato: float = 0.3, breathiness: float = 0.2,
                   **kw: object) -> GenResult:
        import asyncio
        return await asyncio.to_thread(self._run, lyrics, key, tempo, voice, kw)

    def _run(self, lyrics: str, key: str, tempo: int, voice: str, kw: dict) -> GenResult:
        pipe = self._load()
        duration = float(kw.get("duration_s", settings.acestep_duration_s))
        tags = self._tags(key, tempo, voice=voice, **kw)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "song.wav"
            t0 = time.monotonic()
            # ACE-Step writes the audio to save_path. Kwargs are kept to the stable core set;
            # adjust here if the installed acestep version differs.
            pipe(
                audio_duration=duration,
                prompt=tags,
                lyrics=lyrics,
                infer_step=int(settings.acestep_steps),
                guidance_scale=float(settings.acestep_guidance),
                save_path=str(out),
                format="wav",
            )
            elapsed = time.monotonic() - t0
            data = out.read_bytes()
        return GenResult(
            data=data, mime="audio/wav", cost=gpu_util.gpu_cost(elapsed),
            meta={"provider": "acestep_local", "tags": tags, "key": key, "tempo": tempo,
                  "duration_s": duration, "elapsed_s": round(elapsed, 1),
                  "full_song": True},          # vocals+music together (replaces the music bed)
        )
