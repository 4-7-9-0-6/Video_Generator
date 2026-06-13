"""Phase 2 — Character Foundry tests. Fully offline via the deterministic mock provider."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import foundry, models
from app.config import settings
from app.db import init_db
from app.jobs.handlers import JobContext, handle_character_sheets
from app.main import app
from app.jobs.worker import worker
from app.providers import registry


@pytest.fixture(autouse=True)
def _db():
    init_db()


@pytest.fixture()
def mock_image():
    """Force PROVIDER_IMAGE=mock for the duration of a test."""
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


# ---------- domain logic ----------

def test_prompt_reuse_injection():
    char = {
        "description": "a cheerful toddler",
        "style_preset": "3d_toddler_original",
        "palette": ["#FFD23F", "#3A86FF"],
        "style_tokens": ["soft lighting"],
        "edits": [{"instruction": "wearing a green t-shirt"}],
    }
    prompt = foundry.build_character_prompt(char, pose="waving hello", framing="full body")
    assert "#FFD23F" in prompt and "#3A86FF" in prompt
    assert "soft lighting" in prompt
    assert "waving hello" in prompt
    assert "green t-shirt" in prompt          # edit injected
    assert foundry.effective_description(char).endswith("wearing a green t-shirt")


def test_identity_seed_is_stable():
    assert foundry.identity_seed("chr_abc") == foundry.identity_seed("chr_abc")
    assert foundry.identity_seed("chr_abc") != foundry.identity_seed("chr_xyz")


# ---------- full pipeline ----------

def test_character_sheets_end_to_end(mock_image):
    project = models.create_project("Nursery")
    char = models.create_character(
        project["id"], "Mila", "a cheerful toddler with a yellow star shirt",
        palette=["#FFD23F", "#3A86FF"],
    )
    job = {"id": "job_test", "payload": {"character_id": char["id"]}}
    result = asyncio.run(handle_character_sheets(job, JobContext("job_test")))

    c = models.get("characters", char["id"])
    assert len(c["sheets"]["turnaround"]) == 4
    assert set(c["sheets"]["expressions"]) == {"happy", "sad", "surprised", "sleepy", "singing"}
    assert set(c["sheets"]["poses"]) == {
        "standing", "sitting", "jumping", "waving", "holding_object"}
    assert c["embedding_id"]

    rep = c["consistency"]
    assert rep["passed"] is True                     # mock keeps identity -> above threshold
    assert rep["min_score"] >= rep["threshold"]
    assert len(rep["scores"]) == 13                  # 14 items minus the identity reference
    assert result["consistency"]["passed"] is True

    assets = models.list_where("assets", "project_id = ?", (project["id"],))
    assert len(assets) == 14                          # one image per sheet item


def test_partial_sheet_selection(mock_image):
    project = models.create_project("P")
    char = models.create_character(project["id"], "Bo", "a small round robot")
    job = {"id": "j2", "payload": {"character_id": char["id"], "sheets": ["turnaround"]}}
    asyncio.run(handle_character_sheets(job, JobContext("j2")))
    c = models.get("characters", char["id"])
    assert len(c["sheets"]["turnaround"]) == 4
    assert "expressions" not in c["sheets"]


# ---------- API ----------

def test_styles_and_sheets_endpoints(client):
    styles = client.get("/styles").json()
    assert {s["id"] for s in styles} >= {"3d_toddler_original", "2d_flat", "claymation"}
    sheets = client.get("/sheets").json()
    assert "singing" in sheets["expressions"]
    assert "jumping" in sheets["poses"]


def test_instruction_edit_records_and_reenqueues(client):
    pr = client.post("/projects", json={"name": "P"}).json()
    created = client.post("/characters", json={
        "project_id": pr["id"], "name": "Mila", "description": "an original toddler",
    }).json()
    cid = created["character"]["id"]

    edit = client.post(f"/characters/{cid}/edit",
                       json={"instruction": "change her t-shirt to green"})
    assert edit.status_code == 200, edit.text
    body = edit.json()
    assert body["applied"]["instruction"] == "change her t-shirt to green"
    assert len(body["character"]["edits"]) == 1
    assert "job" in body                              # regeneration enqueued

    cons = client.get(f"/characters/{cid}/consistency")
    assert cons.status_code == 200                    # report endpoint exists pre-generation


def test_edit_rejects_protected_brand(client):
    pr = client.post("/projects", json={"name": "P"}).json()
    created = client.post("/characters", json={
        "project_id": pr["id"], "name": "Mila", "description": "an original toddler",
    }).json()
    cid = created["character"]["id"]
    bad = client.post(f"/characters/{cid}/edit",
                      json={"instruction": "make her look like Elsa from Frozen"})
    assert bad.status_code == 422
