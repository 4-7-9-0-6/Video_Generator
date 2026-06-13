"""Onboarding template endpoints (spec §7 Phase 6)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import templates

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
def list_templates() -> list[dict]:
    return templates.list_templates()


@router.post("/{template_id}/instantiate")
def instantiate(template_id: str) -> dict:
    if template_id not in templates.TEMPLATES:
        raise HTTPException(404, f"unknown template; choose from {list(templates.TEMPLATES)}")
    return templates.instantiate(template_id)
