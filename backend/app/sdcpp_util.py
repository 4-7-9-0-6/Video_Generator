"""Resolve the stable-diffusion.cpp executable and the local SD-Turbo model.

This mirrors ffmpeg_util.py: it makes a fully-local, CPU-only image generator a
drop-in by bundling a prebuilt binary + a quantized model under backend/, so the app
runs OFFLINE with no GPU and no paid API.

Lookup order:
  * binary:  SDCPP_BIN env override -> backend/tools/sdcpp/sd(.exe) -> PATH ("sd")
  * model:   SD_MODEL env override (abs/rel) -> first *.gguf under backend/models/sd

Install with: python scripts/install_sdcpp.py && python scripts/download_sd_model.py
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .config import settings

_TOOLS_BIN = settings.backend_dir / "tools" / "sdcpp"
_MODELS_DIR = settings.backend_dir / "models" / "sd"


def sd_exe() -> str | None:
    override = os.environ.get("SDCPP_BIN")
    if override and Path(override).exists():
        return override
    # build naming has shifted over releases: sd-cli.exe (current), sd.exe (older)
    for name in ("sd-cli.exe", "sd.exe", "sd-cli", "sd"):
        local = _TOOLS_BIN / name
        if local.exists():
            return str(local)
    return shutil.which("sd-cli") or shutil.which("sd")


def sd_model(prefer: str = "") -> str | None:
    """Resolve the active model. `prefer` is a filename substring (e.g. "anime") used to
    pick a style-specific model when one is present; otherwise the default is returned, so
    anime styles gracefully fall back to SD-Turbo when no anime model is installed."""
    if prefer and _MODELS_DIR.exists():
        match = next((g for g in sorted(_MODELS_DIR.glob("*.gguf"))
                      if prefer.lower() in g.name.lower()), None)
        if match:
            return str(match)
    override = os.environ.get("SD_MODEL")
    if override:
        p = Path(override)
        p = p if p.is_absolute() else (settings.backend_dir / p)
        if p.exists():
            return str(p)
    if _MODELS_DIR.exists():
        # prefer Q8_0 (quality/size sweet spot), then any gguf, deterministic order
        ggufs = sorted(_MODELS_DIR.glob("*.gguf"))
        if ggufs:
            preferred = next((g for g in ggufs if "Q8_0" in g.name), None)
            return str(preferred or ggufs[0])
    return None


def models_dir() -> Path:
    return _MODELS_DIR


def tools_dir() -> Path:
    return _TOOLS_BIN


def has_sdcpp() -> bool:
    return sd_exe() is not None and sd_model() is not None
