"""FFmpeg assembly — real local muxing and subtitle burn-in (spec §4 rendering).

Requires the ffmpeg binary on PATH. On Windows: `winget install Gyan.FFmpeg`.
"""
from __future__ import annotations

import asyncio

from ...config import settings
from ...ffmpeg_util import ffmpeg_exe
from ..base import (Availability, AssemblyProvider, Capability, ProviderInfo)


class FFmpegAssemblyProvider(AssemblyProvider):
    info = ProviderInfo(
        name="ffmpeg", capability=Capability.ASSEMBLY, kind="local",
        free=True, requires_gpu=False,
    )

    def availability(self) -> Availability:
        if ffmpeg_exe() is None:
            return Availability(
                False, reason="ffmpeg not found",
                install_hint="python scripts/install_ffmpeg.py",
            )
        return Availability(True)

    async def _run(self, args: list[str]) -> None:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg_exe(), "-y", *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _out, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {err.decode(errors='ignore')[-800:]}")

    def _abs(self, rel: str) -> str:
        return str((settings.assets_dir() / rel).resolve())

    async def mux(self, *, video_path: str | None, audio_paths: list[str],
                  out_name: str, fps: int = 24) -> str:
        out_abs = self._abs(out_name)
        args: list[str] = []
        if video_path:
            args += ["-i", self._abs(video_path)]
        for a in audio_paths:
            args += ["-i", self._abs(a)]
        if video_path and audio_paths:
            args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
                     "-c:a", "aac", "-shortest"]
        elif audio_paths:
            args += ["-c:a", "aac"]
        args += [out_abs]
        await self._run(args)
        return out_name

    async def burn_subtitles(self, *, video_path: str, srt_path: str,
                             out_name: str) -> str:
        out_abs = self._abs(out_name)
        sub = self._abs(srt_path).replace("\\", "/").replace(":", "\\:")
        await self._run([
            "-i", self._abs(video_path),
            "-vf", f"subtitles='{sub}'",
            "-c:a", "copy", out_abs,
        ])
        return out_name
