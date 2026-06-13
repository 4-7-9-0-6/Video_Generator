"""YouTube thumbnail proposals — compositor is pure PIL; the job uses the mock provider."""
from __future__ import annotations

import asyncio
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import models, thumbnail
from app.config import settings
from app.db import init_db
from app.jobs.handlers import JobContext, handle_thumbnails
from app.jobs.worker import worker
from app.main import app
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


def _hero(w=1280, h=720) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 80, 160)).save(buf, "PNG")
    return buf.getvalue()


def test_compose_is_1280x720_png():
    png = thumbnail.compose(_hero(), "Mila and the Magic Star", subject_side="right",
                            accent=(255, 209, 0), text_side="left")
    img = Image.open(io.BytesIO(png))
    assert img.size == (1280, 720) and img.format == "PNG"


def test_compose_covers_odd_aspect_hero():
    # a non-16:9 hero must be cover-cropped to exactly 1280x720 (no letterbox)
    png = thumbnail.compose(_hero(800, 1200), "Tall Hero Title", text_side="right")
    assert Image.open(io.BytesIO(png)).size == (1280, 720)


def test_build_variants_are_distinct_and_locked():
    project = {"name": "Mila Sings", "style_preset": "3d_toddler_original"}
    char = {"id": "chr_abc", "style_preset": "3d_toddler_original",
            "description": "a cheerful toddler with pigtails",
            "palette": ["#FFD100", "#2A7FFF"], "negative_prompt": "blurry"}
    vs = thumbnail.build_variants(project, char, "Mila Sings", 3)
    assert len(vs) == 3
    assert {v["subject_side"] for v in vs} == {"left", "right"}      # alternates
    assert len({v["seed"] for v in vs}) == 3                          # distinct seeds
    assert len({v["emotion"] for v in vs}) == 3                       # distinct emotions
    assert all("cheerful toddler" in v["prompt"] for v in vs)         # identity locked
    # accent rotates through the character palette
    assert vs[0]["accent"] == (255, 209, 0) and vs[1]["accent"] == (42, 127, 255)


def test_title_defaults_to_project_name():
    assert thumbnail.default_title({"name": "My Show"}) == "My Show"
    assert thumbnail.default_title({}) == "My Episode"


def test_thumbnail_job_produces_assets(mock_image):
    project = models.create_project("Mila Sings")
    mila = models.create_character(project["id"], "Mila", "a cheerful toddler",
                                   palette=["#FFD23F"])
    res = asyncio.run(handle_thumbnails(
        {"id": "t", "payload": {"project_id": project["id"], "count": 2,
                                "title": "Mila Sings", "character_id": mila["id"]}},
        JobContext("t")))
    assert res["count"] == 2 and len(res["thumbnails"]) == 2
    for t in res["thumbnails"]:
        asset = models.get("assets", t["asset_id"])
        assert asset["kind"] == "thumbnail" and asset["mime"] == "image/png"
        data = (settings.assets_dir() / asset["path"]).read_bytes()
        assert Image.open(io.BytesIO(data)).size == (1280, 720)


def test_thumbnail_api_enqueues(client):
    pr = client.post("/projects", json={"name": "P"}).json()
    job = client.post(f"/projects/{pr['id']}/thumbnails", json={"count": 3})
    assert job.status_code == 200
    assert job.json()["type"] == "thumbnails" and job.json()["status"] == "queued"
    assert client.get(f"/projects/{pr['id']}/thumbnails").json() == []
    assert client.post("/projects/nope/thumbnails", json={}).status_code == 404
