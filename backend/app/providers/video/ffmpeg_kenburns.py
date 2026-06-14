"""FFmpeg Ken Burns video provider — the FREE, CPU-only animation path (spec §C.2/§C.6).

Animates a still keyframe with pan/zoom motion presets (no GPU). Not as alive as a real
image-to-video model, but it turns keyframes into actual moving clips for episode assembly
at zero cost. Set PROVIDER_VIDEO=ffmpeg_kenburns once FFmpeg is on PATH.
"""
from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path

from ..base import Availability, Capability, Cost, GenResult, ProviderInfo, VideoProvider
from ...ffmpeg_util import ffmpeg_exe, kenburns_vf
from ...scene import MOTION_PRESETS


class FFmpegKenBurnsVideoProvider(VideoProvider):
    info = ProviderInfo(
        name="ffmpeg_kenburns", capability=Capability.VIDEO, kind="local",
        free=True, requires_gpu=False,
    )

    def availability(self) -> Availability:
        if ffmpeg_exe() is None:
            return Availability(False, reason="ffmpeg not found",
                                install_hint="python scripts/install_ffmpeg.py")
        return Availability(True)

    async def animate(self, image: bytes, *, motion: str = "static",
                      duration_s: float = 4.0, fps: int = 24,
                      prompt: str = "", **kw: object) -> GenResult:
        kind = MOTION_PRESETS.get(motion, MOTION_PRESETS["static"])["kind"]
        w = int(kw.get("width", 1024))
        h = int(kw.get("height", 576))
        frames = max(1, round(duration_s * fps))

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "frame.png"
            out = Path(tmp) / "clip.mp4"
            src.write_bytes(image)
            args = [
                ffmpeg_exe(), "-y", "-loop", "1", "-i", str(src),
                "-vf", kenburns_vf(kind, w, h, fps, frames),
                "-t", f"{duration_s:.3f}", "-r", str(fps),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out),
            ]
            proc = await asyncio.to_thread(lambda: subprocess.run(args, capture_output=True))
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or b"").decode(errors="ignore")
                raise RuntimeError(f"ffmpeg ken-burns failed: {err[-600:]}")
            data = out.read_bytes()
        return GenResult(data=data, mime="video/mp4", cost=Cost(),
                         meta={"provider": "ffmpeg_kenburns", "motion": motion, "kind": kind})
