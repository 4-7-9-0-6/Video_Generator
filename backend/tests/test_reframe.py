"""Shorts smart auto-reframe — content-aware crop (pure numpy/PIL, offline)."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

from app import reframe


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_matching_aspect_is_noop():
    # 16:9 source, 16:9 target -> full frame
    img = Image.new("RGB", (1600, 900), (10, 10, 10))
    assert reframe.best_crop_box(img, 1920, 1080) == (0, 0, 1600, 900)


def test_16x9_to_9x16_returns_target_aspect():
    img = Image.new("RGB", (1600, 900), (20, 20, 20))
    box = reframe.best_crop_box(img, 1080, 1920)
    left, top, right, bottom = box
    cw, ch = right - left, bottom - top
    assert top == 0 and bottom == 900            # full height
    assert abs((cw / ch) - (1080 / 1920)) < 0.02  # crop is 9:16
    assert 0 <= left and right <= 1600


def test_crop_follows_the_subject():
    # busy detail (high edge energy) on the RIGHT third; reframe should crop toward it
    img = Image.new("RGB", (1600, 900), (15, 15, 15))
    d = ImageDraw.Draw(img)
    for x in range(1120, 1600, 6):               # dense vertical lines on the right
        d.line([(x, 0), (x, 900)], fill=(255, 255, 255), width=2)
    left, _, right, _ = reframe.best_crop_box(img, 1080, 1920)
    window_center = (left + right) / 2
    assert window_center > 1600 / 2              # picked the right (salient) side


def test_reframe_to_aspect_outputs_cropped_png():
    img = Image.new("RGB", (1600, 900), (30, 60, 90))
    out = reframe.reframe_to_aspect(_png(img), 1080, 1920)
    result = Image.open(io.BytesIO(out))
    assert result.format == "PNG"
    w, h = result.size
    assert abs((w / h) - (1080 / 1920)) < 0.02   # now vertical
