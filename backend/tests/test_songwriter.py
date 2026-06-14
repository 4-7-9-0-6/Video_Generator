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


# ---- lyrics → music video ----

def test_cast_keeps_exact_words_and_detects_chorus():
    lines = ["Splish splash bubbles", "Splish splash bubbles", "Wash my little toes"]
    song = songwriter.cast_song_from_lyrics(lines, {})   # no LLM data -> fallback cast
    assert [ln["text"] for ln in song["lines"]] == lines    # words preserved verbatim
    assert song["lines"][0]["section"] == "chorus"          # repeated line -> chorus
    assert song["lines"][2]["section"] == "verse"
    assert song["characters"]                                # at least a fallback character


def test_cast_uses_llm_character_and_background():
    data = {"title": "Bath Time", "mood": "playful",
            "characters": [{"name": "Bubbles", "description": "a cheerful blue toddler"}],
            "lines": [{"n": 1, "section": "verse", "characters": ["Bubbles"], "background": "a sunny bathroom"}]}
    song = songwriter.cast_song_from_lyrics(["Wash my toes"], data)
    assert song["lines"][0]["text"] == "Wash my toes"        # unchanged
    assert song["lines"][0]["characters"] == ["Bubbles"]
    assert song["lines"][0]["background"] == "a sunny bathroom"
    assert song["characters"][0]["name"] == "Bubbles"


def test_cast_from_lyrics_via_mock_llm():
    song = asyncio.run(songwriter.cast_from_lyrics("la la la\nla la la\nshine bright"))
    assert [ln["text"] for ln in song["lines"]] == ["la la la", "la la la", "shine bright"]


def test_from_lyrics_builds_project_keeping_words(client):
    lyrics = "Splish splash bubbles\nSplish splash bubbles\nWash my little toes"
    r = client.post("/generate/from-lyrics", json={"lyrics": lyrics, "style_preset": "anime_cute", "render": False})
    assert r.status_code == 200
    body = r.json()
    shots = client.get(f"/projects/{body['project']['id']}/shots").json()
    assert [s["text"] for s in shots] == ["Splish splash bubbles", "Splish splash bubbles", "Wash my little toes"]


def test_from_lyrics_rejects_empty(client):
    r = client.post("/generate/from-lyrics", json={"lyrics": "   "})
    assert r.status_code == 422
