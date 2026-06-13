"""SadTalker lip-sync provider (spec §C.3) — drives a still character into a talking head
that mouths the audio. GPU, the realism upgrade over the CPU mouth-flap.

SadTalker isn't a pip package — it's a repo (cloned + checkpoints downloaded). This provider
shells out to its `inference.py` (set SADTALKER_DIR), feeding a source image + the audio and
reading back the rendered talking-head MP4. Needs an NVIDIA GPU (fits a free T4).

Interface note: `apply(image, audio)` here takes the first arg as the SOURCE IMAGE (a shot
keyframe / character close-up), not a pre-made video — SadTalker animates the face from the
still. Built against SadTalker's documented CLI; first GPU run may need a flag tweak.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ... import gpu_util
from ...config import settings
from ..base import Availability, Capability, Cost, GenResult, LipSyncProvider, ProviderInfo


class SadTalkerLipSyncProvider(LipSyncProvider):
    info = ProviderInfo(
        name="sadtalker_local", capability=Capability.LIPSYNC, kind="local",
        free=True, requires_gpu=True,
    )

    def availability(self) -> Availability:
        av = gpu_util.require_gpu("torch")
        if not av.available:
            return av
        d = settings.sadtalker_dir
        if not d or not (Path(d) / "inference.py").exists():
            return Availability(
                False, reason="SadTalker repo not found",
                install_hint="git clone https://github.com/OpenTalker/SadTalker + download its "
                             "checkpoints, then set SADTALKER_DIR (see docs/FREE_GPU.md).",
            )
        return Availability(True, reason=f"SadTalker GPU lip-sync ({d})")

    def estimate_cost(self, **kw: object):
        return gpu_util.gpu_cost(float(kw.get("seconds", 30.0)))

    async def apply(self, video: bytes, audio: bytes, **kw: object) -> GenResult:
        # `video` is treated as the source image (keyframe) for SadTalker
        return await asyncio.to_thread(self._run, video, audio, kw)

    def _run(self, source_image: bytes, audio: bytes, kw: dict) -> GenResult:
        d = Path(settings.sadtalker_dir)
        with tempfile.TemporaryDirectory() as tmp:
            tmpd = Path(tmp)
            img = tmpd / "src.png"
            wav = tmpd / "audio.wav"
            res = tmpd / "out"
            img.write_bytes(source_image)
            wav.write_bytes(audio)
            res.mkdir(exist_ok=True)
            cmd = [
                sys.executable, str(d / "inference.py"),
                "--source_image", str(img),
                "--driven_audio", str(wav),
                "--result_dir", str(res),
                "--preprocess", str(kw.get("preprocess", "full")),
                "--still",                       # less head jitter -> good for cartoon faces
            ]
            if kw.get("enhancer", True):
                cmd += ["--enhancer", "gfpgan"]
            t0 = time.monotonic()
            proc = subprocess.run(cmd, cwd=str(d), capture_output=True, text=True)
            elapsed = time.monotonic() - t0
            mp4 = next((p for p in res.rglob("*.mp4")), None)
            if proc.returncode != 0 or mp4 is None:
                tail = (proc.stderr or proc.stdout or "")[-700:]
                raise RuntimeError(f"SadTalker failed (exit {proc.returncode}):\n{tail}")
            data = mp4.read_bytes()
        return GenResult(data=data, mime="video/mp4", cost=gpu_util.gpu_cost(elapsed),
                         meta={"provider": "sadtalker_local", "elapsed_s": round(elapsed, 1)})
