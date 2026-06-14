"""Serve generated asset files by id."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import models
from ..config import settings

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("")
def list_assets(kind: str | None = None, project_id: str | None = None, limit: int = 200) -> list[dict]:
    """List assets, newest first. Filter by ?kind=video (or thumbnail, etc.) and/or ?project_id=."""
    where, params = [], []
    if kind:
        where.append("kind = ?"); params.append(kind)
    if project_id:
        where.append("project_id = ?"); params.append(project_id)
    rows = models.list_where("assets", " AND ".join(where), tuple(params), "created_at DESC")
    return rows[: max(1, min(limit, 500))]


@router.delete("/{asset_id}")
def delete_asset(asset_id: str) -> dict:
    """Delete an asset's file from disk and its DB row."""
    asset = models.get("assets", asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    path = (settings.assets_dir() / asset["path"]).resolve()
    if str(path).startswith(str(settings.assets_dir().resolve())) and path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    models.delete("assets", asset_id)
    return {"deleted": asset_id, "kind": asset["kind"]}


@router.get("/{asset_id}")
def get_asset(asset_id: str):
    asset = models.get("assets", asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    path = (settings.assets_dir() / asset["path"]).resolve()
    # guard against path traversal
    if not str(path).startswith(str(settings.assets_dir().resolve())) or not path.exists():
        raise HTTPException(404, "asset file missing")
    return FileResponse(path, media_type=asset["mime"], filename=Path(asset["path"]).name)


@router.get("/{asset_id}/meta")
def get_asset_meta(asset_id: str) -> dict:
    asset = models.get("assets", asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")
    return asset
