"""MusicGen local music provider (spec §B.3) — real text-to-music via transformers.

A big quality jump over the numpy synth: generates an actual instrumental bed from a text
description. Runs **locally and free on CPU** (slower) and uses a GPU automatically if one
is present. Drop-in: PROVIDER_MUSIC=musicgen_local; the free `symbolic` synth stays the
default fallback. Enable on CPU with `pip install -r requirements-ml-cpu.txt`.

License note: MusicGen weights are CC-BY-NC (NON-COMMERCIAL). Free to use; not for commercial
distribution. Use the `symbolic` provider for commercial output.
"""
from __future__ import annotations

import asyncio
import io
import time
import wave

from ... import gpu_util
from ...config import settings
from ..base import Availability, Capability, GenResult, MusicProvider, ProviderInfo

_model = None
_proc = None
_TOKENS_PER_SEC = 50   # MusicGen EnCodec frame rate


class MusicGenLocalProvider(MusicProvider):
    info = ProviderInfo(
        name="musicgen_local", capability=Capability.MUSIC, kind="local",
        free=True, requires_gpu=False,   # CPU-capable (slow); auto-uses GPU if present
    )

    def availability(self) -> Availability:
        return gpu_util.require_torch("transformers")

    def estimate_cost(self, **kw: object):
        return gpu_util.gpu_cost(float(kw.get("seconds", 30.0)))

    def _load(self):
        global _model, _proc
        if _model is None:
            from transformers import AutoProcessor, MusicgenForConditionalGeneration
            _proc = AutoProcessor.from_pretrained(settings.musicgen_model)
            _model = MusicgenForConditionalGeneration.from_pretrained(
                settings.musicgen_model).to(gpu_util.torch_device())
        return _model, _proc

    async def compose(self, description: str, *, duration_s: float = 30.0,
                      key: str = "C", tempo: int = 100, **kw: object) -> GenResult:
        return await asyncio.to_thread(self._run, description, duration_s, tempo, kw)

    def _run(self, description: str, duration_s: float, tempo: int, kw: dict) -> GenResult:
        import torch

        model, proc = self._load()
        prompt = f"{description}, {tempo} BPM"
        inputs = proc(text=[prompt], padding=True, return_tensors="pt").to(gpu_util.torch_device())
        max_new = max(64, int(duration_s * _TOKENS_PER_SEC))
        t0 = time.monotonic()
        with torch.no_grad():
            audio = model.generate(**inputs, do_sample=True, max_new_tokens=max_new)
        elapsed = time.monotonic() - t0
        sr = model.config.audio_encoder.sampling_rate
        samples = audio[0, 0].cpu().numpy()
        data = _to_wav(samples, sr)
        return GenResult(
            data=data, mime="audio/wav", cost=gpu_util.gpu_cost(elapsed),
            meta={"provider": "musicgen_local", "model": settings.musicgen_model,
                  "sample_rate": sr, "duration_s": round(len(samples) / sr, 2),
                  "elapsed_s": round(elapsed, 1)},
        )


def _to_wav(samples, sr: int) -> bytes:
    import numpy as np
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()
