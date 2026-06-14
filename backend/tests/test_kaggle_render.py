"""App-driven Kaggle GPU render: kernel generation, availability detection, status parsing,
and the endpoint's guard rails. No network / no real Kaggle calls — the CLI is monkeypatched."""
from __future__ import annotations

import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from app import kaggle_render
from app.config import settings
from app.db import init_db
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _db():
    init_db()


def test_kernel_source_bakes_prompt_style_and_keys():
    src = kaggle_render._render_kernel_source("a brave robot", "anime_cyberpunk", 6)
    assert "a brave robot" in src and "anime_cyberpunk" in src
    # the real (frozen) settings keys are interpolated verbatim as Python literals
    assert f'env["OPENROUTER_API_KEY"]    = {settings.openrouter_api_key!r}' in src
    assert f'env["CLOUDFLARE_ACCOUNT_ID"] = {settings.cloudflare_account_id!r}' in src
    assert "scripts/gpu_render.py" in src and "ACE-Step" in src
    assert "PROVIDER_VIDEO" in src and "GPU_OFFLOAD" in src
    compile(src, "<kernel>", "exec")            # the generated script must be valid Python


def test_kernel_source_with_lyrics_uses_lyrics_file():
    src = kaggle_render._render_kernel_source("", "anime_cute", 6, lyrics="Splish splash\nbubbles")
    assert "Splish splash" in src and "--lyrics-file" in src and "LYRICS" in src
    compile(src, "<kernel>", "exec")


def test_write_kernel_dir_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(kaggle_render, "kernel_slug", lambda: "tester/toonforge-render")
    kaggle_render._write_kernel_dir(tmp_path, "p", "fantasy", 4)
    meta = json.loads((tmp_path / "kernel-metadata.json").read_text())
    assert meta["id"] == "tester/toonforge-render"
    assert meta["enable_gpu"] is True and meta["enable_internet"] is True
    assert meta["is_private"] is True and meta["code_file"] == "render_kernel.py"
    assert (tmp_path / "render_kernel.py").exists()


def test_availability_no_cli(monkeypatch):
    monkeypatch.setattr(kaggle_render, "_kaggle_cmd", lambda: None)
    ok, hint = kaggle_render.availability()
    assert ok is False and "pip install kaggle" in hint


def test_availability_no_creds(monkeypatch):
    monkeypatch.setattr(kaggle_render, "_kaggle_cmd", lambda: ["kaggle"])
    monkeypatch.setattr(kaggle_render, "_credentials", lambda: None)
    ok, hint = kaggle_render.availability()
    assert ok is False and "token" in hint.lower()


def test_availability_ready(monkeypatch):
    monkeypatch.setattr(kaggle_render, "_kaggle_cmd", lambda: ["kaggle"])
    monkeypatch.setattr(kaggle_render, "_credentials", lambda: ("tester", "key"))
    ok, hint = kaggle_render.availability()
    assert ok is True and hint == "ready"


def test_status_parsing(monkeypatch):
    monkeypatch.setattr(kaggle_render, "_run",
                        lambda a, timeout=60: subprocess.CompletedProcess(a, 0, 'has status "complete"', ""))
    st = kaggle_render.status("tester/toonforge-render")
    assert st.state == "complete" and st.ok and st.done

    monkeypatch.setattr(kaggle_render, "_run",
                        lambda a, timeout=60: subprocess.CompletedProcess(a, 0, 'status "running"', ""))
    st = kaggle_render.status("x")
    assert st.state == "running" and not st.done


def test_endpoint_503_when_unavailable(monkeypatch):
    monkeypatch.setattr("app.routers.generate.kaggle_render.availability",
                        lambda: (False, "No Kaggle API token."))
    r = client.post("/generate/gpu-video", json={"prompt": "a brave robot"})
    assert r.status_code == 503 and "token" in r.json()["detail"].lower()


def test_endpoint_enqueues_when_available(monkeypatch):
    monkeypatch.setattr("app.routers.generate.kaggle_render.availability", lambda: (True, "ready"))
    monkeypatch.setattr("app.routers.generate.kaggle_render.kernel_slug",
                        lambda: "tester/toonforge-render")
    r = client.post("/generate/gpu-video", json={"prompt": "a brave robot", "scenes": 4})
    assert r.status_code == 200
    body = r.json()
    assert body["job"]["type"] == "gpu_video" and body["job"]["status"] == "queued"
    assert body["kernel"] == "tester/toonforge-render"


def test_endpoint_rejects_unknown_style(monkeypatch):
    monkeypatch.setattr("app.routers.generate.kaggle_render.availability", lambda: (True, "ready"))
    r = client.post("/generate/gpu-video", json={"prompt": "x", "style_preset": "nope"})
    assert r.status_code == 422
