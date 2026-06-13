"""Phase 5 — transcript-driven editing tests (spec §D)."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import init_db
from app.jobs.handlers import JobContext, handle_shot_keyframe
from app.main import app
from app.jobs.worker import worker
from app.providers import registry


@pytest.fixture(autouse=True)
def _db():
    init_db()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(worker, "start", lambda: None)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def mock_image():
    prev = settings.providers.get("image")
    settings.providers["image"] = "mock"
    registry._cache.clear()
    yield
    settings.providers["image"] = prev
    registry._cache.clear()


def _plan(client, script):
    pr = client.post("/projects", json={"name": "T"}).json()
    client.post(f"/projects/{pr['id']}/plan", json={"script": script})
    return pr


def test_transcript_view_and_timing(client):
    pr = _plan(client, "One.\nTwo!\nThree?")
    tr = client.get(f"/projects/{pr['id']}/transcript").json()
    assert tr["count"] == 3
    assert tr["shots"][0]["start_s"] == 0.0
    assert tr["shots"][1]["start_s"] == tr["shots"][0]["end_s"]   # contiguous timeline
    assert all(s["stale"] for s in tr["shots"])                   # no keyframes yet


def test_delete_line_reindexes(client):
    pr = _plan(client, "A.\nB.\nC.")
    shots = client.get(f"/projects/{pr['id']}/shots").json()
    mid = shots[1]["id"]
    r = client.delete(f"/shots/{mid}")
    assert r.status_code == 200 and r.json()["count"] == 2
    after = client.get(f"/projects/{pr['id']}/shots").json()
    assert [s["idx"] for s in after] == [0, 1]
    assert mid not in [s["id"] for s in after]
    assert [s["text"] for s in after] == ["A.", "C."]


def test_insert_line_at_position(client):
    pr = _plan(client, "A.\nB.")
    first = client.get(f"/projects/{pr['id']}/shots").json()[0]["id"]
    client.post(f"/projects/{pr['id']}/shots", json={"text": "inserted", "after_id": first})
    order = client.get(f"/projects/{pr['id']}/shots").json()
    assert [s["text"] for s in order] == ["A.", "inserted", "B."]
    assert [s["idx"] for s in order] == [0, 1, 2]


def test_reorder_lines(client):
    pr = _plan(client, "A.\nB.\nC.")
    ids = [s["id"] for s in client.get(f"/projects/{pr['id']}/shots").json()]
    r = client.post(f"/projects/{pr['id']}/transcript/reorder", json={"order": list(reversed(ids))})
    assert r.status_code == 200
    order = client.get(f"/projects/{pr['id']}/shots").json()
    assert [s["text"] for s in order] == ["C.", "B.", "A."]
    bad = client.post(f"/projects/{pr['id']}/transcript/reorder", json={"order": ids[:2]})
    assert bad.status_code == 422


def test_edit_line_makes_shot_stale(client, mock_image):
    pr = client.post("/projects", json={"name": "S"}).json()
    char = client.post("/characters", json={
        "project_id": pr["id"], "name": "Mila", "description": "a toddler"}).json()
    shot = client.post(f"/projects/{pr['id']}/shots", json={
        "text": "Mila waves", "characters": [char["character"]["id"]], "background": "park"}).json()

    assert client.get(f"/projects/{pr['id']}/transcript").json()["shots"][0]["stale"] is True
    asyncio.run(handle_shot_keyframe(
        {"id": "k", "payload": {"shot_id": shot["id"]}}, JobContext("k")))
    assert client.get(f"/projects/{pr['id']}/transcript").json()["shots"][0]["stale"] is False

    client.patch(f"/shots/{shot['id']}", json={"text": "Mila jumps high"})
    assert client.get(f"/projects/{pr['id']}/transcript").json()["shots"][0]["stale"] is True
