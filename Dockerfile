# ToonForge backend — Python 3.12 so the ML deps (faster-whisper, piper, future torch)
# install from real wheels (sidesteps the host's Python 3.14 wheel gap). FFmpeg comes from
# apt; the stable-diffusion.cpp CPU binary is baked in; the big model + Piper voices download
# on first boot into mounted volumes (kept out of the image to stay lean).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgomp1 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# python deps first for layer caching
COPY backend/requirements.txt backend/requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ml.txt

# app source
COPY backend/ ./

# bake the (small ~20 MB) Linux CPU sd.cpp binary into the image; install_sdcpp.py is OS-aware
RUN python scripts/install_sdcpp.py

ENV PROVIDER_IMAGE=sdcpp \
    TOONFORGE_HOST=0.0.0.0 \
    TOONFORGE_DATA_DIR=/app/backend/data \
    PIPER_MODELS_DIR=/app/backend/models/piper
# (SD model auto-resolves from backend/models/sd/*.gguf — downloaded by the entrypoint)

EXPOSE 8000
ENTRYPOINT ["sh", "scripts/docker_entrypoint.sh"]
