"""Local SD-Turbo image provider via stable-diffusion.cpp — OFFLINE, FREE, CPU-only.

This is the keystone that makes ToonForge fully local: it shells out to a bundled
`sd` binary (ggml/C++ — no torch, no Python-ML wheels, so Python 3.14-safe) running a
quantized SD-Turbo GGUF model. No GPU, no network, no API cost.

SD-Turbo is a distilled 512-native model: great quality in 1-4 steps at cfg-scale 1.0,
which is what keeps it usable on a 4-core CPU. To bound wall-clock, generation happens at
a capped resolution (longest side <= SDCPP_MAX_SIDE, default 640, rounded to /64) and is
then Lanczos-upscaled to the requested size — the stored asset keeps the requested W/H.

Install: python scripts/install_sdcpp.py && python scripts/download_sd_model.py
Select:  PROVIDER_IMAGE=sdcpp
"""
from __future__ import annotations

import asyncio
import io
import os
import subprocess
import tempfile
import time
from pathlib import Path

from ... import sdcpp_util
from ...config import settings
from ..base import Availability, Capability, Cost, GenResult, ImageProvider, ProviderInfo


def _round64(n: int) -> int:
    return max(256, (int(n) // 64) * 64)


def _gen_size(width: int, height: int, max_side: int) -> tuple[int, int]:
    """Scale the requested size down so the longest side <= max_side, rounded to /64.
    Keeps aspect ratio; SD-Turbo is happiest near 512, so we generate small then upscale."""
    longest = max(width, height)
    if longest <= max_side:
        return _round64(width), _round64(height)
    scale = max_side / longest
    return _round64(width * scale), _round64(height * scale)


class SDCppImageProvider(ImageProvider):
    info = ProviderInfo(
        name="sdcpp", capability=Capability.IMAGE, kind="local",
        free=True, requires_gpu=False,
    )

    def availability(self) -> Availability:
        exe = sdcpp_util.sd_exe()
        model = sdcpp_util.sd_model()
        if exe is None:
            return Availability(
                False, reason="stable-diffusion.cpp binary not found",
                install_hint="python scripts/install_sdcpp.py",
            )
        if model is None:
            return Availability(
                False, reason="no local SD model (*.gguf) found",
                install_hint="python scripts/download_sd_model.py",
            )
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            return Availability(False, reason="Pillow missing", install_hint="pip install Pillow")
        return Availability(True, reason=f"local CPU SD-Turbo ({Path(model).name})")

    def estimate_cost(self, **kwargs: object) -> Cost:
        return Cost(gpu_seconds=0.0, usd=0.0)  # local CPU == free

    async def generate(self, prompt: str, *, negative: str = "", width: int = 768,
                       height: int = 1024, seed: int | None = None,
                       reference_images: list[bytes] | None = None,
                       **kw: object) -> GenResult:
        exe = sdcpp_util.sd_exe()
        # a model hint (e.g. "anime") selects a style-specific model file if installed
        model = sdcpp_util.sd_model(prefer=str(kw.get("model_hint", "")))
        if exe is None or model is None:
            raise RuntimeError("sdcpp provider not ready (run scripts/install_sdcpp.py + download_sd_model.py)")

        max_side = int(kw.get("max_side", settings.sdcpp_max_side))
        gw, gh = _gen_size(width, height, max_side)
        steps = int(kw.get("steps", settings.sdcpp_steps))
        cfg = float(kw.get("cfg_scale", settings.sdcpp_cfg))
        threads = int(kw.get("threads", settings.sdcpp_threads))
        s = int(seed if seed is not None else 42)

        png, elapsed = await asyncio.to_thread(
            self._run, exe, model, prompt, negative, gw, gh, steps, cfg, threads, s
        )
        # upscale to the requested size so downstream (sheets/keyframes) keeps its resolution
        data = self._fit(png, width, height) if (gw, gh) != (width, height) else png
        return GenResult(
            data=data, mime="image/png", cost=Cost(),
            meta={"provider": "sdcpp", "model": Path(model).name, "seed": s,
                  "gen_size": [gw, gh], "out_size": [width, height], "steps": steps,
                  "cfg_scale": cfg, "elapsed_s": round(elapsed, 1)},
        )

    @staticmethod
    def _run(exe: str, model: str, prompt: str, negative: str, w: int, h: int,
             steps: int, cfg: float, threads: int, seed: int) -> tuple[bytes, float]:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.png"
            cmd = [
                exe, "-M", "img_gen", "-m", model, "-p", prompt,
                "-o", str(out), "--steps", str(steps), "--cfg-scale", str(cfg),
                "-W", str(w), "-H", str(h), "-s", str(seed),
                "--sampling-method", "euler", "-t", str(threads), "--diffusion-fa",
            ]
            if negative:
                cmd += ["-n", negative]
            # the sd binary ships its shared lib (libstable-diffusion.so / .dll) beside it;
            # on Linux the loader doesn't search the binary's own dir, so add it explicitly
            env = os.environ.copy()
            exe_dir = str(Path(exe).resolve().parent)
            env["LD_LIBRARY_PATH"] = exe_dir + os.pathsep + env.get("LD_LIBRARY_PATH", "")
            t0 = time.monotonic()
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
            elapsed = time.monotonic() - t0
            if proc.returncode != 0 or not out.exists():
                tail = (proc.stderr or proc.stdout or "")[-800:]
                raise RuntimeError(f"stable-diffusion.cpp failed (exit {proc.returncode}):\n{tail}")
            return out.read_bytes(), elapsed

    @staticmethod
    def _fit(png: bytes, width: int, height: int) -> bytes:
        from PIL import Image
        img = Image.open(io.BytesIO(png)).convert("RGB").resize((width, height), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
