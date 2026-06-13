"""Download a quantized SD-Turbo GGUF model into backend/models/sd (free, offline-ready).

    python scripts/download_sd_model.py            # Q8_0 (default, ~1.4 GB, best quality)
    python scripts/download_sd_model.py --quant Q4_0   # ~0.9 GB, lighter/faster on low RAM

Model: gpustack/stable-diffusion-v2-1-turbo-GGUF (SD-Turbo, self-contained unet+vae+clip,
supported by stable-diffusion.cpp). Override the whole URL with SD_MODEL_URL.

ANIME MODEL (optional): the anime_* style presets already render anime-leaning art on the
default SD-Turbo. For a *dedicated* anime model, drop any sd.cpp-compatible .gguf into
backend/models/sd/ with "anime" in its filename — the anime_* styles auto-select it
(SD_ANIME_MODEL controls the match substring). Honest options (see docs/CAPABILITIES.md):
  * Anima-GGUF (JusteLeo/Anima-GGUF) — sd.cpp-ready but NON-COMMERCIAL + Qwen-based
    (needs a separate VAE, 30 steps @1024 -> slow on CPU). Free to use, not for commercial.
  * Animagine XL (cagliostrolab) — commercial-OK (Fair AI license) but SDXL -> realistically GPU.
Download a custom model by URL:  SD_MODEL_URL=<gguf-url> python scripts/download_sd_model.py
(name the saved file with "anime" so the style-switch picks it up).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app import sdcpp_util  # noqa: E402

_REPO = "gpustack/stable-diffusion-v2-1-turbo-GGUF"
_QUANTS = ("Q8_0", "Q4_0", "Q4_1", "FP16")


def _url_for(quant: str) -> tuple[str, str]:
    fname = f"stable-diffusion-v2-1-turbo-{quant}.gguf"
    return f"https://huggingface.co/{_REPO}/resolve/main/{fname}?download=true", fname


def main() -> int:
    quant = "Q8_0"
    if "--quant" in sys.argv:
        quant = sys.argv[sys.argv.index("--quant") + 1]
    if quant not in _QUANTS:
        raise SystemExit(f"--quant must be one of {_QUANTS}")

    override = os.environ.get("SD_MODEL_URL")
    if override:
        url, fname = override, Path(override.split("?")[0]).name
    else:
        url, fname = _url_for(quant)

    models_dir = sdcpp_util.models_dir()
    models_dir.mkdir(parents=True, exist_ok=True)
    dest = models_dir / fname
    if dest.exists() and dest.stat().st_size > 0:
        print(f"Model already present: {dest} ({dest.stat().st_size >> 20} MB)")
        return 0

    print(f"Downloading {fname} from {url}")
    tmp = dest.with_suffix(".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=1800) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done * 100 // total:3d}% ({done >> 20}/{total >> 20} MB)",
                          end="", flush=True)
    tmp.replace(dest)
    print(f"\nReady. Model at: {dest} ({dest.stat().st_size >> 20} MB)")
    print("Set PROVIDER_IMAGE=sdcpp to use it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
