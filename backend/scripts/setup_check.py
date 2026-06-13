"""Setup checker — reports which providers are live and how to enable the rest.

    python scripts/setup_check.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.providers.registry import probe_all  # noqa: E402

PIPER_HELP = (
    "Download Piper voices (.onnx + .onnx.json) into "
    f"{settings.piper_models_dir}\n"
    "  EN: https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/amy/medium\n"
    "  FR: https://huggingface.co/rhasspy/piper-voices/tree/main/fr/fr_FR/siwis/medium"
)


def main() -> int:
    print("=" * 64)
    print(" ToonForge setup check")
    print("=" * 64)
    print(f" data dir : {settings.data_dir}")
    print(f" db       : {settings.db_path}")
    print(f" languages: {', '.join(settings.languages)}")
    print(f" ffmpeg   : {'FOUND ' + (shutil.which('ffmpeg') or '') if shutil.which('ffmpeg') else 'NOT FOUND (winget install Gyan.FFmpeg)'}")
    print("-" * 64)

    probes = probe_all()
    ready = [p for p in probes if p["available"]]
    not_ready = [p for p in probes if not p["available"]]

    print(f" Providers READY ({len(ready)}):")
    for p in ready:
        sel = " *selected*" if p["selected"] else ""
        print(f"   [ok] {p['capability']:<11} {p['provider']:<16} ({p['kind']}, free={p['free']}){sel}")

    print(f"\n Providers NOT ready ({len(not_ready)}):")
    for p in not_ready:
        sel = " *selected*" if p["selected"] else ""
        print(f"   [--] {p['capability']:<11} {p['provider']:<16}{sel}")
        print(f"        reason: {p['reason']}")
        if p["install_hint"]:
            print(f"        fix:    {p['install_hint']}")

    print("-" * 64)
    print(PIPER_HELP)
    print("=" * 64)

    # Non-fatal: report only. Return 0 so this is safe in CI smoke runs.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
