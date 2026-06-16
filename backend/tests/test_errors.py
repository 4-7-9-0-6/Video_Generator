"""Friendly error messages: humanize() mapping + the jobs API exposing friendly_error."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import errors, models
from app.db import init_db
from app.jobs import queue
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _db():
    init_db()


def test_humanize_known_patterns():
    assert "FFmpeg" in errors.humanize("RuntimeError: ffmpeg not installed — run scripts/install_ffmpeg.py")
    assert "keyframes first" in errors.humanize("no shots have keyframes yet — render keyframes first")
    assert "GPU ran out" in errors.humanize("torch.OutOfMemoryError: CUDA out of memory. Tried to allocate ...")
    assert "bug" in errors.humanize("NotImplementedError: ").lower()
    assert "rate" in errors.humanize("HTTP 429 Too Many Requests").lower()
    assert "Kaggle" in errors.humanize("RuntimeError: kaggle kernels push failed: 401")


def test_humanize_strips_exception_prefix():
    assert errors.humanize("ValueError: project not found") == "project not found"


def test_humanize_empty_or_none():
    assert "try running it again" in errors.humanize("").lower()
    assert "try running it again" in errors.humanize(None).lower()


def test_job_endpoint_exposes_friendly_error():
    j = queue.enqueue("episode_assemble", {"x": 1})
    models.update("jobs", j["id"], {"status": "failed", "error": "RuntimeError: ffmpeg failed (1): boom"})
    r = client.get(f"/jobs/{j['id']}").json()
    assert r["status"] == "failed"
    assert "friendly_error" in r and "FFmpeg" in r["friendly_error"]


def test_succeeded_job_has_no_friendly_error():
    j = queue.enqueue("episode_assemble", {"x": 1})
    models.update("jobs", j["id"], {"status": "succeeded", "error": ""})
    r = client.get(f"/jobs/{j['id']}").json()
    assert "friendly_error" not in r
