"""Turn raw exception strings into friendly, actionable messages for the UI.

The worker stores `f"{ExcClass}: {message}"`. That's fine for logs but cryptic in the UI (a user
once saw a bare `NotImplementedError:`). `humanize()` maps common failure patterns to plain
guidance and, otherwise, strips the exception-class noise. Exposed as `friendly_error` on job API
responses so every client shows something useful.
"""
from __future__ import annotations

# (substring to match in the lowercased raw error, friendly message). First match wins; a None
# friendly means "pass the cleaned raw error through" (it's already readable, e.g. 'not found').
_RULES: list[tuple[str, str | None]] = [
    ("ffmpeg not installed", "Video tools (FFmpeg) aren't installed. Run: python scripts/install_ffmpeg.py"),
    ("no shots have keyframes", "Render the keyframes first (Storyboard → Render keyframes), then export."),
    ("out of memory", "The GPU ran out of memory — try fewer scenes or a lower resolution."),
    ("notimplementederror", "Internal render error (a bug, not your input). The run can be retried; please report it if it repeats."),
    ("ffmpeg failed", "Video assembly failed in FFmpeg. Try again, or simplify the export (fewer effects)."),
    ("429", "Rate-limited by the free AI service — wait a minute and try again."),
    ("rate limit", "The free AI service is busy/rate-limited right now — wait a minute and try again."),
    ("503", "The AI service is temporarily unavailable — try again shortly."),
    ("cloudflare", "Image generation failed — check your Cloudflare account ID / API token and daily free limit."),
    ("openrouter", "The AI text model failed — check your OpenRouter key, or it may be rate-limited (free tier)."),
    ("kaggle", "The GPU render couldn't reach Kaggle — check your API token at ~/.kaggle/kaggle.json."),
    ("api key", "An API key is missing or invalid — check backend/.env."),
    ("timed out", "The operation timed out. Try again."),
    ("connection", "Couldn't reach a service. Check your network and try again."),
    ("not found", None),          # e.g. "project not found" — already clear
]


def _clean(raw: str) -> str:
    """Drop a leading 'SomeError: ' prefix when there's a real message after it."""
    if ":" in raw:
        head, _, tail = raw.partition(":")
        if head and head[0].isupper() and head.endswith(("Error", "Exception")) and tail.strip():
            return tail.strip()
    return raw.strip()


def humanize(raw: str | None) -> str:
    if not raw or not raw.strip():
        return "The job failed without error details. Please try running it again."
    low = raw.lower()
    for pat, friendly in _RULES:
        if pat in low:
            return friendly if friendly is not None else _clean(raw)
    return _clean(raw) or "Something went wrong. Please try again."
