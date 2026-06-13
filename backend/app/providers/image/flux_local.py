"""FLUX.1-schnell local GPU image provider — the high-quality image upgrade (spec §A).

FLUX.1-schnell is Apache-2.0 (free, even commercially), 4-step, and runs on a single
24 GB NVIDIA GPU (less with GPU_OFFLOAD=1). Drop-in: PROVIDER_IMAGE=flux_local. The
pipeline is lazy-loaded once. On a machine with no CUDA GPU, availability() reports exactly
why and the rest of the app keeps using the CPU SD-Turbo provider.

Weights download from Hugging Face on first use; cache them on a mounted volume (see
docs/GPU_DEPLOY.md) so a rented GPU doesn't re-download every session.
"""
from __future__ import annotations

import asyncio
import io
import time

from ... import gpu_util
from ...config import settings
from ..base import Capability, GenResult, ImageProvider, ProviderInfo

_pipe = None


class FluxLocalImageProvider(ImageProvider):
    info = ProviderInfo(
        name="flux_local", capability=Capability.IMAGE, kind="local",
        free=True, requires_gpu=True,
    )

    def availability(self):
        return gpu_util.require_gpu("diffusers")

    def estimate_cost(self, **kw: object):
        return gpu_util.gpu_cost(float(kw.get("seconds", 4.0)))

    def _load(self):
        global _pipe
        if _pipe is None:
            import torch
            from diffusers import FluxPipeline
            _pipe = FluxPipeline.from_pretrained(settings.flux_model, torch_dtype=torch.bfloat16)
            if settings.gpu_offload:
                _pipe.enable_model_cpu_offload()   # fits ~12-16 GB cards, slower
            else:
                _pipe.to("cuda")
        return _pipe

    async def generate(self, prompt: str, *, negative: str = "", width: int = 768,
                       height: int = 1024, seed: int | None = None,
                       reference_images: list[bytes] | None = None,
                       **kw: object) -> GenResult:
        return await asyncio.to_thread(self._run, prompt, width, height, seed, kw)

    def _run(self, prompt: str, width: int, height: int, seed: int | None, kw: dict) -> GenResult:
        import torch
        pipe = self._load()
        w = max(256, (int(width) // 16) * 16)      # FLUX needs dims divisible by 16
        h = max(256, (int(height) // 16) * 16)
        steps = int(kw.get("steps", settings.flux_steps))
        gen = torch.Generator("cpu").manual_seed(int(seed) if seed is not None else 0)
        t0 = time.monotonic()
        # schnell is guidance-distilled: guidance_scale=0.0, ~4 steps
        image = pipe(prompt=prompt, width=w, height=h, num_inference_steps=steps,
                     guidance_scale=0.0, max_sequence_length=256, generator=gen).images[0]
        elapsed = time.monotonic() - t0
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return GenResult(
            data=buf.getvalue(), mime="image/png", cost=gpu_util.gpu_cost(elapsed),
            meta={"provider": "flux_local", "model": settings.flux_model, "seed": seed,
                  "size": [w, h], "steps": steps, "elapsed_s": round(elapsed, 1)},
        )
