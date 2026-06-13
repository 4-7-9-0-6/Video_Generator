"""Reference data for clients: style presets and sheet definitions."""
from __future__ import annotations

from fastapi import APIRouter

from .. import foundry

router = APIRouter(tags=["meta"])


@router.get("/styles")
def list_styles() -> list[dict]:
    return [{"id": k, "description": v} for k, v in foundry.STYLE_PRESETS.items()]


@router.get("/sheets")
def list_sheets() -> dict:
    return {
        "turnaround": [k for k, *_ in foundry.TURNAROUND_VIEWS],
        "expressions": [k for k, *_ in foundry.EXPRESSIONS],
        "poses": [k for k, *_ in foundry.POSES],
    }
