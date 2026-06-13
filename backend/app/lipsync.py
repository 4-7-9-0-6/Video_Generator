"""Local CPU lip-sync (spec §C.3) — an audio-driven "mouth flap".

Honest scope: real neural lip-sync (Wav2Lip/SadTalker) needs a GPU and struggles on
stylized cartoon faces. On a no-GPU box the achievable, reliable effect is a cartoon mouth
flap: read the voice loudness envelope, and open/close a mouth overlay at the character's
mouth in sync. Uses numpy + PIL + FFmpeg (no torch); OpenCV face detection is used to place
the mouth when available, otherwise a centered heuristic. Best on character close-ups.

Quality ceiling is "Saturday-morning cartoon", not photoreal — `sadtalker_local` (GPU) is the
realism upgrade behind the LipSyncProvider interface.
"""
from __future__ import annotations

import asyncio
import io
import subprocess
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

from .ffmpeg_util import ffmpeg_exe, has_ffmpeg


def _read_wav(wav_bytes: bytes):
    import numpy as np
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        n, ch, sw = w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}[sw]
    a = np.frombuffer(raw, dtype=dtype).astype("float64")
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a / float(2 ** (8 * sw - 1))


def voice_envelope(wav_bytes: bytes, n_frames: int) -> list[float]:
    """Per-frame mouth openness 0..1 from the audio RMS, percentile-normalized + smoothed."""
    import numpy as np
    if n_frames <= 0:
        return []
    arr = _read_wav(wav_bytes) if wav_bytes else np.zeros(0)
    if arr.size == 0:
        return [0.0] * n_frames
    edges = np.linspace(0, arr.size, n_frames + 1).astype(int)
    rms = np.array([
        float(np.sqrt(np.mean(arr[a:b] ** 2))) if b > a else 0.0
        for a, b in zip(edges[:-1], edges[1:])
    ])
    hi = float(np.percentile(rms, 92)) or 1.0
    env = np.clip(rms / hi, 0.0, 1.0)
    if env.size >= 3:                                # light smoothing -> no per-frame jitter
        env = np.convolve(env, np.array([0.25, 0.5, 0.25]), mode="same")
    return [float(x) for x in env]


def mouth_box(img) -> tuple[int, int, int, int]:
    """(cx, cy, w, h) of the mouth. OpenCV face detect when available, else a centered
    heuristic (~62% down — works for head-and-shoulders character framings)."""
    W, H = img.size
    try:
        import cv2  # type: ignore
        import numpy as np
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        gray = np.asarray(img.convert("L"))
        faces = cascade.detectMultiScale(gray, 1.2, 4, minSize=(int(W * 0.12), int(H * 0.12)))
        if len(faces):
            fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            return (int(fx + fw / 2), int(fy + fh * 0.74), int(fw * 0.22), int(fh * 0.05))
    except Exception:  # noqa: BLE001 — opencv missing / no face -> heuristic
        pass
    # heuristic for a centered head-and-shoulders framing (mouth ~74% down)
    return (int(W * 0.49), int(H * 0.74), int(W * 0.10), int(H * 0.035))


def _cover(img, w: int, h: int):
    from PIL import Image
    sw, sh = img.size
    scale = max(w / sw, h / sh)
    nw, nh = max(w, int(sw * scale)), max(h, int(sh * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


async def render_talking_clip(keyframe: bytes, voice_wav: bytes, *, duration_s: float,
                              fps: int, width: int, height: int) -> bytes:
    if not has_ffmpeg():
        raise RuntimeError("lip-sync needs ffmpeg — run: python scripts/install_ffmpeg.py")
    return await asyncio.to_thread(_render, keyframe, voice_wav, duration_s, fps, width, height)


def _render(keyframe: bytes, voice_wav: bytes, duration_s: float, fps: int,
            width: int, height: int) -> bytes:
    from PIL import Image, ImageDraw, ImageFilter

    base = _cover(Image.open(io.BytesIO(keyframe)).convert("RGB"), width, height)
    cx, cy, mw, mh = mouth_box(base)
    n_frames = max(1, round(duration_s * fps))
    env = voice_envelope(voice_wav, n_frames) if voice_wav else [0.0] * n_frames

    with TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        for i in range(n_frames):
            frame = base.copy()
            open_amt = env[i] if i < len(env) else 0.0
            if open_amt > 0.08:                      # draw an open mouth proportional to loudness
                ow = mw * (0.9 + 0.2 * open_amt)     # mouth is wider than it is tall
                oh = mh * 0.3 + open_amt * mh * 1.0
                mouth = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                d = ImageDraw.Draw(mouth)
                d.ellipse([cx - ow, cy - oh, cx + ow, cy + oh], fill=(74, 30, 32, 225))
                # soft inner (tongue/throat) so it reads as an open mouth, not a black blob
                d.ellipse([cx - ow * 0.55, cy - oh * 0.1, cx + ow * 0.55, cy + oh * 0.8],
                          fill=(150, 72, 74, 150))
                mouth = mouth.filter(ImageFilter.GaussianBlur(max(1, int(mw * 0.06))))
                frame = Image.alpha_composite(frame.convert("RGBA"), mouth).convert("RGB")
            frame.save(tmpd / f"f{i:05d}.png")

        (tmpd / "voice.wav").write_bytes(voice_wav or b"")
        ff = ffmpeg_exe()
        out = tmpd / "talk.mp4"
        args = [ff, "-y", "-framerate", str(fps), "-i", "f%05d.png"]
        if voice_wav:
            args += ["-i", "voice.wav"]
        args += ["-t", f"{duration_s:.3f}", "-r", str(fps), "-c:v", "libx264",
                 "-pix_fmt", "yuv420p"]
        if voice_wav:
            args += ["-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest"]
        args += [str(out.name)]
        proc = subprocess.run(args, cwd=str(tmpd), capture_output=True)
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(f"lip-sync ffmpeg failed: {proc.stderr.decode(errors='ignore')[-500:]}")
        return out.read_bytes()
