"""Generate the ACE-Step song in an ISOLATED process, save it to a WAV, and exit.

ACE-Step (~7 GB) and LTX-Video don't co-fit on a 15 GB T4, and dropping the Python reference
isn't enough to reclaim ACE-Step's VRAM. The bulletproof fix: run the singing in its own process —
when it exits, the OS reclaims every byte of its GPU memory, leaving the whole card free for LTX.

gpu_render.py spawns this:  python scripts/_sing_once.py <lyrics_file> <mood> <duration_s> <out.wav>
The child inherits the parent's env (PROVIDER_SVS, API keys, GPU_OFFLOAD), so provider selection
matches the main run.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import _gpu_compat  # noqa: F401,E402 — applies the fp32-conv shim for T4/P100 on import
from app.providers.base import Capability       # noqa: E402
from app.providers.registry import get_provider  # noqa: E402


async def _main() -> int:
    lyrics_file, mood, duration_s, out_path = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
    lyrics = Path(lyrics_file).read_text(encoding="utf-8")
    svs = get_provider(Capability.SVS)
    res = await svs.sing(lyrics, language="en", mood=mood, duration_s=duration_s)
    Path(out_path).write_bytes(res.data)
    print(f"[sing] {len(res.data) // 1024} KB -> {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
