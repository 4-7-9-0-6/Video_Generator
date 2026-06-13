"""Download Piper voice models (EN + FR) into PIPER_MODELS_DIR.

    python scripts/download_voices.py            # downloads the configured EN + FR voices

Voices come from the rhasspy/piper-voices repo on Hugging Face (CC-licensed).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import settings  # noqa: E402

HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"

# voice name -> repo path prefix (a {prefix}.onnx and {prefix}.onnx.json exist)
VOICE_PATHS = {
    "en_US-amy-medium": "en/en_US/amy/medium/en_US-amy-medium",
    "fr_FR-siwis-medium": "fr/fr_FR/siwis/medium/fr_FR-siwis-medium",
    "en_US-lessac-medium": "en/en_US/lessac/medium/en_US-lessac-medium",
}


def _download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  exists  {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 16):
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    print(f"\r  {dest.name}: {pct:3d}% ({done >> 20} MB)", end="", flush=True)
    tmp.rename(dest)
    print(f"\r  done    {dest.name} ({dest.stat().st_size >> 20} MB)        ")


def main() -> int:
    wanted = {settings.piper_voice_en, settings.piper_voice_fr}
    out = settings.piper_models_dir
    out.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Piper voices into {out}")
    for name in wanted:
        prefix = VOICE_PATHS.get(name)
        if prefix is None:
            print(f"  [skip] unknown voice '{name}' (add it to VOICE_PATHS)")
            continue
        _download(HF_BASE + prefix + ".onnx", out / f"{name}.onnx")
        _download(HF_BASE + prefix + ".onnx.json", out / f"{name}.onnx.json")
    print("Voices ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
