"""Depth-parallax video provider: warp math (no model needed) + a real animate (gated on model)."""
from __future__ import annotations

import asyncio
import io

import numpy as np
import pytest
from PIL import Image

from app.config import settings
from app.ffmpeg_util import has_ffmpeg
from app.providers import registry
from app.providers.base import Capability
from app.providers.video import depth_parallax as dp


def test_registered():
    assert "depth_parallax" in registry._FACTORIES[Capability.VIDEO.value]


def test_bilinear_identity_sampling():
    arr = (np.random.default_rng(0).random((8, 8, 3)) * 255).astype(np.float32)
    ys, xs = np.mgrid[0:8, 0:8].astype(np.float32)
    assert np.array_equal(dp._bilinear(arr, xs, ys), arr.astype(np.uint8))


def test_warp_frame_is_full_and_finite():
    rng = np.random.default_rng(1)
    rgb = (rng.random((32, 48, 3)) * 255).astype(np.float32)
    depth = rng.random((32, 48)).astype(np.float32)
    for t in (0.0, 0.25, 0.5, 0.9):
        frame = dp._warp_frame(rgb, depth, t, "static")
        assert frame.shape == (32, 48, 3) and frame.dtype == np.uint8
        assert np.isfinite(frame).all()        # backward-warp -> no holes/NaNs


def test_zero_depth_is_static_zoom_only():
    # with depth 0 everywhere, there's no parallax shift — just the overscan zoom (deterministic)
    rgb = (np.random.default_rng(2).random((20, 20, 3)) * 255).astype(np.float32)
    depth = np.zeros((20, 20), np.float32)
    a = dp._warp_frame(rgb, depth, 0.1, "static")
    b = dp._warp_frame(rgb, depth, 0.9, "static")
    assert np.array_equal(a, b)                # no depth -> frames identical regardless of t


def test_availability_reflects_model_presence():
    prov = registry._FACTORIES[Capability.VIDEO.value]["depth_parallax"]()
    av = prov.availability()
    if settings.depth_model.exists() and has_ffmpeg():
        assert av.available is True
    else:
        assert av.available is False and av.install_hint


@pytest.mark.skipif(not (has_ffmpeg() and settings.depth_model.exists()),
                    reason="needs ffmpeg + the depth model (scripts/download_depth_model.py)")
def test_animate_produces_valid_mp4():
    arr = np.zeros((180, 320, 3), np.uint8)
    arr[:40] = [40, 40, 120]                   # far sky
    arr[70:130, 120:200] = [210, 90, 90]       # near subject
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    prov = registry._FACTORIES[Capability.VIDEO.value]["depth_parallax"]()
    res = asyncio.run(prov.animate(buf.getvalue(), motion="static", duration_s=1.0, fps=10,
                                   width=320, height=180))
    assert res.mime == "video/mp4" and b"ftyp" in res.data[:64]
    assert res.meta["frames"] >= 8 and res.meta["provider"] == "depth_parallax"
