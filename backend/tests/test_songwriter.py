"""Prompt → song-video: songwriter parsing/normalize + the LLM providers + from-prompt flow.
Uses the deterministic mock LLM (PROVIDER_LLM=mock) — no key/network needed."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import models, songwriter
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


def test_extract_json_handles_fences_and_noise():
    assert songwriter._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert songwriter._extract_json('Sure! {"a": 2} hope that helps') == {"a": 2}


def test_normalize_coerces_bad_song():
    out = songwriter.normalize_song({"mood": "bogus", "lines": []}, fallback_title="My Topic")
    assert out["title"] == "My Topic" and out["mood"] == "playful"
    assert len(out["characters"]) >= 1 and len(out["lines"]) >= 1   # fallbacks fill in


def test_normalize_keeps_chorus_and_maps_characters():
    song = {
        "title": "T", "mood": "epic",
        "characters": [{"name": "Volt", "description": "a robot"}],
        "lines": [
            {"section": "chorus", "text": "Light the night", "characters": ["Volt", "Ghost"]},
            {"section": "weird", "text": "verse line", "characters": []},
        ],
    }
    out = songwriter.normalize_song(song)
    assert out["has_chorus"] is True
    assert out["lines"][0]["characters"] == ["Volt"]          # unknown "Ghost" dropped
    assert out["lines"][1]["section"] == "verse"               # bad section coerced


def test_write_song_via_mock_llm():
    song = asyncio.run(songwriter.write_song("a brave robot", style="anime_cyberpunk"))
    assert song["title"] == "Circuit Heart" and song["has_chorus"]
    assert {c["name"] for c in song["characters"]} == {"Volt", "Mira"}
    assert any(l["section"] == "chorus" for l in song["lines"])


def test_llm_providers_registered():
    fac = registry._FACTORIES[Capability.LLM.value]
    assert {"openrouter", "mock"} <= set(fac)
    assert fac["mock"]().availability().available is True
    # openrouter degrades gracefully — available iff a key is configured (no crash either way)
    assert isinstance(fac["openrouter"]().availability().available, bool)


def test_from_prompt_builds_a_full_project(client):
    res = client.post("/generate/from-prompt", json={
        "prompt": "a brave little robot who saves a neon city",
        "style_preset": "anime_cyberpunk", "scenes": 6, "render": True,
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["project"]["style_preset"] == "anime_cyberpunk"
    assert body["song"]["has_chorus"] and body["song"]["title"]
    assert len(body["characters"]) == 2 and len(body["character_jobs"]) == 2

    chars = client.get(f"/projects/{body['project']['id']}/characters").json()
    assert all(c["lore"]["personality"] for c in chars)            # each got lore
    shots = client.get(f"/projects/{body['project']['id']}/shots").json()
    assert len(shots) == len(body["song"]["lines"])
    assert any(s["camera"] == "bounce_in" for s in shots)         # chorus shots energetic
    # chorus shots reference a created character
    assert any(s["characters"] for s in shots)


def test_from_prompt_rejects_unknown_style(client):
    r = client.post("/generate/from-prompt", json={"prompt": "x", "style_preset": "nope"})
    assert r.status_code == 422
