# GPU Deployment — making ToonForge "outperform"

The CPU stack runs everything offline for $0, but with one physics limit: no real animation,
no Flux-grade images, no voice cloning/singing. Those need an **NVIDIA GPU**. This box has
none, so the GPU providers are built + wired but must run on a CUDA machine — most cheaply a
**rented RTX 4090** (~$0.34–0.40/hr; well under $1 per finished episode of GPU time).

When `PROVIDER_*=*_local` and a CUDA GPU is present, the providers activate with **zero app
code changes** (it's the provider abstraction). When absent, each reports itself unavailable
and the app falls back to the CPU stack.

| Capability | GPU provider | Model | License | VRAM |
|---|---|---|---|---|
| Image | `flux_local` | FLUX.1-schnell | Apache-2.0 (free, commercial OK) | ~24 GB (12–16 w/ `GPU_OFFLOAD=1`) |
| Video (img→video) | `ltx_local` | LTX-Video | open weights | ~24 GB |
| TTS / voice clone | `xtts_local` | XTTS-v2 | Coqui Public Model License (**non-commercial**) | ~6 GB |
| Music | `musicgen_local` | MusicGen-small | CC-BY-NC (**non-commercial**) | ~4 GB |

> ⚠️ XTTS and MusicGen model weights are **non-commercial**. For commercial output, keep
> `PROVIDER_TTS=piper` / `PROVIDER_MUSIC=symbolic` (both free + commercial-OK), and use only
> `flux_local` + `ltx_local` on the GPU.

---

## Recommended: RunPod, RTX 4090

### 1. Create the pod
1. Sign up at runpod.io → **Pods → Deploy**.
2. GPU: **RTX 4090 (24 GB)** (or RTX 3090 to save ~40%). Community Cloud is cheapest.
3. Template: any **CUDA 12.1+** base, or "RunPod PyTorch 2.4". Container disk ≥ 30 GB.
4. **Add a Network Volume** (e.g. 60 GB) mounted at `/workspace` — this persists the model
   weights (~30 GB) so you don't re-download them every session (~$0.05–0.10/GB/mo).
5. Expose **TCP port 8000** (and 3000 if you also run the frontend).

### 2. Get the code + build
```bash
cd /workspace
git clone <your-repo> toonforge && cd toonforge
# point the HF cache at the persistent volume so weights survive pod restarts
export HF_HOME=/workspace/hf-cache
docker compose --profile gpu up --build      # builds Dockerfile.gpu, starts backend-gpu
```
First boot prints the detected GPU. The **first generation downloads weights** (Flux ~24 GB,
LTX ~10 GB, XTTS ~2 GB) into the cache — slow once, instant after.

> No Docker on the pod? Run bare-metal instead:
> ```bash
> cd backend && pip install -r requirements.txt -r requirements-gpu.txt
> PROVIDER_IMAGE=flux_local PROVIDER_VIDEO=ltx_local \
> PROVIDER_TTS=xtts_local PROVIDER_MUSIC=musicgen_local \
> uvicorn app.main:app --host 0.0.0.0 --port 8000
> ```

### 3. Use it
Hit `http://<pod-ip>:8000/providers` — every `*_local` provider should read
`available=true, kind=local`. Then drive it exactly like the CPU app (plan → render →
export). The episode now uses **Flux keyframes** and **real LTX animation** instead of
SD-Turbo + Ken Burns. The cost meter shows GPU-seconds × `GPU_USD_PER_HOUR`.

### 4. Cost control
- Bill is per-hour **while the pod runs** — **stop the pod** when idle.
- Typical: image-only episode ≈ a few cents; full LTX-animated 2-min episode ≈ $0.20–0.45.
- Try it free first: **Modal** gives $30/mo credits; Colab has a free T4 (fine to smoke-test
  one provider).

### Voice cloning
Upload a 6–30 s clean reference `.wav` to the pod and set `XTTS_SPEAKER_WAV=/workspace/me.wav`
(or pass `speaker_wav` per call). Without it, XTTS uses a built-in speaker. Consent required
for cloning a real person's voice (spec §B.1).

---

## Switching back to CPU
Just use the cpu profile (or unset the env): `docker compose --profile cpu up`. Same app,
same projects (shared SQLite/assets) — only the providers differ.

## Still TODO (GPU, not yet implemented)
- **Singing / SVS** (`diffsinger_local`): DiffSinger needs phonemizer + checkpoints + an
  OpenUtau-style note input; integration is non-trivial and untested here. ACE-Step is a
  pip-friendlier alternative worth evaluating. Interface (`SVSProvider.sing`) is ready.
- **Lip-sync** (`sadtalker_local` / LivePortrait): drives the mouth from the voice track;
  custom repo + checkpoints. Interface (`LipSyncProvider.apply`) is ready.

Both slot in behind their existing interfaces the same way the four providers above did.
