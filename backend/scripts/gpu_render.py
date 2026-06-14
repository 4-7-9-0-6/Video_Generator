"""GPU render pipeline — prompt -> animated, SUNG, (optional lip-synced) music video.

Runs on a free cloud GPU (Kaggle / Colab / Lightning — see docs/FREE_GPU.md). Reuses the
ToonForge providers and adds real GPU singing + animation:

  topic -> LLM writes lyrics (OpenRouter) -> ACE-Step sings the whole song (vocals+music)
        -> Flux keyframes per line (Cloudflare, free) -> LTX animates each (or SadTalker
           lip-syncs each) -> concat + overlay the sung track + burn subtitles -> MP4.

    python scripts/gpu_render.py --prompt "a brave little robot lights up a neon city" \
        --style anime_cyberpunk --scenes 6 --out /kaggle/working/song.mp4
    python scripts/gpu_render.py --lyrics-file lyrics.txt --lipsync   # SadTalker instead of LTX

Providers are chosen by env (the notebook sets them):
  PROVIDER_IMAGE=cloudflare  PROVIDER_VIDEO=ltx_local  PROVIDER_SVS=acestep_local
  PROVIDER_LIPSYNC=sadtalker_local  OPENROUTER_API_KEY=...  CLOUDFLARE_ACCOUNT_ID/TOKEN=...
"""
from __future__ import annotations

# Pre-Ampere GPUs (T4/P100, the free-tier cards) have no cuDNN bf16 convolution engine, so the
# ACE-Step and LTX VAE/vocoder decodes crash ("unable to find an engine to execute this
# computation"). Those convs are small and run once, so disabling cuDNN routes them to the
# native bf16 kernel at negligible cost and keeps the models in fast bf16.
try:
    import torch as _torch
    if _torch.cuda.is_available() and _torch.cuda.get_device_capability(0)[0] < 8:
        _torch.backends.cudnn.enabled = False
except Exception:  # noqa: BLE001 — torch absent (CPU box) or driver issue: nothing to disable
    pass

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import foundry, scene, songwriter           # noqa: E402
from app.compose import build_srt, group_words_to_cues  # noqa: E402
from app.ffmpeg_util import ffmpeg_exe                # noqa: E402
from app.providers.base import Capability             # noqa: E402
from app.providers.registry import get_provider       # noqa: E402


def _run(args: list[str], cwd: Path) -> None:
    p = subprocess.run([str(a) for a in args], cwd=str(cwd), capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {(p.stderr or p.stdout)[-800:]}")


async def render(topic: str, lyrics_text: str, style: str, scenes: int, lipsync: bool,
                 width: int, height: int, fps: int, out_path: str) -> None:
    ff = ffmpeg_exe()
    image = get_provider(Capability.IMAGE)
    svs = get_provider(Capability.SVS)                 # acestep_local
    video = get_provider(Capability.VIDEO, required=False) if not lipsync else None
    lip = get_provider(Capability.LIPSYNC) if lipsync else None

    # 1. lyrics: use provided text, else have the LLM write them
    if lyrics_text:
        lines = [{"section": "verse", "text": ln.strip(), "characters": []}
                 for ln in lyrics_text.splitlines() if ln.strip()]
        song = {"title": topic[:60] or "Song", "mood": "playful",
                "characters": [{"name": "Hero", "description": topic}], "lines": lines,
                "has_chorus": any("chorus" in ln.lower() for ln in lyrics_text.splitlines())}
    else:
        song = await songwriter.write_song(topic, style=style, scenes=scenes)
    lyric_lines = [ln["text"] for ln in song["lines"]]
    print(f"[1/5] song '{song['title']}' — {len(lyric_lines)} lines", flush=True)

    # 2. ACE-Step sings the whole song (vocals + music) once
    full_lyrics = "\n".join(f"[{ln['section']}] {ln['text']}" for ln in song["lines"])
    sung = await svs.sing(full_lyrics, language="en", mood=song["mood"],
                          duration_s=max(20, len(lyric_lines) * 6))
    print(f"[2/5] ACE-Step sung track: {len(sung.data) // 1024} KB", flush=True)

    with TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        (tmpd / "song.wav").write_bytes(sung.data)
        # song duration -> even time slice per shot
        probe = subprocess.run(
            [ff.replace("ffmpeg", "ffprobe"), "-v", "error", "-show_entries",
             "format=duration", "-of", "csv=p=0", "song.wav"],
            cwd=str(tmpd), capture_output=True, text=True)
        total = float((probe.stdout or "0").strip() or 0) or len(lyric_lines) * 6.0
        seg = total / max(1, len(lyric_lines))

        seg_files, srt_entries, t = [], [], 0.0
        for i, line in enumerate(song["lines"]):
            present = [song["characters"][0]] if song["characters"] else []
            char_map = {c["name"]: {**c, "id": c["name"], "palette": [],
                                    "style_preset": style} for c in present}
            prompt = scene.build_shot_prompt(
                {"text": line["text"], "characters": list(char_map), "camera": "static",
                 "background": ""}, char_map, {"style_preset": style})
            kf = await image.generate(prompt, width=width, height=height, seed=1000 + i)
            (tmpd / f"key{i}.png").write_bytes(kf.data)
            print(f"[3/5] keyframe {i + 1}/{len(song['lines'])}", flush=True)

            if lipsync:
                # SadTalker: the character mouths this slice of the sung track
                a = tmpd / f"a{i}.wav"
                _run([ff, "-y", "-i", "song.wav", "-ss", f"{t:.2f}", "-t", f"{seg:.2f}", a.name], tmpd)
                clip = await lip.apply((tmpd / f"key{i}.png").read_bytes(), a.read_bytes())
                (tmpd / f"clip{i}.mp4").write_bytes(clip.data)
                vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps}"
                _run([ff, "-y", "-i", f"clip{i}.mp4", "-vf", vf, "-an", "-t", f"{seg:.2f}",
                      "-r", str(fps), "-c:v", "libx264", "-pix_fmt", "yuv420p", f"seg{i}.mp4"], tmpd)
            else:
                # LTX animates the still; pad/hold to fill the slice
                clip = await video.animate((tmpd / f"key{i}.png").read_bytes(), motion="static",
                                           duration_s=min(seg, 6.0), fps=fps,
                                           prompt=line["text"], width=width, height=height)
                (tmpd / f"clip{i}.mp4").write_bytes(clip.data)
                _run([ff, "-y", "-i", f"clip{i}.mp4", "-vf",
                      f"scale={width}:{height},fps={fps},tpad=stop_mode=clone:stop_duration={seg:.2f}",
                      "-an", "-t", f"{seg:.2f}", "-r", str(fps), "-c:v", "libx264",
                      "-pix_fmt", "yuv420p", f"seg{i}.mp4"], tmpd)

            seg_files.append(f"seg{i}.mp4")
            srt_entries.append((line["text"], t, t + seg))
            t += seg

        # 4. concat the silent clips
        (tmpd / "list.txt").write_text("".join(f"file '{n}'\n" for n in seg_files))
        _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", "silent.mp4"], tmpd)
        # 5. add the sung master track + burn subtitles
        (tmpd / "subs.srt").write_text(build_srt(srt_entries), encoding="utf-8")
        _run([ff, "-y", "-i", "silent.mp4", "-i", "song.wav", "-vf", "subtitles=subs.srt",
              "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-shortest", "final.mp4"], tmpd)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes((tmpd / "final.mp4").read_bytes())
    print(f"[5/5] DONE -> {out_path}  ({'lip-sync' if lipsync else 'LTX animation'} + ACE-Step singing)", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="")
    ap.add_argument("--lyrics-file", default="")
    ap.add_argument("--style", default="3d_toddler_original")
    ap.add_argument("--scenes", type=int, default=6)
    ap.add_argument("--lipsync", action="store_true", help="SadTalker lip-sync instead of LTX motion")
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=576)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--out", default="song.mp4")
    a = ap.parse_args()
    if a.style not in foundry.STYLE_PRESETS:
        print(f"unknown style; choose from {list(foundry.STYLE_PRESETS)}"); return 2
    lyrics = Path(a.lyrics_file).read_text(encoding="utf-8") if a.lyrics_file else ""
    if not a.prompt and not lyrics:
        print("provide --prompt or --lyrics-file"); return 2
    asyncio.run(render(a.prompt, lyrics, a.style, a.scenes, a.lipsync,
                       a.width, a.height, a.fps, a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
