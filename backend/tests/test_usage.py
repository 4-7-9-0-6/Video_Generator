"""Free-tier usage guard: counts derived from assets/jobs, budgets honored, warning thresholds."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import models, usage
from app.config import settings
from app.db import init_db
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _db():
    init_db()


def test_counts_cloudflare_images_and_kaggle_renders():
    base_cf = usage.cloudflare_images_today()       # DB is shared across tests — assert deltas
    base_k = usage.kaggle_renders_this_week()
    models.create_asset(kind="keyframe", path="a.png", mime="image/png", provider="cloudflare")
    models.create_asset(kind="keyframe", path="b.png", mime="image/png", provider="cloudflare:flux")
    models.create_asset(kind="keyframe", path="c.png", mime="image/png", provider="sdcpp")  # not counted
    from app.jobs import queue
    queue.enqueue("gpu_video", {"prompt": "x"})
    assert usage.cloudflare_images_today() == base_cf + 2
    assert usage.kaggle_renders_this_week() == base_k + 1


def test_summary_shape_and_remaining():
    s = usage.summary()
    assert s["cloudflare"]["daily_budget"] == settings.cloudflare_daily_image_budget
    assert s["kaggle"]["weekly_budget_minutes"] == settings.kaggle_weekly_gpu_minutes
    assert s["kaggle"]["est_renders_left"] >= 0
    assert "near_limit" in s["kaggle"] and "over_limit" in s["kaggle"]


def test_kaggle_warning_when_over(monkeypatch):
    # settings is frozen; instead simulate many renders this week so the estimate exceeds budget
    monkeypatch.setattr(usage, "kaggle_renders_this_week", lambda: 999)
    assert "free Kaggle GPU" in usage.kaggle_warning()


def test_usage_endpoint():
    r = client.get("/usage")
    assert r.status_code == 200
    assert "cloudflare" in r.json() and "kaggle" in r.json()
