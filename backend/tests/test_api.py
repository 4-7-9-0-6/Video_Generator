"""API integration tests via FastAPI TestClient — offline and fast.

The background worker is stubbed off so these tests exercise only the HTTP layer and
job *enqueue* (worker execution depends on network and is covered separately).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.jobs.worker import worker


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(worker, "start", lambda: None)  # don't run jobs during API tests
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "en" in r.json()["languages"]


def test_providers_report(client):
    r = client.get("/providers")
    assert r.status_code == 200
    ready = {(p["capability"], p["provider"]) for p in r.json()["ready"]}
    assert ("storage", "local_fs") in ready
    assert ("consistency", "phash") in ready
    assert ("music", "symbolic") in ready


def test_project_and_character_flow(client):
    pr = client.post("/projects", json={"name": "Nursery", "language": "en"})
    assert pr.status_code == 200, pr.text
    project_id = pr.json()["id"]

    # IP guard blocks protected names
    blocked = client.post("/characters", json={
        "project_id": project_id, "name": "Elsa", "description": "from Frozen",
    })
    assert blocked.status_code == 422

    # valid original character enqueues a turnaround job
    ok = client.post("/characters", json={
        "project_id": project_id, "name": "Mila",
        "description": "a cheerful original toddler with curly pigtails and a yellow star shirt",
        "palette": ["#FFD23F", "#3A86FF"],
    })
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["character"]["name"] == "Mila"
    job_id = body["job"]["id"]

    jr = client.get(f"/jobs/{job_id}")
    assert jr.status_code == 200
    assert jr.json()["type"] == "character_sheets"
    assert jr.json()["status"] == "queued"


def test_unknown_project_404(client):
    assert client.get("/projects/prj_does_not_exist").status_code == 404
