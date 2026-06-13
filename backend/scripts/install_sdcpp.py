"""Download the stable-diffusion.cpp CPU binary into backend/tools/sdcpp (no admin, no PATH).

    python scripts/install_sdcpp.py

Queries the latest leejet/stable-diffusion.cpp GitHub release and grabs the Windows
AVX2 x64 build (CPU-only; the i5/Tiger-Lake-class dev box supports AVX2). Override the
asset choice with SDCPP_ZIP_URL, or the AVX variant with SDCPP_VARIANT (avx2|avx|avx512|noavx).
"""
from __future__ import annotations

import io
import os
import platform
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app import sdcpp_util  # noqa: E402

_API = "https://api.github.com/repos/leejet/stable-diffusion.cpp/releases/latest"
_VARIANT = os.environ.get("SDCPP_VARIANT", "avx2")
_IS_WIN = platform.system() == "Windows"


def _matches(name: str) -> bool:
    """Pick the plain CPU build for this OS (skip GPU/accelerator variants)."""
    if _IS_WIN:
        return f"bin-win-{_VARIANT}-x64.zip" in name
    # Linux container: the generic CPU x86_64 build, not rocm/vulkan/cuda
    return ("bin-Linux" in name and "x86_64.zip" in name
            and not any(x in name for x in ("rocm", "vulkan", "cuda")))


def _resolve_url() -> str:
    override = os.environ.get("SDCPP_ZIP_URL")
    if override:
        return override
    r = httpx.get(_API, follow_redirects=True, timeout=60,
                  headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    assets = r.json().get("assets", [])
    for a in assets:
        if _matches(a["name"]):
            return a["browser_download_url"]
    names = ", ".join(a["name"] for a in assets)
    raise SystemExit(f"No matching CPU build for {platform.system()} in latest release. "
                     f"Available: {names}")


def main() -> int:
    bin_dir = sdcpp_util.tools_dir()
    if sdcpp_util.sd_exe() is not None:
        print(f"stable-diffusion.cpp already present: {sdcpp_util.sd_exe()}")
        return _verify()

    bin_dir.mkdir(parents=True, exist_ok=True)
    url = _resolve_url()
    print(f"Downloading stable-diffusion.cpp ({_VARIANT}) from {url}")
    buf = io.BytesIO()
    with httpx.stream("GET", url, follow_redirects=True, timeout=600) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        for chunk in r.iter_bytes(1 << 16):
            buf.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done * 100 // total:3d}% ({done >> 20} MB)", end="", flush=True)
    print("\n  extracting…")

    # extract every file (sd-cli + any ggml/*.so|*.dll runtime deps) flat into tools/sdcpp
    with zipfile.ZipFile(buf) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            name = Path(member.filename).name
            if not name:
                continue
            dest = bin_dir / name
            dest.write_bytes(zf.read(member))
            # POSIX zips don't carry the +x bit through write_bytes — restore it for binaries
            if not _IS_WIN and (name.startswith("sd") or "." not in name):
                dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    count = len(list(bin_dir.glob("*")))
    print(f"  installed {count} files into {bin_dir}")
    return _verify()


def _verify() -> int:
    exe = sdcpp_util.sd_exe()
    if exe is None:
        print("[error] sd binary not found after install")
        return 1
    out = subprocess.run([exe, "--help"], capture_output=True, text=True)
    ok = "txt2img" in (out.stdout + out.stderr).lower()
    print(f"Ready. sd at: {exe}" + ("" if ok else "  (warning: --help looked unexpected)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
