"""Rule-based character lore (no LLM) + anime style presets."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import foundry, lore, models
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


def test_archetype_detection():
    assert lore.generate_lore("A", "a brave knight with a sword and armor")["archetype"] == "warrior"
    assert lore.generate_lore("B", "a shadow assassin ninja")["archetype"] == "rogue"
    assert lore.generate_lore("C", "an arcane sorceress casting spells")["archetype"] == "mage"
    assert lore.generate_lore("D", "an android cyborg with robotic parts")["archetype"] == "machine"
    assert lore.generate_lore("E", "a kid who likes to wander")["archetype"] == "wanderer"


def test_no_substring_false_positives():
    # "air" must not match inside "hair"; "ai" must not match inside "kawaii"
    l1 = lore.generate_lore("K", "a warrior with blue hair")
    assert "wind" not in l1["elements"]
    l2 = lore.generate_lore("R", "a cute kawaii cat-girl")
    assert l2["archetype"] != "machine"


def test_theme_from_style_preset_and_elements():
    l = lore.generate_lore("Vex", "a dark assassin wielding cursed flame", style_preset="anime_dark")
    assert l["theme"] == "dark"
    assert "fire" in l["elements"] and "shadow" in l["elements"]


def test_lore_fields_and_name_in_backstory():
    l = lore.generate_lore("Mira", "a gentle ice mage")
    assert l["personality"].startswith("Mira") and "Mira" in l["backstory"]
    assert len(l["abilities"]) >= 2


def test_seed_determinism_and_variety():
    a = lore.generate_lore("X", "a fire warrior", seed=1)
    b = lore.generate_lore("X", "a fire warrior", seed=1)
    c = lore.generate_lore("X", "a fire warrior", seed=2)
    assert a == b and a != c


def test_anime_styles_registered():
    for s in ("anime_shonen", "anime_fantasy", "anime_cyberpunk", "anime_cute", "anime_dark"):
        assert s in foundry.STYLE_PRESETS


def test_styles_endpoint_lists_anime(client):
    styles = {s["id"] for s in client.get("/styles").json()}
    assert {"anime_shonen", "anime_cyberpunk", "anime_dark"} <= styles


def test_character_create_generates_lore_and_regenerate(client):
    pr = client.post("/projects", json={"name": "P"}).json()
    res = client.post("/characters", json={
        "project_id": pr["id"], "name": "Kael",
        "description": "a cyberpunk warrior with robotic armor", "style_preset": "anime_cyberpunk",
    })
    assert res.status_code == 200
    char = res.json()["character"]
    assert char["lore"]["archetype"] == "warrior" and char["lore"]["backstory"]
    # re-roll gives a fresh lore, persisted
    rolled = client.post(f"/characters/{char['id']}/lore").json()
    assert rolled["personality"] and rolled["abilities"]
    assert models.get("characters", char["id"])["lore"]["personality"] == rolled["personality"]
