"""Download a static FFmpeg build into backend/tools/ffmpeg/bin (no admin, no PATH edits).

    python scripts/install_ffmpeg.py

Uses the BtbN static Windows build by default (ffmpeg + ffprobe). Override with FFMPEG_ZIP_URL.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import settings  # noqa: E402

URL = os.environ.get(
    "FFMPEG_ZIP_URL",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
)
WANT = ("ffmpeg.exe", "ffprobe.exe")


def main() -> int:
    bin_dir = settings.backend_dir / "tools" / "ffmpeg" / "bin"
    if all((bin_dir / w).exists() for w in WANT):
        print(f"FFmpeg already present in {bin_dir}")
        return _verify(bin_dir)

    bin_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading FFmpeg from {URL}")
    buf = io.BytesIO()
    with httpx.stream("GET", URL, follow_redirects=True, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        for chunk in r.iter_bytes(1 << 16):
            buf.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done * 100 // total:3d}% ({done >> 20} MB)", end="", flush=True)
    print("\n  extracting…")

    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(buf) as zf:
        zf.extractall(tmp)
        for want in WANT:
            match = next((p for p in Path(tmp).rglob(want)), None)
            if match is None:
                print(f"  [error] {want} not found in archive")
                return 1
            shutil.copy2(match, bin_dir / want)
            print(f"  installed {want}")
    return _verify(bin_dir)


def _verify(bin_dir: Path) -> int:
    exe = bin_dir / "ffmpeg.exe"
    out = subprocess.run([str(exe), "-version"], capture_output=True, text=True)
    print(out.stdout.splitlines()[0] if out.stdout else "ffmpeg ran")
    print(f"Ready. ffmpeg at: {exe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
