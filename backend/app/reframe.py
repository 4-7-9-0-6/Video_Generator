"""Content-aware reframing (spec §6 / Phase 6 "Shorts auto-reframe").

Turning a 16:9 keyframe into a 9:16 Short by `scale=`-ing it stretches the character.
Instead we pick the most *salient* crop window of the target aspect and cut to it, so the
subject stays framed. Saliency = gradient energy (numpy) + a mild center bias — no OpenCV,
no torch, no GPU; just Pillow + numpy (both already installed, Python 3.14-safe).
"""
from __future__ import annotations

import io

_ASPECT_TOL = 0.02  # within 2% of target aspect -> no crop needed


def _gray(img):
    import numpy as np
    return np.asarray(img.convert("L"), dtype="float64")


def _energy(gray):
    """Per-pixel edge energy (|dx| + |dy|), same shape as the input."""
    import numpy as np
    ex = np.zeros_like(gray)
    ey = np.zeros_like(gray)
    ex[:, :-1] = np.abs(np.diff(gray, axis=1))
    ey[:-1, :] = np.abs(np.diff(gray, axis=0))
    return ex + ey


def _best_window(weight, length: int, win: int, *, center_bias: float = 0.3) -> int:
    """Start index of the `win`-wide window over a 1-D `weight` array that maximizes
    energy, gently biased toward the center so flat images crop centrally."""
    import numpy as np
    n = len(weight)
    if win >= n:
        return 0
    cum = np.concatenate([[0.0], np.cumsum(weight)])
    sums = cum[win:] - cum[: n - win + 1]          # window sums, len n-win+1
    centers = np.arange(len(sums)) + win / 2.0
    bias = 1.0 - center_bias * np.abs(centers - n / 2.0) / (n / 2.0)
    return int(np.argmax(sums * bias))


def best_crop_box(img, target_w: int, target_h: int) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) for the salient crop of the given target aspect.
    Returns the full frame when the source already matches the target aspect."""
    W, H = img.size
    src_aspect = W / H
    tgt_aspect = target_w / target_h
    if abs(src_aspect - tgt_aspect) / tgt_aspect <= _ASPECT_TOL:
        return (0, 0, W, H)

    energy = _energy(_gray(img))
    if tgt_aspect < src_aspect:
        # target is narrower -> crop width (e.g. 16:9 -> 9:16)
        cw = max(1, min(W, round(H * tgt_aspect)))
        x = _best_window(energy.sum(axis=0), W, cw)
        return (x, 0, x + cw, H)
    # target is wider -> crop height
    ch = max(1, min(H, round(W / tgt_aspect)))
    y = _best_window(energy.sum(axis=1), H, ch)
    return (0, y, W, y + ch)


def reframe_to_aspect(img_bytes: bytes, target_w: int, target_h: int) -> bytes:
    """Crop the image to the target aspect, subject-centered, and return PNG bytes.
    A no-op (re-encode) when the source already matches the target aspect."""
    from PIL import Image
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    box = best_crop_box(img, target_w, target_h)
    out = img.crop(box)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()
