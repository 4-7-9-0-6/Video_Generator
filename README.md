# ToonForge Studio

An all-in-one, **local-first, free** AI creation suite: **Text → Cartoon Character**, **Text → Voice (speak & sing)**, **Text → Video** — assembled into full animated episodes with lip-sync, music, and subtitles.

This repository is the working implementation of the ToonForge build spec, adapted to run on a **single personal machine with no NVIDIA GPU**. The design centers on a **provider-abstraction layer**: every AI capability (image, video, TTS, SVS, music, lip-sync, alignment, assembly, storage) is an interface with at least one *real* implementation, chosen at runtime from config. Local CPU models are used where possible; free keyless cloud providers are used where a GPU is mandatory; local GPU models drop in unchanged the day a CUDA box is available.

> **Status:** all CPU-feasible modules built & verified (91 tests). Character Foundry, VoiceLab
> (speak **and** sing), Scene Engine, Composer/Export, thumbnails, Shorts reframe, WebGL timeline,
> CLIP IP-guard, lip-sync. GPU features (Flux, LTX animation, neural SVS) are wired & deferred.
>
> 👉 **[`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) — the single "what works locally vs. needs a GPU" summary.**
> Also: `docs/ROADMAP.md` (phase detail), `docs/GPU_DEPLOY.md` (RunPod 4090 guide).

---

## What runs where (this machine: CPU-only, Intel Iris Xe)

| Capability | Default provider | Kind | Free |
|---|---|---|---|
| Image / character art / thumbnails | `sdcpp` (SD-Turbo) | **local CPU** | ✅ |
| Speech (TTS) | `piper` | local CPU | ✅ |
| Subtitles / alignment | `faster_whisper` | local CPU | ✅ |
| Melody composition | `symbolic` | local CPU | ✅ |
| Assembly / mux | `ffmpeg` | local CPU | ✅ |
| Consistency / IP guard | `phash` baseline | local CPU | ✅ |
| Image→video, SVS, lip-sync | (GPU phase) | cloud / future-local | ✅ |

The **entire happy path now runs 100% offline on CPU at $0** — no API keys, no network. Switch
any provider in `backend/.env` (`PROVIDER_IMAGE=pollinations`, `=higgsfield`, `=mock`, etc.).
Providers that can't run report *why* and how to enable them — the app never hard-crashes.

> **Local image generation (`sdcpp`, default):** uses
> [stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp) — a pure C/C++ (ggml)
> binary, **no torch / no Python-ML wheels**, so it sidesteps the Python 3.14 wheel problem —
> running a quantized **SD-Turbo** model. One-time install (binary + ~1.4 GB model) below.
> Generation is ~45–75 s/image on a 4-core CPU (tunable via `SDCPP_STEPS`/`SDCPP_MAX_SIDE`).
> No GPU ⇒ great *stills + Ken Burns motion*, but not true frame-by-frame animation.
>
> **Cloud fallback (`PROVIDER_IMAGE=pollinations`):** keyless and free but networked, and its
> anonymous tier is rate-limited (HTTP 402 when busy; a free token at
> https://enter.pollinations.ai removes the limit). Use it only if you prefer cloud over the
> local CPU wait.

---

## Quick start

### 1. Prerequisites
- **Python 3.12 recommended** (3.14 works for the core API, but some ML wheels may not exist yet).
- **Node 20+** (for the future Next.js frontend).
- **FFmpeg** on `PATH` (required for assembly/export). Windows: `winget install Gyan.FFmpeg`.

### 2. Backend
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt          # core API (always works)
pip install -r requirements-ml.txt       # optional: Piper TTS, faster-whisper (CPU)
copy .env.example .env
python scripts\setup_check.py             # reports which providers are live
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000/docs for the interactive API.

### 3. Frontend (Next.js)
```powershell
cd frontend
npm install
copy .env.local.example .env.local      # points the browser at http://localhost:8000
npm run dev                              # → http://localhost:3000
```
Create a project → open it → create a character ("Mila", a description, a style, optional palette)
→ watch the turnaround / expression / pose sheets generate with a live progress bar and a
consistency report. Use the instruction-edit box ("change her t-shirt to green") to regenerate.

> Tip: to see the whole pipeline complete instantly without the image API, start the backend
> with `$env:PROVIDER_IMAGE='mock'` — it renders deterministic placeholder art so you can
> exercise the full flow offline.

### 4. Go fully offline (local SD-Turbo image generation)
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts\install_sdcpp.py      # one-time: stable-diffusion.cpp CPU binary (~20 MB)
python scripts\download_sd_model.py  # one-time: SD-Turbo Q8_0 model (~1.4 GB)
```
`PROVIDER_IMAGE=sdcpp` is the default, so once these finish, all image/character/thumbnail
generation runs on your CPU with no network. (Add `--quant Q4_0` for a smaller/faster model.)

### 5. Export a full episode + YouTube thumbnails (local, free)
```powershell
python scripts\install_ffmpeg.py     # one-time: local static FFmpeg (no admin)
python scripts\download_voices.py    # one-time: Piper EN+FR voices
```
Then in the UI: open a project → **Storyboard** → paste a script → **Plan shots** →
**Render all keyframes** → **Export MP4** (pick preset, voiceover, subtitles, music). The
finished 1080p video plays inline and downloads. On the same page, **Propose thumbnails**
generates a few 1280×720 character-locked YouTube thumbnails with bold titles. All on CPU at $0.

### 6. Smoke test (no GPU, no keys needed)
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest tests -k "not network" -q   # 54 pass; 1 network test deselected
```

---

## Run with Docker

The whole stack is containerized. Two profiles:

```bash
# 100% offline CPU stack (default) — backend :8000 + frontend :3000
docker compose --profile cpu up --build

# CPU + local ML extras — adds REAL MusicGen music (and optional XTTS voice clone),
# still free, still local, no GPU — just slower (minutes per clip)
docker compose --profile cpu-ml up --build

# CUDA machine only — reserves an NVIDIA GPU for the GPU-phase providers
docker compose --profile gpu up --build
```

- **`cpu`** runs the full offline pipeline (SD-Turbo, Piper, Whisper, FFmpeg). The backend
  image is **Python 3.12**, so the ML wheels install cleanly (sidesteps the host's 3.14 gap),
  and the **Linux `stable-diffusion.cpp` binary is baked in**. The `./backend/models` and
  `./backend/data` volumes are mounted, so the ~1.4 GB model + your projects persist on the
  host and are **not re-downloaded** on rebuild (if you already ran the install scripts, the
  container reuses them immediately).
- **`gpu`** runs the real GPU providers — **`flux_local`** (FLUX.1-schnell images),
  **`ltx_local`** (LTX-Video true img→video animation), **`xtts_local`** (voice cloning),
  **`musicgen_local`** (music). It **requires a physical NVIDIA GPU** + the [NVIDIA Container
  Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html);
  Docker does **not** create a GPU, it only passes through one that exists. Cheapest path is a
  rented RTX 4090 (~$0.34–0.40/hr). **Full step-by-step: [`docs/GPU_DEPLOY.md`](docs/GPU_DEPLOY.md).**

---

## Architecture at a glance
- **`backend/app/providers/`** — the moat. `base.py` defines the capability interfaces; each subpackage has real implementations. `registry.py` resolves `capability → provider` from config with graceful fallback.
- **`backend/app/jobs/`** — SQLite-backed job queue + in-process async worker (no Redis/Celery needed for single-user/local). Resumable, idempotent, retry ×2.
- **`backend/app/db.py` + `models.py`** — explicit SQLite schema (projects, characters, voices, shots, assets, jobs, embeddings). Zero external DB. Upgrade path to Postgres+pgvector documented.
- **`backend/app/routers/`** — FastAPI endpoints. Projects, Characters (Foundry), Jobs.

See `docs/ARCHITECTURE.md` for the full picture and `docs/ROADMAP.md` for the phase plan.
