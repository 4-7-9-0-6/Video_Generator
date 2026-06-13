"""Phase 6 — onboarding template tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.jobs.worker import worker


@pytest.fixture(autouse=True)
def _db():
    init_db()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(worker, "start", lambda: None)
    with TestClient(app) as c:
        yield c


def test_list_templates(client):
    tpls = client.get("/templates").json()
    assert any(t["id"] == "nursery_rhyme" for t in tpls)


def test_instantiate_nursery_rhyme(client):
    r = client.post("/templates/nursery_rhyme/instantiate")
    assert r.status_code == 200, r.text
    body = r.json()
    project_id = body["project"]["id"]
    char = body["characters"][0]
    assert char["name"] == "Mila"

    # a character_sheets job was kicked off
    assert body["jobs"][0]["type"] == "character_sheets"

    # the rhyme planned into 6 shots, each naming Mila
    shots = client.get(f"/projects/{project_id}/shots").json()
    assert len(shots) == 6
    assert all(char["id"] in s["characters"] for s in shots)

    # cameras vary (first establishing, exclamation -> bounce)
    cameras = {s["camera"] for s in shots}
    assert "dolly_in" in cameras


def test_instantiate_unknown_404(client):
    assert client.post("/templates/nope/instantiate").status_code == 404
