# ToonForge — What works locally vs. what needs a GPU

This is the honest, single-page status of every capability, grouped by **what it takes to run
it**. The whole app is built on a provider-abstraction layer, so the *same features* light up
at higher quality when you move from CPU → cpu-ml → GPU, with **zero app-code changes** — you
flip a Docker profile / `PROVIDER_*` env var.

## The three run tiers

| Tier | Command | What it is | Cost |
|---|---|---|---|
| **CPU (default)** | `docker compose --profile cpu up` | 100% offline on a no-GPU machine | $0 |
| **CPU + ML extras** | `docker compose --profile cpu-ml up` | adds torch-CPU features (real music, voice clone, CLIP guard) — free, just slower | $0 |
| **GPU** | `docker compose --profile gpu up` | NVIDIA card (or rented RTX 4090 ~$0.34–0.40/hr) for cinematic quality | rented/HW |

> No NVIDIA GPU on this dev machine (Intel Iris Xe). The CPU and cpu-ml tiers are what runs
> here today; the GPU tier is built and waiting for hardware. See `GPU_DEPLOY.md`.

---

## ✅ Tier 1 — Works 100% local, free, no GPU (the default)

| Capability | How | Honest quality |
|---|---|---|
| **Character art / images** | SD-Turbo via `stable-diffusion.cpp` (`sdcpp`) | Good stylized art; ~45–75 s/image on CPU |
| **Character Foundry** | turnaround + expression + pose sheets, Character Card, instruction edits ("green t-shirt"), style presets | Full identity workflow |
| **Character lock / drift** | per-character seed + palette-similarity auto-regen | Pose-invariant color identity (not face-ID — that's CLIP, Tier 2) |
| **IP/brand guard (names)** | prompt name-blocklist | Blocks "Elsa", "Mickey", etc. at create/edit |
| **Speech (TTS)** | Piper, EN + FR | Clean, fast, natural |
| **Singing (SVS)** | `tts_pitch` — Piper pitch-warped to an auto melody (rubberband formant-preserve + vibrato) | **Works**, but stylized/novelty, not a studio vocal |
| **Lyrics → music** | rule-based mood/tempo/key picker → instrumental bed | Auto-matches the song's vibe |
| **Music bed** | numpy additive synth, auto-ducked under vocals | Simple but instant |
| **Subtitles** | faster-whisper word-level alignment, karaoke cues | Accurate word timing |
| **Script → shots** | rule-based planner (characters, camera, duration, background) | Solid auto-storyboard |
| **Video motion** | Ken Burns pan/zoom (FFmpeg) | Camera motion on stills — **not** true animation |
| **Lip-sync** | audio-driven mouth-flap (`lipsync`) | Basic novelty flap; best on centered close-ups; heuristic mouth placement |
| **Shorts auto-reframe** | content-aware 9:16 crop (saliency) | Keeps the subject framed (no stretch) |
| **Episode export** | FFmpeg assembly → real MP4, presets 1080p / 4K / 9:16 Shorts | Production-ready container |
| **YouTube thumbnails** | character-locked 1280×720 hero + bold title | Eye-catching, ready to upload |
| **Timeline** | PixiJS WebGL multi-track view (Video/Voice/Music/Subs) | Visual, scrubbable |
| **Transcript editing, cost meter, autosave, templates** | SQLite + in-process worker | Full project flow |

**The §5 happy path runs end-to-end here for $0:** paste lyrics → characters → sung/spoken
voice → auto music → shots → 1080p MP4 + thumbnails, all offline.

---

## ✅ Tier 2 — Local + free, but needs the `cpu-ml` image (torch-CPU, slower)

Built and verified on CPU; runs in the Python-3.12 `cpu-ml` Docker image (torch has no 3.14
wheels). Free, just slow.

| Capability | Provider | Quality / speed |
|---|---|---|
| **Real AI music** | `musicgen_local` (MusicGen) | Real instruments vs the numpy synth; **~5 min per 5 s** on CPU |
| **Voice cloning** | `xtts_local` (XTTS-v2) | Clone a voice from a 6–30 s sample; slow per line. *Model is non-commercial* |
| **CLIP IP-image guard** | `clip` consistency provider + `ip_guard.py` | Flags outputs that *look like* a protected IP (zero-shot CLIP); verified it doesn't false-flag original 3D-toddler art |
| **CLIP identity score (§6)** | `clip.similarity()` | Real semantic same-character score (vs the palette proxy) |

Enable per-capability, e.g. `PROVIDER_MUSIC=musicgen_local`, `PROVIDER_CONSISTENCY=clip`.

---

## ⚙️ Tier 3 — Needs an NVIDIA GPU (built + wired, deferred for hardware)

These are implemented behind their interfaces and activate via the `gpu` Docker profile on a
CUDA box. They can't run usefully on this CPU (minutes-to-hours per item).

| Capability | Provider | Why GPU | Status |
|---|---|---|---|
| **High-end images** | `flux_local` (FLUX.1-schnell, Apache-2.0) | 24 GB VRAM | Built, runtime-test pending a GPU |
| **True animation (img→video)** | `ltx_local` (LTX-Video) | the real "cinematic" upgrade over Ken Burns | Built, wired into compose with Ken Burns fallback |
| **Voice clone / music (fast)** | `xtts_local` / `musicgen_local` | same code, GPU speed | Auto-uses GPU when present |
| **Studio singing (SVS)** | `diffsinger_local` | neural vocoder | **Not built** — interface ready |
| **Realism lip-sync** | `sadtalker_local` | talking-head model + checkpoints | Registered, deferred (raises until GPU + checkpoints) |

---

## Where we *don't* meet the spec's quality bars (and why)

The build spec (§6) sets bars that assume a GPU. On this no-GPU machine:

- **Lip-sync ≤ 80 ms / mouth-shape accuracy** — ❌ not met. The CPU mouth-flap is approximate; needs SadTalker (GPU).
- **Singing pitch RMSE ≤ 25 cents** — ⚠️ approximate. `tts_pitch` follows the melody but is stylized; needs DiffSinger (GPU).
- **Character identity (CLIP/ArcFace ≥ 0.85)** — ✅ available via the `clip` provider (Tier 2); the default CPU tier uses a palette proxy.
- **"Full happy path on 100% open-source providers"** — ✅ met (Tier 1, entirely local & free).

---

## Anime styles & models

The app ships 5 anime **style presets** — `anime_shonen`, `anime_fantasy`, `anime_cyberpunk`,
`anime_cute`, `anime_dark` — plus a rule-based **character lore** generator (personality /
backstory / abilities, no LLM). On the **default SD-Turbo** model these already produce
anime-leaning art (e.g. a cyberpunk-anime warrior), fast and free.

For a **dedicated anime model**: the `sdcpp` provider auto-switches to a model whose filename
contains "anime" (config `SD_ANIME_MODEL`) when an `anime_*` style is used, else falls back to
SD-Turbo. Drop a compatible `.gguf` into `backend/models/sd/`. Honest free options (no single
one is *both* commercial-OK *and* CPU-fast):

| Model | Free? | sd.cpp-ready | CPU-practical | Note |
|---|---|---|---|---|
| **SD-Turbo + anime prompt** (default) | ✅ commercial-OK | ✅ | ✅ fast | anime-*leaning*, not true anime |
| [**Anima-GGUF**](https://huggingface.co/JusteLeo/Anima-GGUF) | ⚠️ **non-commercial** | ✅ | ❌ Qwen base, 30 steps @1024, needs VAE → slow | best dedicated-anime quality, personal use only |
| [**Animagine XL**](https://huggingface.co/cagliostrolab/animagine-xl-4.0) | ✅ commercial-OK (Fair AI) | ⚠️ SDXL | ❌ GPU realistically | true anime, but needs a GPU |

So: anime *styling* works locally & free today; a true anime *model* is either non-commercial
(Anima) or GPU (Animagine) — both are linked above and drop in via the filename auto-switch.

## One-line summary

**Everything that is physically possible on a no-GPU machine is built and works locally for
$0** — image gen, voice (speak *and* sing), auto-music, subtitles, Shorts reframe, thumbnails,
timeline, full episode export. The only things that genuinely need a GPU are **Flux-grade
images**, **true frame-by-frame animation**, and **studio-quality singing/lip-sync** — all
pre-wired to drop in the moment a CUDA card (local or a ~$0.40/hr rented 4090) is available.
