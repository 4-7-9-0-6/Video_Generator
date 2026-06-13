#!/bin/sh
# GPU entrypoint. Model weights (FLUX / LTX / XTTS / MusicGen) download from Hugging Face
# lazily on first generation into $HF_HOME (a mounted volume), so we don't bake ~30 GB into
# the image. Just report the GPU and launch the API.
set -e

echo "[entrypoint-gpu] CUDA check:"
python - <<'PY'
try:
    import torch
    print("  torch", torch.__version__, "| cuda_available:", torch.cuda.is_available(),
          "|", (torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NO GPU"))
except Exception as e:
    print("  torch import failed:", e)
PY

echo "[entrypoint-gpu] starting ToonForge API on :8000 (weights download on first use)"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
