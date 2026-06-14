"""Job handlers. Each handler turns a queued job into real assets using providers.

Implemented: `character_sheets` (Character Foundry — turnaround + expression + pose sheets
with perceptual-hash drift auto-regeneration and a consistency report). New job types
(shot_keyframe, voice_tts, episode_assemble, ...) register here as later phases land.
"""
from __future__ import annotations

import asyncio
import hashlib
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .. import compose, foundry, ip_guard, kaggle_render, models, scene, thumbnail
from ..config import settings
from ..providers.base import Capability, GenResult
from ..providers.registry import get_provider
from . import queue

_MAX_REGEN = 3  # attempts to beat the drift threshold before keeping the best


class JobContext:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id

    def progress(self, value: float, message: str = "") -> None:
        queue.set_progress(self.job_id, value, message)


async def _generate_consistent(image, *, prompt: str, negative: str, base_seed: int,
                               identity_bytes: bytes | None, consistency, threshold: float,
                               extra_kw: dict) -> tuple[GenResult, float, int]:
    """Generate, and if it drifts from the identity below threshold, retry with a new
    seed; keep the best-scoring attempt. Returns (result, score, attempts)."""
    best: GenResult | None = None
    best_score = -1.0
    attempts = 0
    for attempt in range(_MAX_REGEN):
        attempts = attempt + 1
        result = await image.generate(prompt, negative=negative, width=768, height=1024,
                                      seed=base_seed + attempt, **extra_kw)
        if identity_bytes is None or consistency is None:
            return result, 1.0, attempts
        # palette similarity is robust to pose/view, so it's the cross-view identity signal
        score = consistency.palette_similarity(identity_bytes, result.data)
        if score > best_score:
            best, best_score = result, score
        if score >= threshold:
            return result, score, attempts
    assert best is not None
    return best, best_score, attempts


async def handle_character_sheets(job: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    payload = job["payload"]
    character_id = payload["character_id"]
    which = payload.get("sheets") or ["turnaround", "expressions", "poses"]
    character = models.get("characters", character_id)
    if character is None:
        raise ValueError(f"character {character_id} not found")

    image = get_provider(Capability.IMAGE)
    storage = get_provider(Capability.STORAGE)
    consistency = get_provider(Capability.CONSISTENCY, required=False)

    negative = character.get("negative_prompt", "")
    seed = foundry.identity_seed(character_id)
    threshold = settings.consistency_min_score
    model_hint = (settings.sd_anime_model
                  if str(character.get("style_preset", "")).startswith("anime") else "")

    items = list(foundry.all_sheet_items(which))
    total = len(items)
    identity_bytes: bytes | None = None
    identity_embedding_id: str | None = character.get("embedding_id")

    sheets: dict[str, Any] = dict(character.get("sheets") or {})
    turnaround_ids: list[str] = []
    scores: dict[str, float] = {}
    regenerated: dict[str, int] = {}

    for i, (sheet, key, fragment, framing) in enumerate(items):
        ctx.progress(i / total, f"{sheet}:{key}")
        prompt = foundry.build_character_prompt(character, pose=fragment, framing=framing)
        result, score, attempts = await _generate_consistent(
            image, prompt=prompt, negative=negative, base_seed=seed + i * 100,
            identity_bytes=identity_bytes, consistency=consistency, threshold=threshold,
            extra_kw={"identity_key": character_id, "model_hint": model_hint},
        )

        ext = "png" if "png" in result.mime else "jpg"
        rel = storage.put(result.data, name=f"{key}.{ext}",
                          subdir=f"characters/{character_id}/{sheet}")
        asset = models.create_asset(
            kind="image", path=rel, project_id=character["project_id"],
            mime=result.mime, sha256=hashlib.sha256(result.data).hexdigest(),
            provider=result.meta.get("provider"), cost_usd=result.cost.usd,
            gpu_seconds=result.cost.gpu_seconds,
            meta={"sheet": sheet, "key": key, "character_id": character_id,
                  "consistency_score": score},
        )

        if consistency is not None:
            space, dim, vec = consistency.embed(result.data)
            emb = models.create_embedding(space=space, dim=dim, vector=vec,
                                          asset_id=asset["id"], character_id=character_id)
            if identity_bytes is None:
                identity_embedding_id = emb["id"]

        if identity_bytes is None:
            identity_bytes = result.data  # first generated item is the identity reference
        else:
            scores[f"{sheet}:{key}"] = round(score, 4)
            if attempts > 1:
                regenerated[f"{sheet}:{key}"] = attempts

        # place into the right sheet bucket
        if sheet == "turnaround":
            turnaround_ids.append(asset["id"])
        else:
            sheets.setdefault(sheet, {})[key] = asset["id"]

    if turnaround_ids:
        sheets["turnaround"] = turnaround_ids

    min_score = min(scores.values()) if scores else 1.0
    consistency_report = {
        "threshold": threshold,
        "method": "palette_similarity" if consistency else None,
        "space": consistency.info.name if consistency else None,
        "identity_view": items[0][1] if items else None,
        "scores": scores,
        "min_score": round(min_score, 4),
        "passed": min_score >= threshold,
        "regenerated": regenerated,
    }

    changes: dict[str, Any] = {"sheets": sheets, "consistency": consistency_report}
    # IP-similarity image guard (spec §A.7): flag outputs that *look like* a known IP.
    # No-op unless the consistency provider does CLIP zero-shot (graceful on the pHash default).
    if identity_bytes is not None and consistency is not None:
        ip = ip_guard.check_image(identity_bytes, consistency,
                                  threshold=settings.ip_guard_threshold)
        if ip.get("available"):
            consistency_report["ip_guard"] = ip
            changes["ip_flagged"] = 1 if ip.get("flagged") else 0
    if identity_embedding_id:
        changes["embedding_id"] = identity_embedding_id
    models.update("characters", character_id, changes)

    ctx.progress(1.0, "sheets complete")
    return {"character_id": character_id, "sheets": list(which),
            "consistency": consistency_report}


def _keyframe_dims(project: dict[str, Any]) -> tuple[int, int]:
    w, h = project["width"], project["height"]
    long = 1024
    if w >= h:
        return long, max(8, round(long * h / w / 8) * 8)
    return max(8, round(long * w / h / 8) * 8), long


def _identity_front_bytes(character: dict[str, Any], storage) -> bytes | None:
    turn = (character.get("sheets") or {}).get("turnaround") or []
    if not turn:
        return None
    asset = models.get("assets", turn[0])
    if not asset:
        return None
    try:
        return storage.open(asset["path"])
    except OSError:
        return None


async def handle_shot_keyframe(job: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    payload = job["payload"]
    shot = models.get("shots", payload["shot_id"])
    if shot is None:
        raise ValueError(f"shot {payload['shot_id']} not found")
    project = models.get("projects", shot["project_id"])
    force = bool(payload.get("force"))

    image = get_provider(Capability.IMAGE)
    storage = get_provider(Capability.STORAGE)
    consistency = get_provider(Capability.CONSISTENCY, required=False)

    char_list = models.list_where("characters", "project_id = ?", (shot["project_id"],))
    char_map = {c["id"]: c for c in char_list}

    ctx.progress(0.1, "building locked prompt")
    prompt = scene.build_shot_prompt(shot, char_map, project)
    key = scene.prompt_hash(prompt, image.info.name)

    # render cache — never re-render an unchanged shot (spec §D)
    if not force and shot.get("prompt_hash") == key and shot.get("keyframe_id"):
        if models.get("assets", shot["keyframe_id"]):
            ctx.progress(1.0, "cached")
            return {"shot_id": shot["id"], "keyframe_id": shot["keyframe_id"], "cached": True}

    present = [char_map[cid] for cid in shot.get("characters", []) if cid in char_map]
    primary = present[0] if present else None
    seed = (foundry.identity_seed(primary["id"]) if primary
            else foundry.identity_seed(shot["id"])) + shot["idx"]

    # continuity: seed the next shot with the previous shot's keyframe when same background
    refs: list[bytes] = []
    prev = models.list_where("shots", "project_id = ? AND idx = ?",
                             (shot["project_id"], shot["idx"] - 1))
    if prev and prev[0].get("keyframe_id") and prev[0].get("background") == shot.get("background"):
        prev_asset = models.get("assets", prev[0]["keyframe_id"])
        if prev_asset:
            try:
                refs.append(storage.open(prev_asset["path"]))
            except OSError:
                pass

    w, h = _keyframe_dims(project)
    style = (primary or {}).get("style_preset") or project.get("style_preset", "")
    model_hint = settings.sd_anime_model if str(style).startswith("anime") else ""
    ctx.progress(0.3, "generating keyframe")
    result = await image.generate(
        prompt, negative=(primary or {}).get("negative_prompt", ""),
        width=w, height=h, seed=seed,
        reference_images=refs or None,
        identity_key=(primary["id"] if primary else shot["id"]),
        model_hint=model_hint,
    )

    ext = "png" if "png" in result.mime else "jpg"
    rel = storage.put(result.data, name=f"keyframe.{ext}",
                      subdir=f"shots/{shot['project_id']}/{shot['id']}")

    # cross-shot character persistence check (spec §6) vs the character's identity sheet
    drift = None
    if consistency is not None and primary is not None:
        front = _identity_front_bytes(primary, storage)
        if front is not None:
            drift = round(consistency.palette_similarity(front, result.data), 4)

    asset = models.create_asset(
        kind="image", path=rel, project_id=shot["project_id"], mime=result.mime,
        sha256=hashlib.sha256(result.data).hexdigest(),
        provider=result.meta.get("provider"), cost_usd=result.cost.usd,
        gpu_seconds=result.cost.gpu_seconds,
        meta={"shot_id": shot["id"], "kind": "keyframe", "seed": seed,
              "character_drift": drift, "continuity_ref": bool(refs)},
    )
    models.update("shots", shot["id"], {
        "keyframe_id": asset["id"], "prompt_hash": key, "status": "keyframed",
    })
    ctx.progress(1.0, "keyframe ready")
    return {"shot_id": shot["id"], "keyframe_id": asset["id"], "cached": False,
            "character_drift": drift}


async def handle_episode_assemble(job: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    payload = job["payload"]
    project = models.get("projects", payload["project_id"])
    if project is None:
        raise ValueError("project not found")
    shots = models.list_where("shots", "project_id = ?", (project["id"],), "idx ASC")
    result = await compose.assemble_episode(
        project, shots,
        voice=payload.get("voice", True), sing=payload.get("sing", False),
        sing_vibrato=payload.get("sing_vibrato", 0.3),
        key_override=payload.get("sing_key", "auto"),
        tempo_override=payload.get("sing_tempo", 0),
        lipsync=payload.get("lipsync", False),
        subtitles=payload.get("subtitles", True),
        word_subtitles=payload.get("word_subtitles", True),
        music=payload.get("music", False),
        music_auto=payload.get("music_auto", True),
        music_description=payload.get("music_description",
                                      "gentle cheerful children's nursery music"),
        music_tempo=payload.get("music_tempo", 96),
        preset=payload.get("preset", "youtube_1080p"),
        smart_reframe=payload.get("smart_reframe", True),
        grade=payload.get("grade", "none"),
        progress=lambda f, m: ctx.progress(f, m),
    )
    ctx.progress(1.0, "episode ready")
    return result


async def handle_thumbnails(job: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    payload = job["payload"]
    project = models.get("projects", payload["project_id"])
    if project is None:
        raise ValueError("project not found")

    characters = models.list_where("characters", "project_id = ?", (project["id"],))
    character = None
    if payload.get("character_id"):
        character = next((c for c in characters if c["id"] == payload["character_id"]), None)
    character = character or (characters[0] if characters else None)

    title = payload.get("title") or thumbnail.default_title(project)
    count = int(payload.get("count", 3))
    variants = thumbnail.build_variants(project, character, title, count,
                                        background=payload.get("background", ""))

    image = get_provider(Capability.IMAGE)
    storage = get_provider(Capability.STORAGE)
    style = (character or {}).get("style_preset") or project.get("style_preset", "")
    model_hint = settings.sd_anime_model if str(style).startswith("anime") else ""

    thumbs: list[dict[str, Any]] = []
    for i, v in enumerate(variants):
        ctx.progress(i / len(variants), f"thumbnail {i + 1}/{len(variants)}")
        result = await image.generate(
            v["prompt"], negative=v["negative"],
            width=thumbnail.THUMB_W, height=thumbnail.THUMB_H, seed=v["seed"],
            identity_key=(character["id"] if character else project["id"]),
            model_hint=model_hint,
        )
        png = thumbnail.compose(result.data, v["title"], subject_side=v["subject_side"],
                                accent=tuple(v["accent"]), text_side=v["text_side"])
        rel = storage.put(png, name=f"thumb_{i}.png", subdir=f"thumbnails/{project['id']}")
        asset = models.create_asset(
            kind="thumbnail", path=rel, project_id=project["id"], mime="image/png",
            sha256=hashlib.sha256(png).hexdigest(), provider=result.meta.get("provider"),
            cost_usd=result.cost.usd, gpu_seconds=result.cost.gpu_seconds,
            meta={"title": v["title"], "variant": i, "emotion": v["emotion"],
                  "character_id": character["id"] if character else None},
        )
        thumbs.append({"asset_id": asset["id"], "variant": i, "title": v["title"]})

    ctx.progress(1.0, "thumbnails ready")
    return {"project_id": project["id"], "thumbnails": thumbs, "count": len(thumbs)}


async def handle_gpu_video(job: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    """Dispatch the full prompt->sung+animated MP4 render to a free Kaggle GPU, poll until it
    finishes (~30-40 min), then download the video and save it as a project asset. The GPU work
    (ACE-Step singing + LTX animation) can't run on this no-GPU machine, so it runs on Kaggle's
    hardware via a private batch kernel (ToS-safe). One worker is busy for the whole render."""
    payload = job["payload"]
    prompt = payload["prompt"]
    style = payload.get("style_preset", "anime_cyberpunk")
    scenes = int(payload.get("scenes", 6))
    project_id = payload.get("project_id")

    ok, hint = kaggle_render.availability()
    if not ok:
        raise RuntimeError(hint)

    ctx.progress(0.03, "dispatching render to Kaggle GPU…")
    slug = await asyncio.to_thread(kaggle_render.dispatch, prompt, style, scenes)
    ctx.progress(0.08, f"queued on Kaggle ({slug}) — this takes ~30-40 min")

    loop = asyncio.get_event_loop()
    start = loop.time()
    await asyncio.sleep(min(20.0, settings.kaggle_poll_interval_s))  # let the new run register
    last = "queued"
    while True:
        st = await asyncio.to_thread(kaggle_render.status, slug)
        if st.state != "unknown":
            last = st.state
        if st.done:
            if not st.ok:
                raise RuntimeError(f"Kaggle render ended in state '{st.state}'. Open the kernel "
                                   f"on kaggle.com to see the log. {st.message[:300]}")
            break
        elapsed = loop.time() - start
        if elapsed > settings.kaggle_timeout_s:
            raise RuntimeError(f"Kaggle render timed out after {int(elapsed)}s (last state: {last})")
        ctx.progress(min(0.9, 0.1 + 0.8 * elapsed / settings.kaggle_timeout_s), f"Kaggle GPU: {last}…")
        await asyncio.sleep(settings.kaggle_poll_interval_s)

    ctx.progress(0.92, "downloading the finished video from Kaggle…")
    with tempfile.TemporaryDirectory() as tmp:
        mp4 = await asyncio.to_thread(kaggle_render.fetch_output, Path(tmp), slug)
        if mp4 is None:
            raise RuntimeError("Kaggle run completed but no song.mp4 was found in its output.")
        data = mp4.read_bytes()

    storage = get_provider(Capability.STORAGE)
    rel = storage.put(data, name="song.mp4", subdir=f"gpu_video/{project_id or 'adhoc'}")
    asset = models.create_asset(
        kind="video", path=rel, project_id=project_id, mime="video/mp4",
        sha256=hashlib.sha256(data).hexdigest(), provider="kaggle:acestep+ltx",
        meta={"prompt": prompt, "style": style, "scenes": scenes, "kernel": slug,
              "source": "kaggle_gpu"},
    )
    ctx.progress(1.0, "video ready")
    return {"asset_id": asset["id"], "path": rel, "kernel": slug, "bytes": len(data)}


HANDLERS: dict[str, Callable[[dict[str, Any], JobContext], Awaitable[dict[str, Any]]]] = {
    "character_sheets": handle_character_sheets,
    "shot_keyframe": handle_shot_keyframe,
    "episode_assemble": handle_episode_assemble,
    "thumbnails": handle_thumbnails,
    "gpu_video": handle_gpu_video,
}
