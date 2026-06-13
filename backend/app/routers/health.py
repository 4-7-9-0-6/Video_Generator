"""Health + provider availability."""
from __future__ import annotations

from fastapi import APIRouter

from .. import __version__
from ..config import settings
from ..providers.registry import probe_all

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__,
            "languages": list(settings.languages)}


@router.get("/providers")
def providers() -> dict:
    probes = probe_all()
    return {
        "selected": settings.providers,
        "providers": probes,
        "ready": [p for p in probes if p["available"]],
        "unavailable": [p for p in probes if not p["available"]],
    }
