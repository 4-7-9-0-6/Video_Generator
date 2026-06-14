"""Social/marketing pack: heuristic fallbacks always produce a valid pack + virality score,
and the endpoint derives it from a project. Uses PROVIDER_LLM=mock (no network)."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import models, social_pack
from app.db import init_db
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _db():
    init_db()


def test_normalize_fills_fallbacks_when_empty():
    pack = social_pack.normalize_pack({}, title="Neon Pulse", lyrics="shine little hero\nshine little hero",
                                      platform="youtube")
    assert pack["titles"] and pack["description"]
    assert len(pack["hashtags"]) >= 5
    assert pack["hashtag_string"].startswith("#")
    assert 1 <= pack["virality"]["score"] <= 100


def test_virality_rewards_repeated_hook_and_number():
    no_hook = social_pack.virality_score("Plain title", "a\nb\nc", ["music"])["score"]
    with_hook = social_pack.virality_score("3 Reasons 🎵", "hook line\nhook line\nverse", ["shorts", "music"])["score"]
    assert with_hook > no_hook


def test_generate_pack_runs_with_mock_llm():
    pack = asyncio.run(social_pack.generate_pack("Neon Pulse", "shine\nshine", style="anime", platform="tiktok"))
    assert pack["platform"] == "tiktok"
    assert pack["titles"] and pack["caption"] and pack["virality"]["grade"]


def test_endpoint_returns_pack():
    p = models.create_project("Neon Pulse")
    models.create_shot(p["id"], 0, "shine little hero light the night")
    models.create_shot(p["id"], 1, "shine little hero light the night")
    r = client.post(f"/projects/{p['id']}/social-pack?platform=youtube")
    assert r.status_code == 200
    body = r.json()
    assert body["titles"] and body["hashtags"] and "score" in body["virality"]
