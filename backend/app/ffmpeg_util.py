"""Resolve the ffmpeg / ffprobe executables.

Lookup order: FFMPEG_BIN / FFPROBE_BIN env override → the locally-installed copy under
backend/tools/ffmpeg/bin (see scripts/install_ffmpeg.py) → whatever is on PATH.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .config import settings

_TOOLS_BIN = settings.backend_dir / "tools" / "ffmpeg" / "bin"


def _resolve(name: str, env_var: str) -> str | None:
    override = os.environ.get(env_var)
    if override and Path(override).exists():
        return override
    local = _TOOLS_BIN / f"{name}.exe"
    if local.exists():
        return str(local)
    local_nix = _TOOLS_BIN / name
    if local_nix.exists():
        return str(local_nix)
    return shutil.which(name)


def ffmpeg_exe() -> str | None:
    return _resolve("ffmpeg", "FFMPEG_BIN")


def ffprobe_exe() -> str | None:
    return _resolve("ffprobe", "FFPROBE_BIN")


def has_ffmpeg() -> bool:
    return ffmpeg_exe() is not None


def kenburns_vf(kind: str, w: int, h: int, fps: int, frames: int) -> str:
    """Build the zoompan filterchain for a motion 'kind' (shared by the Ken Burns video
    provider and the episode assembler). Upscales first so pan/zoom has headroom."""
    zp = f":d={frames}:s={w}x{h}:fps={fps}"
    center = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    if kind == "zoom_in":
        pan = f"zoompan=z='min(zoom+0.0015,1.4)':{center}{zp}"
    elif kind == "zoom_out":
        pan = f"zoompan=z='if(eq(on,0),1.4,max(zoom-0.0015,1.0))':{center}{zp}"
    elif kind == "pan_left":
        pan = f"zoompan=z=1.2:x='(iw-iw/zoom)*(1-on/{frames})':y='ih/2-(ih/zoom/2)'{zp}"
    elif kind == "pan_right":
        pan = f"zoompan=z=1.2:x='(iw-iw/zoom)*(on/{frames})':y='ih/2-(ih/zoom/2)'{zp}"
    else:  # static
        pan = f"zoompan=z=1.0:x=0:y=0{zp}"
    # 1.5x upscale gives enough headroom for zoom≤1.4 / pan without 4K-heavy intermediates
    return f"scale={int(w * 3 / 2)}:{int(h * 3 / 2)},{pan},format=yuv420p"
