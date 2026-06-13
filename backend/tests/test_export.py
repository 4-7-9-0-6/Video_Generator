"""Phase 5 — Composer/Export tests. SRT + cost are offline; full assembly needs FFmpeg."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import compose, models, music_synth, voicelab
from app.compose import group_words_to_cues
from app.config import settings
from app.db import init_db
from app.ffmpeg_util import has_ffmpeg
from app.jobs.handlers import JobContext, handle_shot_keyframe
from app.main import app
from app.jobs.worker import worker
from app.providers import registry
from app.providers.base import Capability
from app.providers.music.symbolic import melody_notes
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


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(worker, "start", lambda: None)
    with TestClient(app) as c:
        yield c


def test_build_srt():
    srt = compose.build_srt([("Hello", 0.0, 2.0), ("World", 2.0, 4.5), ("", 4.5, 5.0)])
    assert "00:00:00,000 --> 00:00:02,000" in srt
    assert "Hello" in srt and "World" in srt
    assert srt.count("-->") == 2          # the empty line is skipped


def test_presets_and_cost(client):
    pr = client.post("/projects", json={"name": "Ep"}).json()
    presets = client.get("/export/presets").json()
    assert "youtube_1080p" in presets and presets["youtube_1080p"]["width"] == 1920
    cost = client.get(f"/projects/{pr['id']}/cost").json()
    assert cost["assets"] == 0 and cost["usd"] == 0.0


def test_export_requires_keyframes(client):
    pr = client.post("/projects", json={"name": "Ep"}).json()
    r = client.post(f"/projects/{pr['id']}/export", json={"preset": "youtube_1080p"})
    assert r.status_code == 409
    bad = client.post(f"/projects/{pr['id']}/export", json={"preset": "nope"})
    assert bad.status_code == 422


def test_music_synth_wav():
    notes, _info = melody_notes("cheerful nursery", duration_s=2.0, tempo=120)
    wav = music_synth.synth_wav(notes, total_s=2.0)
    assert wav[:4] == b"RIFF"
    assert voicelab.wav_duration(wav) == pytest.approx(2.0, abs=0.05)


def test_group_words_to_cues():
    words = [("Hello", 0.0, 0.4), ("there", 0.4, 0.8), ("Mila", 2.0, 2.4)]
    cues = group_words_to_cues(words, max_words=7, max_gap=0.7)
    assert len(cues) == 2                      # big gap before "Mila" splits the cue
    assert cues[0][0] == "Hello there"
    assert cues[1] == ("Mila", 2.0, 2.4)


def test_melody_audio_endpoint(client):
    r = client.post("/voice/melody",
                    json={"description": "upbeat C major", "duration_s": 2.0, "audio": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "audio_url" in body and body["audio_duration_s"] > 1.0
    wav = client.get(body["audio_url"])
    assert wav.status_code == 200 and wav.content[:4] == b"RIFF"


@pytest.mark.skipif(not has_ffmpeg(), reason="ffmpeg not installed")
def test_assemble_with_music_bed(mock_image):
    project = models.create_project("Ep", width=480, height=270, fps=12)
    shots = []
    for i in range(2):
        s = models.create_shot(project["id"], i, f"Line {i}", camera="static", duration_s=1.0)
        asyncio.run(handle_shot_keyframe(
            {"id": f"m{i}", "payload": {"shot_id": s["id"]}}, JobContext(f"m{i}")))
        shots.append(models.get("shots", s["id"]))
    res = asyncio.run(compose.assemble_episode(
        project, shots, voice=False, subtitles=False, music=True, preset="native"))
    assert res["music"] is True
    data = get_provider(Capability.STORAGE).open(models.get("assets", res["asset_id"])["path"])
    assert b"ftyp" in data[:32]


@pytest.mark.skipif(not has_ffmpeg(), reason="ffmpeg not installed")
def test_assemble_episode_makes_mp4(mock_image):
    project = models.create_project("Ep", width=480, height=270, fps=12)
    shots = []
    for i in range(2):
        s = models.create_shot(project["id"], i, f"Line {i}", camera="static",
                               background="park", duration_s=1.0)
        asyncio.run(handle_shot_keyframe(
            {"id": f"k{i}", "payload": {"shot_id": s["id"]}}, JobContext(f"k{i}")))
        shots.append(models.get("shots", s["id"]))

    res = asyncio.run(compose.assemble_episode(
        project, shots, voice=False, subtitles=True, preset="project_native"))
    asset = models.get("assets", res["asset_id"])
    assert asset["mime"] == "video/mp4"
    data = get_provider(Capability.STORAGE).open(asset["path"])
    assert b"ftyp" in data[:32]                # valid MP4 container
    assert res["duration_s"] >= 1.5
    assert "srt_asset_id" in res              # subtitles produced
