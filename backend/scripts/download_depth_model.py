"""Download the small ONNX depth model used by the depth_parallax video provider.

~66 MB, CPU, no torch. Default is MiDaS v2.1 small (works with onnxruntime). Override the URL
with DEPTH_MODEL_URL / the path with DEPTH_MODEL in backend/.env.

    python scripts/download_depth_model.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings  # noqa: E402


def _progress(done: int, total: int) -> None:
    if total > 0:
        pct = done * 100 // total
        sys.stdout.write(f"\r  {pct:3d}%  ({done // 1024 // 1024} / {total // 1024 // 1024} MB)")
        sys.stdout.flush()


def main() -> int:
    dest = settings.depth_model
    if dest.exists():
        print(f"depth model already present: {dest}")
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = settings.depth_model_url
    print(f"downloading depth model:\n  {url}\n  -> {dest}")
    try:
        with urllib.request.urlopen(url) as r:
            total = int(r.headers.get("Content-Length", 0))
            done = 0
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    _progress(done, total)
            tmp.replace(dest)
        print(f"\ndone: {dest} ({dest.stat().st_size // 1024 // 1024} MB)")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"\nfailed: {e}\nSet a working DEPTH_MODEL_URL in backend/.env and retry.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
