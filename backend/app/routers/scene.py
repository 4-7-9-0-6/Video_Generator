"""Scene Engine endpoints (spec Module C): plan a script into shots, edit shots,
and render keyframes with the character identity locked."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from .. import compose, models, reframe, scene
from ..config import settings
from ..jobs import queue
from ..providers.base import Capability
from ..providers.registry import get_provider
from ..schemas import PlanRequest, ReorderRequest, ShotInsert, ShotPatch

router = APIRouter(tags=["scene"])


def _project_or_404(project_id: str) -> dict:
    project = models.get("projects", project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return project


def _char_map(project_id: str) -> dict:
    return {c["id"]: c for c in models.list_where("characters", "project_id = ?", (project_id,))}


def _is_stale(shot: dict, project: dict, char_map: dict) -> bool:
    """A shot needs (re)rendering if it has no keyframe or its prompt has changed
    since the keyframe was made (e.g. the transcript line was edited)."""
    if not shot.get("keyframe_id"):
        return True
    expected = scene.prompt_hash(scene.build_shot_prompt(shot, char_map, project),
                                 settings.providers.get("image", ""))
    return shot.get("prompt_hash") != expected


def _reindex(order_ids: list[str]) -> None:
    for i, sid in enumerate(order_ids):
        models.update("shots", sid, {"idx": i})


@router.post("/projects/{project_id}/plan")
def plan(project_id: str, body: PlanRequest) -> list[dict]:
    _project_or_404(project_id)
    characters = models.list_where("characters", "project_id = ?", (project_id,))
    proposals = scene.plan_script(body.script, characters,
                                  default_background=body.default_background)
    if body.replace:
        for old in models.list_where("shots", "project_id = ?", (project_id,)):
            models.delete("shots", old["id"])
    created = [
        models.create_shot(project_id, p["idx"], p["text"], characters=p["characters"],
                           camera=p["camera"], background=p["background"],
                           duration_s=p["duration_s"])
        for p in proposals
    ]
    return created


@router.get("/projects/{project_id}/shots")
def list_shots(project_id: str) -> list[dict]:
    _project_or_404(project_id)
    return models.list_where("shots", "project_id = ?", (project_id,), "idx ASC")


@router.get("/shots/{shot_id}")
def get_shot(shot_id: str) -> dict:
    shot = models.get("shots", shot_id)
    if shot is None:
        raise HTTPException(404, "shot not found")
    return shot


@router.patch("/shots/{shot_id}")
def patch_shot(shot_id: str, body: ShotPatch) -> dict:
    shot = models.get("shots", shot_id)
    if shot is None:
        raise HTTPException(404, "shot not found")
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if "camera" in changes and changes["camera"] not in scene.MOTION_PRESETS:
        raise HTTPException(422, f"camera must be one of {list(scene.MOTION_PRESETS)}")
    return models.update("shots", shot_id, changes)


@router.post("/shots/{shot_id}/keyframe")
def render_keyframe(shot_id: str, force: bool = False) -> dict:
    shot = models.get("shots", shot_id)
    if shot is None:
        raise HTTPException(404, "shot not found")
    return queue.enqueue("shot_keyframe", {"shot_id": shot_id, "force": force},
                         project_id=shot["project_id"])


@router.post("/projects/{project_id}/render-keyframes")
def render_all_keyframes(project_id: str, force: bool = False) -> list[dict]:
    project = _project_or_404(project_id)
    char_map = _char_map(project_id)
    shots = models.list_where("shots", "project_id = ?", (project_id,), "idx ASC")
    jobs = []
    for shot in shots:
        # render shots that are new or whose transcript line changed (stale); the job's
        # own cache also no-ops anything unchanged that slips through.
        if force or _is_stale(shot, project, char_map):
            jobs.append(queue.enqueue("shot_keyframe",
                                      {"shot_id": shot["id"], "force": force},
                                      project_id=project_id))
    return jobs


# ---------- transcript-driven editing (spec §D) ----------

@router.get("/projects/{project_id}/transcript")
def get_transcript(project_id: str) -> dict:
    project = _project_or_404(project_id)
    char_map = _char_map(project_id)
    shots = models.list_where("shots", "project_id = ?", (project_id,), "idx ASC")
    lines = []
    t = 0.0
    for s in shots:
        dur = float(s.get("duration_s") or 4.0)
        lines.append({
            "id": s["id"], "idx": s["idx"], "text": s["text"],
            "characters": s["characters"], "camera": s["camera"],
            "background": s["background"], "duration_s": dur,
            "start_s": round(t, 2), "end_s": round(t + dur, 2),
            "has_keyframe": bool(s.get("keyframe_id")),
            "stale": _is_stale(s, project, char_map),
        })
        t += dur
    return {"shots": lines, "count": len(lines), "total_duration_s": round(t, 2)}


@router.post("/projects/{project_id}/shots")
def insert_shot(project_id: str, body: ShotInsert) -> dict:
    _project_or_404(project_id)
    if body.camera not in scene.MOTION_PRESETS:
        raise HTTPException(422, f"camera must be one of {list(scene.MOTION_PRESETS)}")
    shots = models.list_where("shots", "project_id = ?", (project_id,), "idx ASC")
    new = models.create_shot(project_id, len(shots), body.text,
                             characters=body.characters, camera=body.camera,
                             background=body.background, duration_s=body.duration_s)
    order = [s["id"] for s in shots]
    pos = order.index(body.after_id) + 1 if body.after_id in order else len(order)
    order.insert(pos, new["id"])
    _reindex(order)
    return models.get("shots", new["id"])


@router.delete("/shots/{shot_id}")
def delete_shot(shot_id: str) -> dict:
    shot = models.get("shots", shot_id)
    if shot is None:
        raise HTTPException(404, "shot not found")
    project_id = shot["project_id"]
    models.delete("shots", shot_id)
    remaining = models.list_where("shots", "project_id = ?", (project_id,), "idx ASC")
    _reindex([s["id"] for s in remaining])
    return {"deleted": shot_id, "count": len(remaining)}


@router.post("/projects/{project_id}/transcript/reorder")
def reorder_shots(project_id: str, body: ReorderRequest) -> list[dict]:
    _project_or_404(project_id)
    ids = {s["id"] for s in models.list_where("shots", "project_id = ?", (project_id,))}
    if set(body.order) != ids:
        raise HTTPException(422, "order must be a full permutation of the project's shot ids")
    _reindex(body.order)
    return models.list_where("shots", "project_id = ?", (project_id,), "idx ASC")


@router.get("/shots/{shot_id}/reframe")
def reframe_preview(shot_id: str, preset: str = "shorts_1080x1920") -> Response:
    """Preview the content-aware crop of a shot's keyframe for an export preset (e.g. Shorts)."""
    shot = models.get("shots", shot_id)
    if shot is None:
        raise HTTPException(404, "shot not found")
    if not shot.get("keyframe_id"):
        raise HTTPException(409, "shot has no keyframe yet")
    if preset not in compose.EXPORT_PRESETS:
        raise HTTPException(422, f"preset must be one of {list(compose.EXPORT_PRESETS)}")
    kf = models.get("assets", shot["keyframe_id"])
    storage = get_provider(Capability.STORAGE)
    w, h = compose.EXPORT_PRESETS[preset]
    png = reframe.reframe_to_aspect(storage.open(kf["path"]), w, h)
    return Response(content=png, media_type="image/png")


@router.get("/motion-presets")
def motion_presets() -> dict:
    return scene.MOTION_PRESETS
