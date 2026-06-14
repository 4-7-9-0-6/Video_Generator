"""Asset library endpoints: list (filter by kind) + delete (removes file + DB row)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import models
from app.config import settings
from app.db import init_db
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _db():
    init_db()


def _make_video() -> dict:
    rel = "test/clip.mp4"
    p = settings.assets_dir() / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"fakevideo")
    return models.create_asset(kind="video", path=rel, mime="video/mp4", meta={"prompt": "a robot"})


def test_list_filters_by_kind():
    v = _make_video()
    models.create_asset(kind="thumbnail", path="t/x.png", mime="image/png")
    vids = client.get("/assets?kind=video").json()
    assert any(a["id"] == v["id"] for a in vids)
    assert all(a["kind"] == "video" for a in vids)


def test_delete_removes_file_and_row():
    v = _make_video()
    path = settings.assets_dir() / v["path"]
    assert path.exists()
    r = client.delete(f"/assets/{v['id']}")
    assert r.status_code == 200 and r.json()["deleted"] == v["id"]
    assert not path.exists()
    assert models.get("assets", v["id"]) is None


def test_delete_missing_404():
    assert client.delete("/assets/does-not-exist").status_code == 404
