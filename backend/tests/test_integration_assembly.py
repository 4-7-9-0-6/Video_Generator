"""End-to-end integration tests for the full FFmpeg assembly — the path unit tests skip, and
where the Windows asyncio-subprocess crash hid. These actually run FFmpeg and verify a valid MP4
comes out, including the feature combos (lip-sync + transitions + grade + music + word subs).

Why this file exists: the original crash was *event-loop dependent* — `asyncio.run()` uses the
Proactor loop (works), but uvicorn used a Selector loop where `asyncio.create_subprocess_exec`
raises NotImplementedError. So we (1) statically forbid that call in the ffmpeg paths, and
(2) actually run the assembly on a Selector loop to reproduce the exact failure condition.
"""
from __future__ import annotations

import asyncio
import inspect
import subprocess
from pathlib import Path

import pytest

from app import compose, models
from app.config import settings
from app.db import init_db
from app.ffmpeg_util import ffmpeg_exe, has_ffmpeg
from app.jobs.handlers import JobContext, handle_shot_keyframe
from app.providers import registry
from app.providers.base import Capability
from app.providers.registry import get_provider


@pytest.fixture(autouse=True)
def _db():
    init_db()


@pytest.fixture()
def mock_image():
    prev = settings.providers.get("image")
    settings.providers["image"] = "mock"
    registry._cache.clear()
    yield
    settings.providers["image"] = prev
    registry._cache.clear()


def _tts_ok() -> bool:
    try:
        p = get_provider(Capability.TTS, required=False)
        return p is not None and p.availability().available
    except Exception:  # noqa: BLE001
        return False


def _project_with_keyframes(n: int = 3):
    """Small project (320x240) with n mock-rendered keyframes — fast to assemble."""
    project = models.create_project("Ep", width=320, height=240, fps=10)
    shots = []
    for i in range(n):
        s = models.create_shot(project["id"], i, f"La la line {i}", camera="static", duration_s=1.0)
        asyncio.run(handle_shot_keyframe(
            {"id": f"kf{i}", "payload": {"shot_id": s["id"]}}, JobContext(f"kf{i}")))
        shots.append(models.get("shots", s["id"]))
    return project, shots


def _probe_streams(asset_id: str) -> str:
    asset = models.get("assets", asset_id)
    path = settings.assets_dir() / asset["path"]
    ff = ffmpeg_exe()
    ffprobe = str(Path(ff).with_name("ffprobe" + Path(ff).suffix))
    return subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=codec_type",
                           "-of", "default=nw=1", str(path)], capture_output=True, text=True).stdout


# ---- (1) static regression guard — runs everywhere, no ffmpeg needed ----

def test_ffmpeg_paths_avoid_asyncio_subprocess():
    """asyncio.create_subprocess_exec raises NotImplementedError on non-Proactor event loops
    (uvicorn's). The ffmpeg paths must run ffmpeg via thread + sync subprocess instead."""
    import app.compose
    import app.providers.assembly.ffmpeg as asm
    import app.providers.video.ffmpeg_kenburns as kb
    for mod in (app.compose, asm, kb):
        src = inspect.getsource(mod)
        # match the CALL (with paren), not mentions in comments
        assert "create_subprocess_exec(" not in src and "create_subprocess_shell(" not in src, (
            f"{mod.__name__} calls an asyncio subprocess — breaks on non-Proactor Windows event "
            "loops; use asyncio.to_thread(subprocess.run) instead")


# ---- (2) reproduce the exact crash condition on a Selector loop ----

@pytest.mark.skipif(not has_ffmpeg(), reason="ffmpeg not installed")
def test_assemble_runs_on_selector_loop(mock_image):
    """Run the full assembly (with a transition -> forces the stitch ffmpeg call) on a
    SelectorEventLoop, where the old asyncio-subprocess code raised NotImplementedError. The
    thread-based fix must succeed on ANY loop."""
    project, shots = _project_with_keyframes(3)
    loop = asyncio.SelectorEventLoop()
    try:
        res = loop.run_until_complete(compose.assemble_episode(
            project, shots, voice=False, subtitles=True, music=True,
            grade="cinematic", transition="fade", preset="project_native"))
    finally:
        loop.close()
    asset = models.get("assets", res["asset_id"])
    data = get_provider(Capability.STORAGE).open(asset["path"])
    assert b"ftyp" in data[:64]
    assert asset["meta"]["transition"] == "fade" and asset["meta"]["grade"] == "cinematic"
    assert "video" in _probe_streams(res["asset_id"])


# ---- (3) feature-combo integration tests (real FFmpeg) ----

@pytest.mark.skipif(not has_ffmpeg(), reason="ffmpeg not installed")
def test_transition_compresses_timeline(mock_image):
    project, shots = _project_with_keyframes(4)
    hard = asyncio.run(compose.assemble_episode(
        project, shots, voice=False, subtitles=False, transition="none", preset="project_native"))
    soft = asyncio.run(compose.assemble_episode(
        project, shots, voice=False, subtitles=False, transition="fade", preset="project_native"))
    assert soft["duration_s"] < hard["duration_s"]   # crossfades overlap clips -> shorter


@pytest.mark.skipif(not has_ffmpeg(), reason="ffmpeg not installed")
def test_grade_produces_valid_mp4(mock_image):
    project, shots = _project_with_keyframes(2)
    res = asyncio.run(compose.assemble_episode(
        project, shots, voice=False, subtitles=False, grade="noir", preset="project_native"))
    assert models.get("assets", res["asset_id"])["meta"]["grade"] == "noir"
    assert "video" in _probe_streams(res["asset_id"])


@pytest.mark.skipif(not (has_ffmpeg() and _tts_ok()), reason="needs ffmpeg + a TTS provider")
def test_reported_duration_matches_file_lipsync_transition(mock_image):
    """Regression: lip-sync clips don't come out at the requested length, so the timeline/reported
    duration used to drift (e.g. meta 28.1 s vs a 20.5 s file). The reported duration must now
    match the actual encoded file."""
    project, shots = _project_with_keyframes(2)
    res = asyncio.run(compose.assemble_episode(
        project, shots, voice=True, lipsync=True, subtitles=False,
        transition="fade", preset="project_native"))
    asset = models.get("assets", res["asset_id"])
    actual = compose._probe_duration(settings.assets_dir() / asset["path"])
    assert actual > 0 and abs(res["duration_s"] - actual) < 0.35    # within rounding/xfade edges


@pytest.mark.skipif(not (has_ffmpeg() and _tts_ok()), reason="needs ffmpeg + a TTS provider")
def test_full_combo_with_lipsync_makes_valid_mp4(mock_image):
    """The user's exact scenario: lip-sync + music + grade + transition + word subtitles together
    -> a valid MP4 with BOTH a video and an audio stream."""
    project, shots = _project_with_keyframes(2)
    res = asyncio.run(compose.assemble_episode(
        project, shots, voice=True, lipsync=True, music=True, music_auto=True,
        subtitles=True, word_subtitles=True, smart_reframe=True,
        grade="cinematic", transition="fade", preset="project_native"))
    asset = models.get("assets", res["asset_id"])
    assert asset["meta"]["lipsync"] is True and asset["meta"]["music"] is True
    streams = _probe_streams(res["asset_id"])
    assert "video" in streams and "audio" in streams
