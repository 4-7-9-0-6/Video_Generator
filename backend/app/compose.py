"""Episode Composer (spec Module D) — assemble shots + voice + subtitles into one MP4.

CPU-only pipeline, all via the local FFmpeg:
  per shot -> Ken Burns clip of the keyframe + the shot's Piper voiceover (or silence),
  concat the segments, build an SRT from shot timing, burn it in, export at a preset.

Each ffmpeg invocation runs with cwd set to a temp dir and uses relative filenames, so
Windows drive-letter paths never trip the subtitles filter's escaping rules.
"""
from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from . import lipsync as lipsync_fx
from . import models, music_brief, music_synth, reframe, scene, voicelab
from .ffmpeg_util import ffmpeg_exe, has_ffmpeg, kenburns_vf
from .providers.base import Capability
from .providers.music.symbolic import melody_notes
from .providers.registry import get_provider

# preset -> (width, height)
EXPORT_PRESETS: dict[str, tuple[int, int]] = {
    "youtube_1080p": (1920, 1080),
    "youtube_4k": (3840, 2160),
    "shorts_1080x1920": (1080, 1920),
    "tiktok_1080x1920": (1080, 1920),
    "instagram_reel": (1080, 1920),
    "instagram_square": (1080, 1080),
    "instagram_portrait": (1080, 1350),
}

# color-grade "look" presets — pure FFmpeg video filters (free, CPU). Applied in the final pass.
GRADE_PRESETS: dict[str, str] = {
    "none": "",
    "warm": "eq=saturation=1.12,colorbalance=rm=0.06:gm=0.02:bm=-0.06",
    "cool": "eq=saturation=1.08,colorbalance=rm=-0.06:bm=0.06",
    "cinematic": "curves=preset=medium_contrast,colorbalance=rs=-0.08:bs=0.08:rm=0.04:bm=-0.04,eq=saturation=1.1",
    "vivid": "eq=contrast=1.08:saturation=1.35",
    "noir": "hue=s=0,eq=contrast=1.22:brightness=0.02",
    "vintage": "curves=preset=vintage,eq=saturation=0.92",
}

# shot-to-shot transitions — names map straight to FFmpeg xfade (free, CPU). "none" = hard cuts.
TRANSITIONS: tuple[str, ...] = (
    "none", "fade", "fadeblack", "dissolve", "slideleft", "wipeleft", "circleopen", "smoothleft",
)

ProgressCb = Callable[[float, str], None]


def _xfade_chain(n: int, durs: list[float], td: float, transition: str) -> tuple[str, str, str]:
    """Build a filter_complex that xfades n segment inputs (each with v+a) into one stream.
    Returns (filter_complex, final_video_label, final_audio_label). Video uses xfade with the
    right cumulative offsets; audio uses acrossfade (auto-timed)."""
    v_parts, a_parts = [], []
    prev_v, prev_a = "0:v", "0:a"
    cum = durs[0]
    for k in range(1, n):
        offset = max(0.0, cum - td)
        vout, aout = f"vx{k}", f"ax{k}"
        v_parts.append(f"[{prev_v}][{k}:v]xfade=transition={transition}:duration={td:.3f}:offset={offset:.3f}[{vout}]")
        a_parts.append(f"[{prev_a}][{k}:a]acrossfade=d={td:.3f}[{aout}]")
        prev_v, prev_a = vout, aout
        cum = cum + durs[k] - td
    return ";".join(v_parts + a_parts), prev_v, prev_a


def _ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(entries: list[tuple[str, float, float]]) -> str:
    out = []
    idx = 1
    for text, start, end in entries:
        if not text.strip():
            continue
        out.append(f"{idx}\n{_ts(start)} --> {_ts(max(end, start + 0.3))}\n{text.strip()}\n")
        idx += 1
    return "\n".join(out)


def group_words_to_cues(words: list[tuple[str, float, float]], *, max_words: int = 7,
                        max_dur: float = 3.0, max_gap: float = 0.7,
                        ) -> list[tuple[str, float, float]]:
    """Group aligned words into short, readable subtitle cues (karaoke-friendly)."""
    cues: list[tuple[str, float, float]] = []
    cur: list[str] = []
    start = end = 0.0
    for word, ws, we in words:
        if not word.strip():
            continue
        if cur and (len(cur) >= max_words or (we - start) > max_dur or (ws - end) > max_gap):
            cues.append((" ".join(cur), start, end))
            cur = []
        if not cur:
            start = ws
        cur.append(word.strip())
        end = we
    if cur:
        cues.append((" ".join(cur), start, end))
    return cues


async def _run(args: list[str], cwd: Path) -> None:
    # Run FFmpeg in a worker thread with sync subprocess.run — NOT asyncio.create_subprocess_exec,
    # which raises NotImplementedError on Windows event loops that aren't the Proactor loop (e.g.
    # under some uvicorn/--reload setups). subprocess.run works regardless of the loop type.
    proc = await asyncio.to_thread(
        lambda: subprocess.run(args, cwd=str(cwd), capture_output=True))
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b"").decode(errors="ignore")
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {err[-900:]}")


async def assemble_episode(project: dict[str, Any], shots: list[dict[str, Any]], *,
                           voice: bool = True, sing: bool = False, subtitles: bool = True,
                           word_subtitles: bool = True, music: bool = False,
                           music_description: str = "gentle cheerful children's nursery music",
                           music_tempo: int = 96, music_auto: bool = True,
                           sing_vibrato: float = 0.3, key_override: str = "",
                           tempo_override: int = 0, lipsync: bool = False,
                           preset: str = "youtube_1080p", smart_reframe: bool = True,
                           grade: str = "none", transition: str = "none",
                           transition_dur: float = 0.4,
                           progress: ProgressCb = lambda f, m: None) -> dict[str, Any]:
    if not has_ffmpeg():
        raise RuntimeError("ffmpeg not installed — run: python scripts/install_ffmpeg.py")

    storage = get_provider(Capability.STORAGE)
    tts = get_provider(Capability.TTS, required=False) if voice else None
    if tts is not None and not tts.availability().available:
        tts = None
    # sing override: route the voiceover through the SVS provider (melody-pitched vocals)
    svs = get_provider(Capability.SVS, required=False) if (voice and sing) else None
    if svs is not None and not svs.availability().available:
        svs = None
    align = get_provider(Capability.ALIGN, required=False) if (word_subtitles and tts) else None
    if align is not None and not align.availability().available:
        align = None

    # GPU image-to-video animation (e.g. ltx_local) when configured + available; otherwise
    # the CPU Ken Burns path below. Empty PROVIDER_VIDEO (the CPU default) => video is None.
    video = get_provider(Capability.VIDEO, required=False)
    if video is not None and not video.availability().available:
        video = None
    animated = video is not None
    word_stamps: list[tuple[str, float, float, int]] = []   # (word, start, end, shot_index)
    word_mode = align is not None

    w, h = EXPORT_PRESETS.get(preset, (project["width"], project["height"]))
    fps = project["fps"]
    usable = [s for s in shots if s.get("keyframe_id")]
    if not usable:
        raise ValueError("no shots have keyframes yet — render keyframes first")

    # one music brief drives both the sung melody and the auto music bed (same mood),
    # unless the caller overrides the key/tempo (then both follow the override).
    brief = (music_brief.music_brief(" ".join(s.get("text", "") for s in usable))
             if (sing or (music and music_auto)) else None)
    has_key_override = bool(key_override and key_override.lower() != "auto")
    sing_key = key_override if has_key_override else (brief["key"] if brief else "C")
    sing_tempo = tempo_override if tempo_override else (brief["tempo"] if brief else 100)

    ff = ffmpeg_exe()
    srt_entries: list[tuple[str, float, float]] = []
    timeline = 0.0

    with TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        seg_names: list[str] = []
        seg_durs: list[float] = []

        for i, shot in enumerate(usable):
            progress(i / (len(usable) + 1), f"rendering shot {i + 1}/{len(usable)}")
            kf = models.get("assets", shot["keyframe_id"])
            raw = storage.open(kf["path"])
            # content-aware reframe to the export aspect (e.g. 16:9 keyframe -> 9:16 Short)
            # so the subject stays framed instead of being stretched by the scale filter
            framed = reframe.reframe_to_aspect(raw, w, h) if smart_reframe else raw
            (tmp / f"key{i}.png").write_bytes(framed)

            seg_dur = float(shot.get("duration_s") or 4.0)
            voice_file = None
            if (svs is not None or tts is not None) and shot.get("text"):
                if svs is not None:
                    res = await svs.sing(shot["text"], language=project["language"],
                                         key=sing_key, tempo=sing_tempo, vibrato=sing_vibrato)
                else:
                    res = await tts.synthesize(shot["text"], language=project["language"])
                (tmp / f"voice{i}.wav").write_bytes(res.data)
                voice_file = f"voice{i}.wav"
                seg_dur = max(seg_dur, voicelab.wav_duration(res.data) + 0.3)
                if align is not None and word_mode:
                    progress(i / (len(usable) + 1), f"aligning words (shot {i + 1})")
                    try:
                        for s in await align.align(res.data, text=shot["text"],
                                                   language=project["language"]):
                            word_stamps.append((s.word, timeline + s.start, timeline + s.end, i))
                    except Exception:  # noqa: BLE001 — fall back to line-level subtitles
                        word_mode = False

            # lip-sync: render a talking clip (mouth synced to the voice) as the segment
            # (trades the Ken Burns camera move for mouth movement; needs a voice track)
            if lipsync and voice_file:
                progress(i / (len(usable) + 1), f"lip-sync shot {i + 1}/{len(usable)}")
                talk = await lipsync_fx.render_talking_clip(
                    framed, res.data, duration_s=seg_dur, fps=fps, width=w, height=h)
                (tmp / f"seg{i}.mp4").write_bytes(talk)
                seg_names.append(f"seg{i}.mp4")
                seg_durs.append(seg_dur)
                srt_entries.append((shot.get("text", ""), timeline, timeline + seg_dur))
                timeline += seg_dur
                continue

            # video source: a real animated clip (GPU) or a Ken Burns move on the still (CPU)
            if animated:
                progress(i / (len(usable) + 1), f"animating shot {i + 1}/{len(usable)}")
                clip = await video.animate(
                    framed, motion=shot.get("camera", "static"), duration_s=seg_dur,
                    fps=fps, prompt=shot.get("text", ""), width=w, height=h)
                (tmp / f"anim{i}.mp4").write_bytes(clip.data)
                vin = ["-i", f"anim{i}.mp4"]
                vchain = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                          f"crop={w}:{h},fps={fps},format=yuv420p[v]")
            else:
                kind = scene.MOTION_PRESETS.get(shot.get("camera", "static"),
                                                scene.MOTION_PRESETS["static"])["kind"]
                vin = ["-loop", "1", "-i", f"key{i}.png"]
                vchain = f"[0:v]{kenburns_vf(kind, w, h, fps, max(1, round(seg_dur * fps)))}[v]"

            common_tail = ["-t", f"{seg_dur:.3f}", "-r", str(fps),
                           "-c:v", "libx264", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-ar", "44100", "-ac", "2", f"seg{i}.mp4"]
            if voice_file:
                args = [ff, "-y", *vin, "-i", voice_file,
                        "-filter_complex",
                        f"{vchain};[1:a]aformat=sample_rates=44100:channel_layouts=stereo,apad[a]",
                        "-map", "[v]", "-map", "[a]", *common_tail]
            else:
                args = [ff, "-y", *vin,
                        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                        "-filter_complex", vchain,
                        "-map", "[v]", "-map", "1:a", *common_tail]
            await _run(args, tmp)
            seg_names.append(f"seg{i}.mp4")
            seg_durs.append(seg_dur)
            srt_entries.append((shot.get("text", ""), timeline, timeline + seg_dur))
            timeline += seg_dur

        # stitch: hard-cut concat (fast, lossless copy) OR xfade transitions (re-encode, overlaps
        # clips by `td`, which compresses the timeline — subtitles/music are shifted to match).
        progress(len(usable) / (len(usable) + 1), "stitching")
        n = len(seg_names)
        td = 0.0
        transitions_on = transition in TRANSITIONS and transition != "none" and n > 1
        if transitions_on:
            td = max(0.1, min(transition_dur, (min(seg_durs) / 2) - 0.05))
            fc, vlab, alab = _xfade_chain(n, seg_durs, td, transition)
            inputs: list[str] = []
            for nm in seg_names:
                inputs += ["-i", nm]
            await _run([ff, "-y", *inputs, "-filter_complex", fc,
                        "-map", f"[{vlab}]", "-map", f"[{alab}]", "-r", str(fps),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-ar", "44100", "-ac", "2", "episode.mp4"], tmp)
        else:
            (tmp / "list.txt").write_text("".join(f"file '{nm}'\n" for nm in seg_names), encoding="utf-8")
            await _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
                        "-c", "copy", "episode.mp4"], tmp)
        current = "episode.mp4"

        # with transitions the video is shorter by (n-1)*td, and shot k starts k*td earlier
        final_total = timeline - (n - 1) * td if transitions_on else timeline
        if transitions_on:
            srt_entries = [(t, max(0.0, s - k * td), max(0.0, e - k * td))
                           for k, (t, s, e) in enumerate(srt_entries)]
            word_stamps = [(w, max(0.0, s - si * td), max(0.0, e - si * td), si)
                           for (w, s, e, si) in word_stamps]

        # music bed, auto-ducked under the vocals (sidechain compression)
        music_mood = None
        music_key = "C"
        if music:
            if music_auto and brief:
                # "lyrics alone" -> the brief picked a fitting mood/tempo/key from the shot text
                music_description, music_tempo, music_key = (
                    brief["description"], brief["tempo"], brief["key"])
                music_mood = brief["mood"]
            # caller overrides keep the bed in the same key/tempo as the sung vocals
            if has_key_override:
                music_key = key_override
                if "minor" in key_override.lower() and "minor" not in music_description.lower():
                    music_description += ", minor key"
            if tempo_override:
                music_tempo = tempo_override
            progress(0.9, f"music bed ({music_mood or 'custom'})")
            notes, _info = melody_notes(music_description, duration_s=final_total,
                                        key=music_key, tempo=music_tempo)
            (tmp / "music.wav").write_bytes(music_synth.synth_wav(notes, total_s=final_total))
            await _run([
                ff, "-y", "-i", current, "-i", "music.wav", "-filter_complex",
                "[0:a]asplit=2[voa][vob];"
                "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.35[m];"
                "[m][voa]sidechaincompress=threshold=0.05:ratio=6:attack=10:release=350[duck];"
                "[duck][vob]amix=inputs=2:duration=first:normalize=0[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                "-c:a", "aac", "-ar", "44100", "-ac", "2", "episode_music.mp4",
            ], tmp)
            current = "episode_music.mp4"

        # subtitles: word-level cues when aligned, else line-level from shot timing
        used_word_subs = bool(word_mode and word_stamps)
        if subtitles:
            ws3 = [(w, s, e) for (w, s, e, _si) in word_stamps]   # drop the shot-index tag
            entries = group_words_to_cues(ws3) if used_word_subs else srt_entries
            srt_text = build_srt(entries)
        else:
            srt_text = ""

        # final video-filter pass — subtitles + color grade are both video filters, so one
        # re-encode handles both (audio is copied through untouched).
        vf_parts: list[str] = []
        if srt_text:
            (tmp / "subs.srt").write_text(srt_text, encoding="utf-8")
            vf_parts.append("subtitles=subs.srt")
        grade_vf = GRADE_PRESETS.get(grade, "")
        if grade_vf:
            vf_parts.append(grade_vf)
        if vf_parts:
            progress(0.95, "subtitles + grade" if grade_vf and srt_text else
                     ("color grade" if grade_vf else "subtitles"))
            await _run([ff, "-y", "-i", current, "-vf", ",".join(vf_parts),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy", "final.mp4"], tmp)
            current = "final.mp4"

        data = (tmp / current).read_bytes()
        srt_bytes = srt_text.encode("utf-8") if srt_text else b""

    name = f"{models.new_id('ep_')}.mp4"
    rel = storage.put(data, name=name, subdir=f"episodes/{project['id']}")
    asset = models.create_asset(
        kind="video", path=rel, project_id=project["id"], mime="video/mp4",
        provider="ffmpeg",
        meta={"kind": "episode", "preset": preset, "resolution": f"{w}x{h}",
              "fps": fps, "shots": len(usable), "duration_s": round(final_total, 2),
              "transition": transition if transitions_on else "none",
              "voice": (svs or tts) is not None, "sing": svs is not None,
              "sing_key": sing_key if svs is not None else None,
              "sing_vibrato": sing_vibrato if svs is not None else None,
              "subtitles": bool(srt_text),
              "word_subtitles": used_word_subs, "music": music,
              "smart_reframe": smart_reframe, "animated": animated, "lipsync": lipsync,
              "grade": grade if GRADE_PRESETS.get(grade) else "none",
              "video_provider": ("lipsync_mouth_flap" if lipsync else
                                 (video.info.name if animated else "ffmpeg_kenburns")),
              "music_auto": music_auto and music, "music_mood": music_mood,
              "music_tempo": music_tempo if music else None},
    )

    result = {"asset_id": asset["id"], "url": f"/assets/{asset['id']}",
              "duration_s": round(final_total, 2), "resolution": f"{w}x{h}",
              "preset": preset, "shots": len(usable),
              "word_subtitles": used_word_subs, "music": music}
    if srt_bytes:
        srt_rel = storage.put(srt_bytes, name=name.replace(".mp4", ".srt"),
                              subdir=f"episodes/{project['id']}")
        srt_asset = models.create_asset(kind="subtitle", path=srt_rel,
                                        project_id=project["id"], mime="application/x-subrip",
                                        meta={"kind": "subtitles"})
        result["srt_asset_id"] = srt_asset["id"]
        result["srt_url"] = f"/assets/{srt_asset['id']}"
    return result
