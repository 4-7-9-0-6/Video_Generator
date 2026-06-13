"""Offline smoke tests — no GPU, no API keys, no network (except the marked optional test).

Verifies the Phase-1 foundation actually works: DB, storage, consistency, music,
safety guard, registry probing, and the job queue.
"""
from __future__ import annotations

import asyncio
import io

import httpx
import numpy as np
import pytest
from PIL import Image

from app.db import init_db
from app import models
from app.jobs import queue
from app.providers.registry import probe_all, get_provider
from app.providers.base import Capability
from app.providers.image.pollinations import PollinationsRateLimited
from app.providers.storage.local_fs import LocalFSStorageProvider
from app.providers.consistency.phash import PHashConsistencyProvider
from app.providers.music.symbolic import SymbolicMusicProvider
from app import safety


def _png(seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(128, 128, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _db():
    init_db()


def test_db_and_models():
    project = models.create_project("Test", language="en")
    assert project["id"].startswith("prj_")
    char = models.create_character(project["id"], "Mila", "a cheerful toddler")
    assert char["project_id"] == project["id"]
    assert models.get("characters", char["id"])["name"] == "Mila"


def test_storage_roundtrip():
    store = LocalFSStorageProvider()
    assert store.availability().available
    rel = store.put(b"hello", name="a.txt", subdir="unit")
    assert store.open(rel) == b"hello"
    assert store.abs_path(rel).endswith("a.txt")


def test_phash_consistency():
    cons = PHashConsistencyProvider()
    assert cons.availability().available
    a, b = _png(1), _png(2)
    assert cons.similarity(a, a) == pytest.approx(1.0)
    assert cons.similarity(a, b) < 1.0
    space, dim, vec = cons.embed(a)
    assert space == "phash" and dim > 0 and len(vec) == dim


def test_symbolic_music_is_valid_midi():
    music = SymbolicMusicProvider()
    res = asyncio.run(music.compose("upbeat C-major nursery melody", duration_s=4, tempo=100))
    assert res.mime == "audio/midi"
    assert res.data[:4] == b"MThd"          # valid Standard MIDI File header
    assert res.meta["scale"] == "major"


def test_safety_ip_guard():
    assert not safety.check_ip("Elsa", "from Frozen").ok
    assert safety.check_ip("Mila", "a cheerful original toddler").ok
    assert not safety.check_safe_mode("a scene with a knife").ok


def test_registry_probe_never_crashes():
    probes = probe_all()
    by_name = {(p["capability"], p["provider"]): p for p in probes}
    assert by_name[("storage", "local_fs")]["available"]
    assert by_name[("consistency", "phash")]["available"]
    assert by_name[("music", "symbolic")]["available"]
    # image provider resolves (availability is network-optimistic)
    assert get_provider(Capability.IMAGE).info.name == "pollinations"


def test_job_queue_enqueue_and_claim():
    project = models.create_project("Q")
    job = queue.enqueue("character_turnaround", {"character_id": "x"},
                        project_id=project["id"])
    assert job["status"] == "queued"
    claimed = queue.claim_next()
    assert claimed is not None and claimed["status"] == "running"
    assert claimed["attempts"] == 1
    queue.succeed(claimed["id"], {"ok": True})
    assert queue.get(claimed["id"])["status"] == "succeeded"


@pytest.mark.parametrize("provider_name", ["pollinations"])
def test_pollinations_optional_network(provider_name):
    """Real free image generation. Skips automatically if offline."""
    image = get_provider(Capability.IMAGE)
    try:
        res = asyncio.run(image.generate("a tiny red star icon, flat", width=128, height=128))
    except (httpx.HTTPError, httpx.TimeoutException, OSError, PollinationsRateLimited) as e:
        pytest.skip(f"network unavailable or rate-limited: {e}")
    assert len(res.data) > 100
    # confirm it's a real image
    Image.open(io.BytesIO(res.data)).verify()
