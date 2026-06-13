"""Phase 4 — Scene Engine tests. Planner is pure logic; keyframe pipeline uses the mock provider."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import models, scene
from app.config import settings
from app.db import init_db
from app.jobs.handlers import JobContext, handle_character_sheets, handle_shot_keyframe
from app.main import app
from app.jobs.worker import worker
from app.providers import registry


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


def test_plan_script_segmentation():
    project = models.create_project("P")
    mila = models.create_character(project["id"], "Mila", "a toddler")
    bo = models.create_character(project["id"], "Bo", "a robot")
    script = "Mila wakes up!\nBo says hello to Mila.\nWhere is the sun?"
    shots = scene.plan_script(script, [mila, bo])
    assert [s["idx"] for s in shots] == [0, 1, 2]
    assert shots[0]["camera"] == "dolly_in"          # establishing
    assert mila["id"] in shots[0]["characters"]
    assert set(shots[1]["characters"]) == {mila["id"], bo["id"]}
    assert shots[2]["camera"] == "static"            # question -> steady
    assert all(2.0 <= s["duration_s"] <= 10.0 for s in shots)


def test_shot_prompt_locks_identity():
    project = models.create_project("P")
    mila = models.create_character(project["id"], "Mila", "a toddler with pigtails",
                                   palette=["#FFD23F"])
    shot = {"idx": 0, "text": "Mila waves", "characters": [mila["id"]],
            "camera": "dolly_in", "background": "sunny park"}
    p = scene.build_shot_prompt(shot, {mila["id"]: mila}, project)
    assert "Mila" in p and "#FFD23F" in p and "sunny park" in p and "dolly-in" in p


def test_keyframe_job_with_cache(mock_image):
    project = models.create_project("P")
    mila = models.create_character(project["id"], "Mila", "a cheerful toddler",
                                   palette=["#FFD23F"])
    asyncio.run(handle_character_sheets(
        {"id": "j", "payload": {"character_id": mila["id"], "sheets": ["turnaround"]}},
        JobContext("j")))
    shot = models.create_shot(project["id"], 0, "Mila waves",
                              characters=[mila["id"]], camera="dolly_in", background="park")

    res = asyncio.run(handle_shot_keyframe(
        {"id": "k", "payload": {"shot_id": shot["id"]}}, JobContext("k")))
    assert res["cached"] is False
    saved = models.get("shots", shot["id"])
    assert saved["keyframe_id"] and saved["status"] == "keyframed" and saved["prompt_hash"]
    asset = models.get("assets", saved["keyframe_id"])
    assert asset["meta"]["character_drift"] is not None   # checked vs the turnaround sheet

    # unchanged shot -> render cache hit, no regeneration
    res2 = asyncio.run(handle_shot_keyframe(
        {"id": "k2", "payload": {"shot_id": shot["id"]}}, JobContext("k2")))
    assert res2["cached"] is True


def test_continuity_seeding(mock_image):
    project = models.create_project("P")
    s0 = models.create_shot(project["id"], 0, "scene one", background="park")
    s1 = models.create_shot(project["id"], 1, "scene two", background="park")
    asyncio.run(handle_shot_keyframe({"id": "a", "payload": {"shot_id": s0["id"]}}, JobContext("a")))
    asyncio.run(handle_shot_keyframe({"id": "b", "payload": {"shot_id": s1["id"]}}, JobContext("b")))
    kf1 = models.get("assets", models.get("shots", s1["id"])["keyframe_id"])
    assert kf1["meta"]["continuity_ref"] is True          # seeded from previous shot


def test_scene_api(client):
    pr = client.post("/projects", json={"name": "P"}).json()
    shots = client.post(f"/projects/{pr['id']}/plan",
                        json={"script": "Line one.\nLine two!", "default_background": "park"}).json()
    assert len(shots) == 2
    got = client.get(f"/projects/{pr['id']}/shots").json()
    assert len(got) == 2 and got[0]["background"] == "park"
    assert client.patch(f"/shots/{got[0]['id']}", json={"camera": "nope"}).status_code == 422
    ok = client.patch(f"/shots/{got[0]['id']}", json={"duration_s": 5.0})
    assert ok.status_code == 200 and ok.json()["duration_s"] == 5.0
    job = client.post(f"/shots/{got[0]['id']}/keyframe").json()
    assert job["type"] == "shot_keyframe" and job["status"] == "queued"
