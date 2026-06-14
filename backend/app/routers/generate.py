"""One-shot: a topic prompt → a complete song-video project (lyrics+chorus, characters,
scenes). The LLM writes the song; the local pipeline builds the rest. This generalizes the
app well beyond nursery rhymes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import foundry, kaggle_render, lore, models, safety, scene, songwriter, usage
from ..jobs import queue
from ..providers.base import Capability
from ..providers.registry import ProviderUnavailable, get_provider
from ..schemas import FromPromptRequest, GpuVideoRequest

router = APIRouter(tags=["generate"])


@router.get("/generate/gpu-video/availability")
async def gpu_video_availability() -> dict:
    """Whether the app can drive a Kaggle GPU (CLI installed + API token present)."""
    ok, hint = kaggle_render.availability()
    return {"available": ok, "hint": hint, "kernel": kaggle_render.kernel_slug() if ok else None}


@router.post("/generate/gpu-video")
async def gpu_video(body: GpuVideoRequest) -> dict:
    """Type a prompt → the app runs the full sung+animated render on a free Kaggle GPU and saves
    the MP4 back as a project asset. Returns a job; poll GET /jobs/{id} for progress (~30-40 min)."""
    if body.style_preset not in foundry.STYLE_PRESETS:
        raise HTTPException(422, f"unknown style_preset; choose from {list(foundry.STYLE_PRESETS)}")
    ip = safety.check_ip(body.prompt)
    if not ip.ok:
        raise HTTPException(422, {"error": ip.reason, "matched": list(ip.matched)})
    ok, hint = kaggle_render.availability()
    if not ok:
        raise HTTPException(503, hint)
    job = queue.enqueue("gpu_video", {
        "prompt": body.prompt, "style_preset": body.style_preset,
        "scenes": body.scenes, "project_id": body.project_id,
    }, project_id=body.project_id, max_attempts=1)   # one Kaggle run; don't auto-retry a 40-min job
    return {"job": job, "kernel": kaggle_render.kernel_slug(),
            "note": "Rendering on a free Kaggle GPU — this takes ~30-40 min. Poll the job for progress.",
            "usage_warning": usage.kaggle_warning(), "usage": usage.summary()}


@router.post("/generate/from-prompt")
async def from_prompt(body: FromPromptRequest) -> dict:
    if body.style_preset not in foundry.STYLE_PRESETS:
        raise HTTPException(422, f"unknown style_preset; choose from {list(foundry.STYLE_PRESETS)}")

    ip = safety.check_ip(body.prompt)
    if not ip.ok:
        raise HTTPException(422, {"error": ip.reason, "matched": list(ip.matched)})
    if body.safe_mode and not safety.check_safe_mode(body.prompt).ok:
        raise HTTPException(422, {"error": "Blocked by safe mode.", "prompt": body.prompt})

    try:
        get_provider(Capability.LLM)                      # 503 with a clear hint if no key
    except ProviderUnavailable as e:
        raise HTTPException(503, str(e))

    # 1. LLM writes the song (lyrics + repeated chorus + characters + scene lines)
    try:
        song = await songwriter.write_song(body.prompt, language=body.language,
                                           style=body.style_preset, scenes=body.scenes)
    except ValueError as e:
        raise HTTPException(502, f"songwriting failed (bad LLM output): {e}")
    except RuntimeError as e:           # rate-limited / API error -> retryable
        raise HTTPException(503, str(e))

    # 2. project
    project = models.create_project(song["title"], style_preset=body.style_preset,
                                    language=body.language, safe_mode=body.safe_mode)

    # 3. characters (+ lore, + background sheet generation), skipping any IP-flagged design
    name_to_id: dict[str, str] = {}
    char_jobs: list[dict] = []
    for c in song["characters"]:
        if not safety.check_ip(c["name"], c["description"]).ok:
            continue
        ch = models.create_character(
            project["id"], c["name"], c["description"], style_preset=body.style_preset,
            lore=lore.generate_lore(c["name"], c["description"],
                                    style_preset=body.style_preset, language=body.language),
        )
        name_to_id[c["name"]] = ch["id"]
        if body.render:
            char_jobs.append(queue.enqueue(
                "character_sheets",
                {"character_id": ch["id"], "sheets": ["turnaround", "expressions", "poses"]},
                project_id=project["id"]))

    # 4. shots from the lyric lines (chorus gets an energetic camera)
    for idx, line in enumerate(song["lines"]):
        char_ids = [name_to_id[n] for n in line["characters"] if n in name_to_id]
        camera = "bounce_in" if line["section"] == "chorus" else scene._pick_camera(line["text"], idx)
        models.create_shot(project["id"], idx, line["text"], characters=char_ids,
                           camera=camera, background=body.default_background,
                           duration_s=scene._duration_for(line["text"]))

    shots = models.list_where("shots", "project_id = ?", (project["id"],), "idx ASC")
    return {"project": project, "song": song, "shots": shots,
            "characters": list(name_to_id.values()), "character_jobs": char_jobs}
