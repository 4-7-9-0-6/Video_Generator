"""LTX-Video local GPU image-to-video provider — TRUE animation of a keyframe (spec §C.2).

This is the headline GPU upgrade: instead of Ken Burns pan/zoom on a still, LTX-Video
(Lightricks, open weights) animates each keyframe into a real moving clip. Needs an NVIDIA
GPU (~24 GB; less with GPU_OFFLOAD=1). Drop-in: PROVIDER_VIDEO=ltx_local. When unavailable
(no GPU), compose automatically falls back to the free Ken Burns path.
"""
from __future__ import annotations

import asyncio
import io
import tempfile
import time
from pathlib import Path

from ... import gpu_util
from ...config import settings
from ..base import Availability, Capability, GenResult, ProviderInfo, VideoProvider

_pipe = None


class LTXLocalVideoProvider(VideoProvider):
    info = ProviderInfo(
        name="ltx_local", capability=Capability.VIDEO, kind="local",
        free=True, requires_gpu=True,
    )

    def availability(self) -> Availability:
        av = gpu_util.require_gpu("diffusers")
        if not av.available:
            return av
        try:
            import imageio  # noqa: F401  — export_to_video backend
        except ImportError:
            return Availability(False, reason="imageio not installed",
                                install_hint="pip install -r requirements-gpu.txt")
        return av

    def estimate_cost(self, **kw: object):
        return gpu_util.gpu_cost(float(kw.get("seconds", 60.0)))

    def _load(self):
        global _pipe
        if _pipe is None:
            import torch
            from diffusers import LTXImageToVideoPipeline
            _pipe = LTXImageToVideoPipeline.from_pretrained(settings.ltx_model, torch_dtype=torch.bfloat16)
            if settings.gpu_offload:
                _pipe.enable_model_cpu_offload()
            else:
                _pipe.to("cuda")
        return _pipe

    async def animate(self, image: bytes, *, motion: str = "static",
                      duration_s: float = 4.0, fps: int = 24,
                      prompt: str = "", **kw: object) -> GenResult:
        return await asyncio.to_thread(self._run, image, motion, duration_s, fps, prompt, kw)

    def _run(self, image: bytes, motion: str, duration_s: float, fps: int,
             prompt: str, kw: dict) -> GenResult:
        import torch
        from diffusers.utils import export_to_video
        from PIL import Image

        pipe = self._load()
        img = Image.open(io.BytesIO(image)).convert("RGB")
        w = max(256, (int(kw.get("width", img.width)) // 32) * 32)    # LTX needs /32
        h = max(256, (int(kw.get("height", img.height)) // 32) * 32)
        # LTX wants num_frames of the form 8*k + 1
        nf = max(9, int(duration_s * fps))
        nf = ((nf - 1) // 8) * 8 + 1
        gen = torch.Generator("cpu").manual_seed(int(kw.get("seed", 0)))
        full_prompt = prompt or f"{motion} camera motion, gentle natural movement, cinematic"
        t0 = time.monotonic()
        frames = pipe(image=img, prompt=full_prompt, width=w, height=h, num_frames=nf,
                      num_inference_steps=int(settings.ltx_steps), generator=gen).frames[0]
        elapsed = time.monotonic() - t0
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "clip.mp4"
            export_to_video(frames, str(out), fps=fps)
            data = out.read_bytes()
        return GenResult(
            data=data, mime="video/mp4", cost=gpu_util.gpu_cost(elapsed),
            meta={"provider": "ltx_local", "model": settings.ltx_model, "frames": nf,
                  "size": [w, h], "fps": fps, "elapsed_s": round(elapsed, 1)},
        )
