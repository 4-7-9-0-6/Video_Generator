"""Export + cost endpoints (spec Module D / §6 cost transparency)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import compose, models, music_brief
from ..jobs import queue
from ..schemas import ExportRequest

router = APIRouter(tags=["export"])


@router.get("/export/presets")
def export_presets() -> dict:
    return {name: {"width": w, "height": h} for name, (w, h) in compose.EXPORT_PRESETS.items()}


@router.post("/projects/{project_id}/export")
def export_episode(project_id: str, body: ExportRequest) -> dict:
    if models.get("projects", project_id) is None:
        raise HTTPException(404, "project not found")
    if body.preset not in compose.EXPORT_PRESETS:
        raise HTTPException(422, f"preset must be one of {list(compose.EXPORT_PRESETS)}")
    shots = models.list_where("shots", "project_id = ? AND keyframe_id IS NOT NULL", (project_id,))
    if not shots:
        raise HTTPException(409, "no shots have keyframes yet — render keyframes first")
    return queue.enqueue("episode_assemble", {
        "project_id": project_id, "preset": body.preset,
        "voice": body.voice, "sing": body.sing, "subtitles": body.subtitles,
        "sing_key": body.sing_key, "sing_tempo": body.sing_tempo,
        "sing_vibrato": body.sing_vibrato, "lipsync": body.lipsync,
        "word_subtitles": body.word_subtitles, "music": body.music,
        "music_auto": body.music_auto, "music_description": body.music_description,
        "music_tempo": body.music_tempo, "smart_reframe": body.smart_reframe,
    }, project_id=project_id)


@router.get("/projects/{project_id}/music-brief")
def music_brief_for_project(project_id: str) -> dict:
    """Preview the music the app will auto-pick from this project's lyrics (mood/tempo/key)."""
    if models.get("projects", project_id) is None:
        raise HTTPException(404, "project not found")
    shots = models.list_where("shots", "project_id = ?", (project_id,), "idx ASC")
    lyrics = " ".join(s.get("text", "") for s in shots)
    return music_brief.music_brief(lyrics)


@router.get("/projects/{project_id}/cost")
def project_cost(project_id: str) -> dict:
    if models.get("projects", project_id) is None:
        raise HTTPException(404, "project not found")
    assets = models.list_where("assets", "project_id = ?", (project_id,))
    by_kind: dict[str, int] = {}
    gpu = usd = 0.0
    for a in assets:
        by_kind[a["kind"]] = by_kind.get(a["kind"], 0) + 1
        gpu += a.get("gpu_seconds", 0) or 0
        usd += a.get("cost_usd", 0) or 0
    return {"assets": len(assets), "by_kind": by_kind,
            "gpu_seconds": round(gpu, 2), "usd": round(usd, 4),
            "note": "0 cost on the free local/CPU stack"}
