# ToonForge — Roadmap (adapted to local-first / CPU-only)

The original spec assumes a GPU and cloud infra. This roadmap keeps the same module order
but sequences the work to what your machine can run free today, with GPU work clearly fenced off.

## Phase 1 — Foundation  ✅ in progress (this commit)
- [x] Repo structure, docs, env config
- [x] SQLite schema + data layer
- [x] Provider abstraction (interfaces + registry + graceful availability)
- [x] Real providers: local FS storage, pHash consistency, image gen — **`sdcpp` local SD-Turbo (offline CPU, default)** with `pollinations` (free cloud) + `mock` (test) alternates
- [x] Job queue + in-process async worker + retry
- [x] FastAPI app + Projects/Characters/Jobs routers + setup_check + smoke tests
- [ ] Piper TTS + faster-whisper providers verified installed (needs `requirements-ml.txt`)
- [ ] FFmpeg assembly verified (needs FFmpeg on PATH)

## Phase 2 — Character Foundry  ✅ done (tested offline via mock provider)
- [x] Turnaround (front/3-4/side/back) + expression + pose sheets from one prompt (`character_sheets` job)
- [x] Character Card persistence + reuse-injection prompt builder (`foundry.build_character_prompt`, shared with shots)
- [x] Instruction-based edit ("change shirt to green") → `POST /characters/{id}/edit`, re-applies + regenerates
- [x] Style presets (3D-toddler/2D/chibi/clay/watercolor) + `GET /styles`; legally-distinct phrasing baked into presets
- [x] Drift auto-regeneration + consistency report (palette similarity ≥ threshold; auto-retry below)
- [x] IP/brand guard on create + edit (name blocklist) **+ CLIP image-similarity guard** (`app/ip_guard.py` + `clip` consistency provider): zero-shot CLIP classifies the generated character against known-IP text prompts vs "original" anchors; flags only when a protected IP beats every anchor (so legit originals pass). Logged into the consistency report + sets `ip_flagged`. CPU-capable (cpu-ml image, `PROVIDER_CONSISTENCY=clip`); pHash stays the no-torch default.

**Design note:** cross-view identity drift is scored by **palette similarity** (color histogram
cosine), not pHash — different poses are *supposed* to look structurally different, so pHash
would false-flag them. Palette is preserved across poses, making it the right CPU signal.
True face-identity (CLIP/ArcFace ≥ 0.85) lands in the GPU phase behind the same interface.

## Phase 3 — VoiceLab  ◑ in progress
- [x] TTS (Piper) EN+FR with speed control — `POST /voice/tts`, real local CPU audio (installed + tested)
- [x] Melody-from-text → MIDI — `POST /voice/melody` (symbolic, CPU)
- [x] VoiceLab UI page at `/voice` — speak + compose melody + **🎤 Sing panel** (lyrics + language/key/tempo/vibrato sliders → audio preview)
- [ ] Emotion/pitch controls + per-word regen (Overdub parity) — piper has no emotion axis; per-word splice is next
- [ ] Voice cloning (XTTS) — **GPU**; interface ready, deferred
- [x] **SVS (local CPU baseline)**: `tts_pitch` provider + `app/singing.py` — sings lyrics to an auto melody by pitch-warping Piper words (faster-whisper align → numpy F0 → FFmpeg pitch-shift to scale notes near the voice's register). `POST /voice/sing`, `ExportRequest.sing` override (sing instead of speak), storyboard 🎤 toggle **with key / tempo / vibrato controls** (override the auto-from-lyrics pick; the music bed follows the same key/tempo). Free/local/CPU, no torch. **Verified: "Twinkle twinkle" sung over a lullaby bed → real 1080p MP4 in 31s; pitch contour lands on C-E-G.**
- [x] **Singing quality polish**: FFmpeg **rubberband `formant=preserved`** pitch shift (kills the chipmunk/robotic timbre) + a continuous **vibrato** pass (`vibrato` param) + raised-cosine edge fades (de-click word joins). Verified rubberband active in the bundled build; per-line synth ~5-6s.
- [ ] Studio-quality SVS (neural DiffSinger) — **GPU**, deferred (the `tts_pitch` baseline holds the same `SVSProvider.sing` interface)
- [ ] Music bed + auto-duck (CPU mixing via FFmpeg) + stems export

## Phase 4 — Scene Engine  ◑ in progress
- [x] Script→shots planner (rule-based: characters present, camera, duration, background) — `POST /projects/{id}/plan`
- [x] Keyframe gen with character + background lock (`shot_keyframe` job, reuses Foundry identity)
- [x] Render cache (prompt_hash) — never re-renders an unchanged shot
- [x] Continuity seeding (previous shot's keyframe → next shot when same background)
- [x] Cross-shot character drift check (palette similarity vs the character's turnaround sheet)
- [x] Motion-preset library + free CPU `ffmpeg_kenburns` video provider (activates once FFmpeg installed)
- [x] Storyboard UI (`/projects/[id]/storyboard`): plan, edit camera/shot, render keyframes live
- [ ] Image→video animation via the motion provider end-to-end (needs FFmpeg installed) or GPU/cloud LTX/Higgsfield
- [x] **Lip-sync (local CPU mouth-flap)**: `app/lipsync.py` — voice RMS envelope drives an open-mouth overlay (PIL) at the mouth (OpenCV face-detect when available, else a centered heuristic), synced per frame, encoded with FFmpeg. `ExportRequest.lipsync` flag (replaces Ken Burns on voiced shots). numpy/PIL/FFmpeg only, no torch. **Verified live: mouth opens on loud frames, closed when silent.** Honest ceiling: novelty cartoon flap; placement is heuristic without face detection.
- [x] GPU `sadtalker_local` LipSyncProvider — registered, deferred (needs GPU + SadTalker checkpoints); the realism upgrade behind the same interface.

## Phase 5 — Composer & Export  ◑ in progress
- [x] Episode assembler (`app/compose.py`, `episode_assemble` job): per-shot Ken Burns clip + Piper voiceover, concat, burned subtitles → MP4
- [x] Export presets (youtube_1080p / youtube_4k / shorts_1080x1920) — `POST /projects/{id}/export`
- [x] Subtitles (SRT from shot timing, burned in) + exported as a sidecar `.srt` asset
- [x] Cost meter — `GET /projects/{id}/cost` (GPU-seconds + $; 0 on the free stack)
- [x] Export UI in the storyboard (preset/voice/subtitles → inline video player + download)
- [x] **Verified live: real 1920×1080 H.264+AAC MP4 with voice + subtitles, 100% local CPU**
- [x] Word-level subtitles via faster-whisper alignment (grouped into readable cues; line-level fallback)
- [x] Music bed: numpy additive synth (text→melody→audio) + FFmpeg sidechain auto-duck under vocals
- [x] **Lyrics → auto music** (`app/music_brief.py`): rule-based EN+FR mood/tempo/key picker — paste lyrics, the app auto-selects a fitting bed (lullaby→slow minor, playful→fast major, etc.) with no manual description. `ExportRequest.music_auto` (default on), `GET /projects/{id}/music-brief` preview, storyboard shows the picked mood. **Verified: lullaby lyrics → 68 BPM A-minor bed in a real export.**
- [x] Playable melody audio in VoiceLab (`/voice/melody` `audio:true`)
- [x] Transcript-driven editing (delete/edit/insert/reorder lines; edit → shot goes stale → re-renders just that shot; cache skips unchanged) + Transcript editor UI
- [x] **WebGL multi-track timeline** (`/projects/[id]/timeline`, PixiJS v8): Video/Voice/Music/Subtitle lanes, per-shot clip blocks sized by duration, keyframe thumbnails (best-effort), pseudo-waveform on the voice lane, time ruler, scrubbable playhead + play/pause, click-to-select shot. Pure frontend, local/free, no GPU. Pixi dynamically imported (no SSR). Linked from the storyboard. **Verified live in headless Chrome: lanes, clip blocks, voice waveforms, music span, subtitle cue text, ruler and playhead all render.**
- [ ] Timeline editing (drag/trim clips, WebCodecs frame-accurate preview) — next refinement

## Phase 6 — Polish  ◑ in progress
- [x] Motion presets library (Scene Engine)
- [x] Onboarding "Nursery Rhyme Episode" template — one click scaffolds project+character+shots (`POST /templates/{id}/instantiate`); home-page UI
- [x] **Verified: one template click → render → export → finished 27.8s 1080p MP4 (voice + word subs + music)**
- [x] **YouTube thumbnail proposals** (`app/thumbnail.py`, `POST /projects/{id}/thumbnails`): N character-locked 1280×720 hero images + bold outlined titles via PIL; storyboard UI to preview/download. **Verified live: real SD-Turbo thumbnail composited offline in 47s, $0.**
- [x] **Fully-offline image pipeline** — `sdcpp` local SD-Turbo replaces the cloud image dependency; the whole §5 happy path now runs with zero network.
- [x] **Shorts smart auto-reframe** (`app/reframe.py`): content-aware (gradient-energy + center-bias) crop to the export aspect — vertical Shorts keep the subject framed instead of stretching 16:9→9:16. Wired into `compose` (`smart_reframe` flag) + `GET /shots/{id}/reframe` preview + export-panel toggle. numpy/PIL only (no OpenCV/torch). **Verified live: real 1080×1920 Shorts MP4; crop follows the character on real SD-Turbo art.**
- [x] Dockerfile + compose (cpu/gpu profiles) for reproducibility + GPU-upgrade portability *(written; unverified — no Docker on the dev box)*
- [ ] Harmony stacking (SVS, GPU)

## GPU upgrade switch  ◑ providers built; runtime-test pending a GPU
The moment a CUDA box (local or rented RTX 4090) is available, the GPU stack activates with
**zero app code changes** — `docker compose --profile gpu up` (see `docs/GPU_DEPLOY.md`).
- [x] `flux_local` — FLUX.1-schnell images (diffusers `FluxPipeline`, Apache-2.0)
- [x] `ltx_local` — LTX-Video **true img→video** (diffusers `LTXImageToVideoPipeline`), wired into `compose` with automatic Ken Burns fallback
- [x] `xtts_local` — XTTS-v2 voice cloning (Coqui; non-commercial model license). **CPU-capable** (free, slow) — auto-uses a GPU if present.
- [x] `musicgen_local` — MusicGen text→music (transformers; non-commercial). **CPU-capable** (free, slow) — runs locally with no GPU via the `cpu-ml` Docker profile / `requirements-ml-cpu.txt`.
- [x] Infra: `requirements-gpu.txt`, `Dockerfile.gpu` (pytorch/cuda base), `backend-gpu` compose profile, `GPU_USD_PER_HOUR` cost meter, graceful no-GPU availability (**66 tests pass offline**)
- [x] `acestep_local` — **ACE-Step real singing** (lyrics → sung vocals+music, SVS provider) + `sadtalker_local` — **real lip-sync** (shells out to SadTalker inference). Built against documented APIs; GPU-run-pending.
- [x] **Free-GPU render path** (`scripts/gpu_render.py` + `notebooks/toonforge_gpu.ipynb` + `docs/FREE_GPU.md`): prompt → ACE-Step song → Cloudflare-Flux keyframes → LTX animation (or SadTalker lip-sync) → assembled MP4, run on a **free Kaggle/Colab/Lightning GPU** (rotate when quota runs out). 110 tests pass offline.
- [ ] Runtime verification on an actual GPU (can't be tested on the dev box — no NVIDIA card)
