# ToonForge — Architecture

## Guiding constraint
Single-user, **local-first**, **free**, **no NVIDIA GPU** (Intel Iris Xe, CPU-only). Therefore:
- No Postgres/Redis/Celery/S3/Docker at this stage. SQLite + local filesystem + in-process async worker.
- GPU-bound capabilities (image, video, SVS, lip-sync) route to **free cloud providers** behind the same interfaces; local GPU implementations drop in unchanged later.

## The provider abstraction (the moat)
`app/providers/base.py` declares one ABC per capability:

| Interface | Method | Local impl (CPU) | Cloud / future impl |
|---|---|---|---|
| `ImageProvider` | `generate()` | — | `pollinations` (free), `higgsfield`, `flux_local` (GPU) |
| `TTSProvider` | `synthesize()` | `piper` | `xtts_local` (GPU) |
| `SVSProvider` | `sing()` | — | `diffsinger_local` (GPU) |
| `MusicProvider` | `compose()` | `symbolic` | `musicgen_local` (GPU) |
| `VideoProvider` | `animate()` | — | `higgsfield`, `ltx_local` (GPU) |
| `LipSyncProvider` | `apply()` | — | `sadtalker_local` (GPU) |
| `AlignProvider` | `align()` | `faster_whisper` | — |
| `ConsistencyProvider` | `embed()` / `similarity()` / `palette_similarity()` | `phash` | `clip_local` / `arcface_local` (GPU) |
| `StorageProvider` | `put()` / `path()` | `local_fs` | `s3` (future) |
| `AssemblyProvider` | `mux()` / `burn_subs()` | `ffmpeg` | — |

Every provider exposes `availability()` → `Availability(available, reason, install_hint)` and `estimate_cost()` → `{gpu_seconds, usd}`. `registry.py` reads `PROVIDER_<CAP>` from env, instantiates the chosen provider, and falls back to the next available one if it's not ready. **Nothing hard-crashes on a missing model** — it reports why.

## Data model (SQLite — see `app/db.py`)
- `projects` — top-level container (style preset, language, fps, resolution).
- `characters` — Character Cards: prompt, palette hex, style tokens, negative prompts, embedding ref, turnaround/expression/pose asset ids (JSON).
- `voices` — voice presets / clones (consent record, language, age, params).
- `shots` — ordered script beats: text, characters present, camera move, background ref, duration, keyframe asset, clip asset.
- `assets` — every generated/imported file: path, kind, mime, sha256, provider, cost, metadata JSON.
- `jobs` — queue: type, status, progress, payload JSON, result JSON, attempts, error, timestamps.
- `embeddings` — pHash/CLIP vectors as BLOB + dim + space, linked to asset/character (pgvector replacement; cosine/Hamming in `numpy`).

Upgrade path: the schema maps 1:1 to Postgres; `embeddings` → `pgvector`; `assets.path` → S3 keys.

## Job orchestration
`app/jobs/queue.py` persists jobs in SQLite. `app/jobs/worker.py` is an asyncio loop launched on FastAPI startup: it claims `queued` jobs, dispatches by `type` to a handler in `handlers.py`, streams progress, retries failed jobs ×2, then marks `failed` with a one-click-fix payload. Per-shot result caching keys on `(shot_id, prompt_hash, provider)` so unchanged shots never re-render. Progress is pushed to clients via SSE (`/jobs/{id}/stream`).

## Request flow (Character Foundry, implemented)
1. `POST /characters` → IP/safe-mode guard → creates a Character Card + enqueues a `character_sheets` job (sheets: turnaround / expressions / poses).
2. Worker → for each sheet item, `foundry.build_character_prompt()` (identity + palette + style + edits) → `ImageProvider.generate()` → palette-drift check vs the identity (front) view, auto-regenerate below threshold → `StorageProvider.put()` → record `assets` + pHash `embeddings` → write `sheets` + `consistency` report to the Card.
3. `POST /characters/{id}/edit` ("change her shirt to green") appends an edit and re-runs sheets with the edit injected into the prompt.
4. Client polls `GET /jobs/{id}` or subscribes to `/jobs/{id}/stream`; `GET /characters/{id}/consistency` returns the drift report; `GET /assets/{id}` serves the image.
5. `PROVIDER_IMAGE=mock` swaps in a deterministic offline generator for tests.

## Scene Engine (`app/scene.py` + `shot_keyframe` job, implemented)
1. `POST /projects/{id}/plan` → `scene.plan_script()` segments the script into shots (detects which characters are named, assigns a camera motion preset, estimates duration from word count, sets a default background) and persists them.
2. `POST /projects/{id}/render-keyframes` enqueues a `shot_keyframe` job per shot. The handler resolves the shot's characters, builds a **locked prompt** via `scene.build_shot_prompt()` (every present character's identity + palette + the background + the camera hint + project style), then:
   - **render cache:** if `prompt_hash` is unchanged and a keyframe exists, it returns the cached one — unchanged shots never re-render.
   - **continuity:** if the previous shot shares the background, its keyframe is passed as a reference image (used by providers that support img2img).
   - **drift check:** palette similarity of the keyframe vs the primary character's turnaround sheet is recorded on the asset.
3. Free CPU animation: `ffmpeg_kenburns` VideoProvider turns a keyframe into a pan/zoom clip per the motion preset (needs FFmpeg). GPU/cloud img2video (Higgsfield/LTX) sits behind the same `VideoProvider` interface.
4. Storyboard UI at `/projects/[id]/storyboard`.

## Composer / Export (`app/compose.py` + `episode_assemble` job, implemented)
Turns a storyboard into a finished MP4, CPU-only via the local FFmpeg (`backend/tools/ffmpeg`,
resolved by `app/ffmpeg_util.py`): per shot it renders a Ken Burns clip of the keyframe with the
shot's Piper voiceover (or silence), concatenates the segments, builds an SRT from shot timing,
burns it in, and exports at a preset (`youtube_1080p` / `youtube_4k` / `shorts_1080x1920`). Each
ffmpeg call runs with `cwd` = a temp dir using relative filenames to avoid Windows path-escaping.
`GET /projects/{id}/cost` sums GPU-seconds and $ across assets (the cost meter). Verified live:
1920×1080 H.264+AAC with voice + burned subtitles.

## Frontend (`frontend/`, built)
Next.js 15 (App Router) + TypeScript, hand-rolled minimal CSS (no Tailwind/shadcn yet — keeps the
install tiny and deterministic). Three routes: `/` (projects + live provider-readiness), `/projects/[id]`
(Character Foundry create form: style preset, palette, sheet selection), `/characters/[id]` (live job
progress, turnaround/expression/pose galleries, palette-drift consistency report, instruction edits).
Talks to the API via `lib/api.ts` (`NEXT_PUBLIC_API_BASE`). The episode-timeline editor (PixiJS/WebCodecs)
comes with the Composer phase.
