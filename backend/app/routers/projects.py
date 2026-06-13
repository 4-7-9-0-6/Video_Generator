"""Project CRUD."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import models
from ..config import settings
from ..schemas import ProjectCreate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("")
def create_project(body: ProjectCreate) -> dict:
    if body.language not in settings.languages:
        raise HTTPException(400, f"language must be one of {list(settings.languages)}")
    return models.create_project(
        body.name, style_preset=body.style_preset, language=body.language,
        fps=body.fps, width=body.width, height=body.height,
    )


@router.get("")
def list_projects() -> list[dict]:
    return models.list_where("projects", order="created_at DESC")


@router.get("/{project_id}")
def get_project(project_id: str) -> dict:
    project = models.get("projects", project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return project


@router.get("/{project_id}/characters")
def list_characters(project_id: str) -> list[dict]:
    return models.list_where("characters", "project_id = ?", (project_id,), "created_at DESC")


@router.delete("/{project_id}")
def delete_project(project_id: str) -> dict:
    if models.get("projects", project_id) is None:
        raise HTTPException(404, "project not found")
    models.delete("projects", project_id)
    return {"deleted": project_id}
