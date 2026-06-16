"""Depth-parallax video provider — 2.5D "DepthFlow"-style motion, FREE + LOCAL on CPU (spec §C.2).

Turns a still keyframe into a real depth-parallax clip: estimate a depth map with a small ONNX
model (onnxruntime — NO torch, so it runs on Python 3.14 and a 16 GB CPU box), then animate a
gentle camera move where NEAR pixels shift more than FAR ones — the 2.5D effect. A numpy inverse
(backward) warp samples every output pixel, so there are no disocclusion holes, and a small
overscan zoom hides edge artifacts. Far livelier than flat Ken Burns, still $0 and offline.

Model: a MiDaS-small-style ONNX depth model at models/depth/ (scripts/download_depth_model.py).
Select with PROVIDER_VIDEO=depth_parallax; falls back to ffmpeg_kenburns if the model is missing.
"""
from __future__ import annotations

import asyncio
import io
import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from ...config import settings
from ...ffmpeg_util import ffmpeg_exe
from ..base import Availability, Capability, Cost, GenResult, ProviderInfo, VideoProvider

try:
    import cv2 as _cv2          # opencv-python-headless — its C/SIMD remap is ~30x the numpy warp
except ImportError:
    _cv2 = None

_session = None
_inp_name: str | None = None
_inp_hw: tuple[int, int] = (256, 256)
_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)


def _get_session():
    global _session, _inp_name, _inp_hw
    if _session is None:
        import onnxruntime as ort
        _session = ort.InferenceSession(str(settings.depth_model), providers=["CPUExecutionProvider"])
        inp = _session.get_inputs()[0]
        _inp_name = inp.name
        dims = [d for d in inp.shape if isinstance(d, int) and d > 3]
        if len(dims) >= 2:
            _inp_hw = (dims[-2], dims[-1])
    return _session


def _estimate_depth(rgb: np.ndarray) -> np.ndarray:
    """rgb: HxWx3 float[0..255] -> depth HxW in [0,1] (1 = nearest)."""
    H, W = rgb.shape[:2]
    sess = _get_session()
    ih, iw = _inp_hw
    small = np.asarray(Image.fromarray(rgb.astype(np.uint8)).resize((iw, ih), Image.BILINEAR), np.float32) / 255.0
    small = (small - _MEAN) / _STD
    inp = small.transpose(2, 0, 1)[None].astype(np.float32)
    out = np.squeeze(sess.run(None, {_inp_name: inp})[0]).astype(np.float32)
    # np.array (not asarray) -> a writable copy; PIL image buffers are read-only
    depth = np.array(Image.fromarray(out, mode="F").resize((W, H), Image.BILINEAR), np.float32)
    depth -= float(depth.min())
    peak = float(depth.max())
    if peak > 1e-6:
        depth /= peak            # MiDaS outputs inverse depth -> larger == nearer
    return depth


def _bilinear(arr: np.ndarray, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
    H, W = arr.shape[:2]
    sx = np.clip(sx, 0, W - 1)
    sy = np.clip(sy, 0, H - 1)
    x0 = np.floor(sx).astype(np.int32)
    y0 = np.floor(sy).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, W - 1)
    y1 = np.clip(y0 + 1, 0, H - 1)
    wx = (sx - x0)[..., None]
    wy = (sy - y0)[..., None]
    top = arr[y0, x0] * (1 - wx) + arr[y0, x1] * wx
    bot = arr[y1, x0] * (1 - wx) + arr[y1, x1] * wx
    return np.clip(top * (1 - wy) + bot * wy, 0, 255).astype(np.uint8)


def _base_grid(H: int, W: int) -> tuple[np.ndarray, np.ndarray]:
    """Static (zoom-applied) sampling coords — same for every frame, so build once per clip."""
    zoom = 1.0 + settings.depth_parallax_zoom
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2.0, H / 2.0
    return cx + (xs - cx) / zoom, cy + (ys - cy) / zoom


def _camera_offset(t: float, motion: str, W: int) -> tuple[float, float]:
    """Gentle, loopable circular camera path (returns to start at t=1)."""
    amp = settings.depth_parallax_amplitude * (1.4 if ("zoom" in motion or "bounce" in motion) else 1.0)
    return math.sin(2 * math.pi * t) * amp * W, math.cos(2 * math.pi * t) * amp * W * 0.5


def _warp_with(rgb, depth, base_sx, base_sy, ox: float, oy: float) -> np.ndarray:
    """Backward-sample with the depth-displaced grid (near pixels shift most). cv2.remap when
    available (fast), else the numpy fallback. Always returns uint8."""
    mx = (base_sx + ox * depth).astype(np.float32)
    my = (base_sy + oy * depth).astype(np.float32)
    if _cv2 is not None:
        src = rgb if rgb.dtype == np.uint8 else rgb.astype(np.uint8)
        return _cv2.remap(src, mx, my, interpolation=_cv2.INTER_LINEAR, borderMode=_cv2.BORDER_REPLICATE)
    return _bilinear(rgb, mx, my)


def _warp_frame(rgb: np.ndarray, depth: np.ndarray, t: float, motion: str) -> np.ndarray:
    """Convenience used by tests; the hot loop in _run precomputes the grid instead."""
    H, W = depth.shape
    bsx, bsy = _base_grid(H, W)
    ox, oy = _camera_offset(t, motion, W)
    return _warp_with(rgb, depth, bsx, bsy, ox, oy)


class DepthParallaxVideoProvider(VideoProvider):
    info = ProviderInfo(
        name="depth_parallax", capability=Capability.VIDEO, kind="local",
        free=True, requires_gpu=False,
    )

    def availability(self) -> Availability:
        if ffmpeg_exe() is None:
            return Availability(False, reason="ffmpeg not found",
                                install_hint="python scripts/install_ffmpeg.py")
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            return Availability(False, reason="onnxruntime not installed",
                                install_hint="pip install onnxruntime")
        if not settings.depth_model.exists():
            return Availability(False, reason="depth model missing",
                                install_hint="python scripts/download_depth_model.py")
        return Availability(True, reason="local depth-parallax (CPU, no torch)")

    def estimate_cost(self, **kw: object) -> Cost:
        return Cost()

    async def animate(self, image: bytes, *, motion: str = "static",
                      duration_s: float = 4.0, fps: int = 24, prompt: str = "",
                      **kw: object) -> GenResult:
        return await asyncio.to_thread(self._run, image, motion, duration_s, fps, kw)

    def _run(self, image: bytes, motion: str, duration_s: float, fps: int, kw: dict) -> GenResult:
        w = int(kw.get("width", 0)) or None
        h = int(kw.get("height", 0)) or None
        img = Image.open(io.BytesIO(image)).convert("RGB")
        tw, th = (w, h) if (w and h) else img.size
        # Cap the WARP resolution — the numpy warp cost is ~O(pixels), and compose upscales the
        # clip to the export size anyway, so warping at full 1080p would just be slow for nothing.
        side = max(tw, th)
        if side > settings.depth_max_side:
            s = settings.depth_max_side / side
            tw, th = max(16, int(tw * s) // 2 * 2), max(16, int(th * s) // 2 * 2)
        img = ImageOps.fit(img, (tw, th), Image.LANCZOS)
        rgb = np.asarray(img)               # uint8 — cv2.remap warps it with no per-frame cast
        H, W = rgb.shape[:2]
        depth = _estimate_depth(rgb)
        nframes = max(2, int(round(duration_s * fps)))
        # precompute the static grid once, then pipe raw RGB frames straight into ffmpeg (no PNG I/O)
        bsx, bsy = _base_grid(H, W)
        parts = []
        for i in range(nframes):
            ox, oy = _camera_offset(i / max(1, nframes - 1), motion, W)
            parts.append(_warp_with(rgb, depth, bsx, bsy, ox, oy).tobytes())
        raw = b"".join(parts)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "clip.mp4"
            proc = subprocess.run(
                [ffmpeg_exe(), "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                 "-framerate", str(fps), "-i", "-", "-t", f"{duration_s:.3f}", "-r", str(fps),
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out)],
                input=raw, capture_output=True)
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or b"").decode(errors="ignore")
                raise RuntimeError(f"ffmpeg depth-parallax failed: {err[-600:]}")
            data = out.read_bytes()
        return GenResult(data=data, mime="video/mp4", cost=Cost(),
                         meta={"provider": "depth_parallax", "motion": motion, "frames": nframes})
