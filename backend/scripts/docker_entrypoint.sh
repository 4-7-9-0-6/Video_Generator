#!/bin/sh
# First-boot setup, then launch the API. Model + voices land in mounted volumes so they
# download only once and survive container rebuilds. Failures are non-fatal: the app still
# boots and reports which providers are unavailable (and how to fix them).
set -e

echo "[entrypoint] ensuring local SD-Turbo model…"
python scripts/download_sd_model.py || echo "[entrypoint] WARN: SD model download failed (set PROVIDER_IMAGE=pollinations to use the free cloud fallback, or retry)."

echo "[entrypoint] ensuring Piper voices…"
python scripts/download_voices.py || echo "[entrypoint] WARN: Piper voice download failed (TTS will be unavailable until voices are present)."

echo "[entrypoint] starting ToonForge API on :8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
