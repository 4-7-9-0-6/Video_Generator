"""Phase 3 — VoiceLab tests. Melody is fully offline; TTS runs real Piper if installed."""
from __future__ import annotations

import io
import wave

import pytest
from fastapi.testclient import TestClient

from app import voicelab
from app.db import init_db
from app.main import app
from app.jobs.worker import worker
from app.providers.base import Capability
from app.providers.registry import get_provider


@pytest.fixture(autouse=True)
def _db():
    init_db()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(worker, "start", lambda: None)
    with TestClient(app) as c:
        yield c


def test_wav_duration_helper():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 22050)  # 1 second
    assert voicelab.wav_duration(buf.getvalue()) == pytest.approx(1.0, abs=0.01)
    assert voicelab.wav_duration(b"not a wav") == 0.0


def test_voices_endpoint(client):
    body = client.get("/voice/voices").json()
    assert "en" in body["languages"] and "fr" in body["languages"]
    assert body["voices"]["fr"]


def test_melody_endpoint_offline(client):
    r = client.post("/voice/melody", json={
        "description": "upbeat C-major nursery melody", "tempo": 96, "duration_s": 6,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mime"] == "audio/midi"
    assert body["meta"]["scale"] == "major"
    midi = client.get(body["url"])
    assert midi.status_code == 200
    assert midi.content[:4] == b"MThd"           # valid Standard MIDI File


def test_tts_endpoint(client):
    if get_provider(Capability.TTS, required=False) is None:
        # voices not installed in this environment
        r = client.post("/voice/tts", json={"text": "hello", "language": "en"})
        assert r.status_code == 503
        pytest.skip("Piper TTS not available")
    r = client.post("/voice/tts", json={
        "text": "Hello, I am Mila!", "language": "en", "speed": 1.0,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mime"] == "audio/wav"
    assert body["duration_s"] > 0.3
    wav = client.get(body["url"])
    assert wav.status_code == 200 and wav.content[:4] == b"RIFF"


def test_tts_bad_language(client):
    assert client.post("/voice/tts", json={"text": "x", "language": "de"}).status_code == 422
