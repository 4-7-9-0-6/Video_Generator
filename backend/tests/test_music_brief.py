"""Lyrics -> music brief: mood/tempo/key picked from the words alone (free, local, rule-based)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import models, music_brief
from app.db import init_db
from app.jobs.worker import worker
from app.main import app


@pytest.fixture(autouse=True)
def _db():
    init_db()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(worker, "start", lambda: None)
    with TestClient(app) as c:
        yield c


def test_lullaby_lyrics_pick_slow_minor():
    b = music_brief.music_brief("Goodnight little star, close your eyes and dream\n"
                                "The moon is high, time to sleep")
    assert b["mood"] == "lullaby"
    assert b["tempo"] < 80                      # slow
    assert "minor" in b["description"]          # melody_notes -> minor scale


def test_playful_lyrics_pick_fast_major():
    b = music_brief.music_brief("Jump and play in the sun, we dance and laugh, hooray!")
    assert b["mood"] == "playful"
    assert b["tempo"] >= 120                     # upbeat (and ! nudges it higher)
    assert "minor" not in b["description"]


def test_french_lyrics_supported():
    b = music_brief.music_brief("Dors mon petit, la lune brille dans la nuit, fais de beaux rêves")
    assert b["mood"] == "lullaby"


def test_empty_lyrics_default_cheerful():
    b = music_brief.music_brief("")
    assert b["mood"] == "cheerful" and b["match_score"] == 0


def test_exclamation_nudges_tempo_but_caps():
    base = music_brief.music_brief("we play and run")["tempo"]
    hyped = music_brief.music_brief("we play and run!!!!!!!!!!")["tempo"]
    assert hyped > base and hyped - base <= 16


def test_music_brief_endpoint(client):
    pr = client.post("/projects", json={"name": "Lullaby"}).json()
    client.post(f"/projects/{pr['id']}/plan",
                json={"script": "The moon is bright tonight.\nClose your eyes and sleep, little star."})
    b = client.get(f"/projects/{pr['id']}/music-brief").json()
    assert b["mood"] == "lullaby" and "key" in b and "tempo" in b
    assert client.get("/projects/nope/music-brief").status_code == 404
