"""YouTube thumbnail endpoints: propose N thumbnails for a project, list existing ones."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import models
from ..jobs import queue
from ..schemas import ThumbnailRequest

router = APIRouter(tags=["thumbnails"])


@router.post("/projects/{project_id}/thumbnails")
def propose_thumbnails(project_id: str, body: ThumbnailRequest) -> dict:
    if models.get("projects", project_id) is None:
        raise HTTPException(404, "project not found")
    return queue.enqueue("thumbnails", {
        "project_id": project_id, "title": body.title, "count": body.count,
        "character_id": body.character_id, "background": body.background,
    }, project_id=project_id)


@router.get("/projects/{project_id}/thumbnails")
def list_thumbnails(project_id: str) -> list[dict]:
    if models.get("projects", project_id) is None:
        raise HTTPException(404, "project not found")
    thumbs = models.list_where("assets", "project_id = ? AND kind = ?",
                               (project_id, "thumbnail"), "created_at DESC")
    return [{"asset_id": a["id"], "title": (a.get("meta") or {}).get("title"),
             "variant": (a.get("meta") or {}).get("variant"),
             "created_at": a["created_at"]} for a in thumbs]
