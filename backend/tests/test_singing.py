"""Singing (SVS) — provider registration + pure music-helpers. The audio path needs Piper +
ffmpeg (not assumed in CI), so the heavy synth is exercised by the live demo, not unit tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import singing
from app.db import init_db
from app.jobs.worker import worker
from app.main import app
from app.providers import registry
from app.providers.base import Capability


@pytest.fixture(autouse=True)
def _db():
    init_db()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(worker, "start", lambda: None)
    with TestClient(app) as c:
        yield c


def test_svs_provider_registered_and_default():
    assert "tts_pitch" in registry._FACTORIES[Capability.SVS.value]
    from app.config import settings
    assert settings.providers["svs"] == "tts_pitch"


def test_sing_notes_follow_scale_near_voice():
    # melody transposes to the octave nearest the voice's median pitch (~C4=60)
    notes = singing._sing_notes(8, "C", center_midi=60.0, minor=False)
    assert all(48 <= n <= 84 for n in notes)
    # major scale degrees only (C D E F G A B relative to a C root)
    assert all((n % 12) in {0, 2, 4, 5, 7, 9, 11} for n in notes)


def test_sing_notes_minor_key():
    notes = singing._sing_notes(8, "A", center_midi=57.0, minor=True)
    # A natural-minor pitch classes: A B C D E F G = {9,11,0,2,4,5,7}
    assert all((n % 12) in {9, 11, 0, 2, 4, 5, 7} for n in notes)


def test_midi_hz_roundtrip():
    assert abs(singing._midi_to_hz(69) - 440.0) < 0.01
    assert abs(singing._hz_to_midi(440.0) - 69.0) < 0.01


def test_sing_endpoint_validates(client):
    # bad language -> 422 (doesn't require the audio stack)
    r = client.post("/voice/sing", json={"lyrics": "la la la", "language": "xx"})
    assert r.status_code == 422


def test_svs_in_provider_probe():
    rows = registry.probe_all()
    assert any(r["capability"] == "svs" and r["provider"] == "tts_pitch" for r in rows)


def test_edge_fade_ramps_the_boundaries():
    import numpy as np
    seg = np.ones(2000)
    faded = singing._edge_fade(seg, 22050, ms=3.0)
    assert faded[0] < 0.05 and faded[-1] < 0.05      # edges fade toward zero
    assert faded[1000] == pytest.approx(1.0)          # middle untouched


def test_has_rubberband_returns_bool():
    # must never crash, even if ffmpeg is absent — just reports capability
    assert isinstance(singing._has_rubberband(), bool)
