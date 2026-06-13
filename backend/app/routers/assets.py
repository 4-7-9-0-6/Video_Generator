"""Serve generated asset files by id."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import models
from ..config import settings

router = APIRouter(prefix="/assets", tags=["assets"])


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
