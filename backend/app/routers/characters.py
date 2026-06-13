"""Character Foundry endpoints (spec Module A)."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException

from .. import foundry, lore, models, safety
from ..jobs import queue
from ..models import now, new_id
from ..schemas import CharacterCreate, CharacterEdit

router = APIRouter(prefix="/characters", tags=["characters"])

_VALID_SHEETS = {"turnaround", "expressions", "poses"}


def _validate_sheets(sheets: list[str]) -> None:
    bad = [s for s in sheets if s not in _VALID_SHEETS]
    if bad:
        raise HTTPException(422, f"invalid sheet(s) {bad}; allowed: {sorted(_VALID_SHEETS)}")


def _guard(project: dict, *texts: str) -> None:
    ip = safety.check_ip(*texts)
    if not ip.ok:
        raise HTTPException(422, {"error": ip.reason, "matched": list(ip.matched)})
    if project["safe_mode"]:
        safe = safety.check_safe_mode(*texts)
        if not safe.ok:
            raise HTTPException(422, {"error": safe.reason, "matched": list(safe.matched)})


@router.post("")
def create_character(body: CharacterCreate) -> dict:
    project = models.get("projects", body.project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if body.style_preset not in foundry.STYLE_PRESETS:
        raise HTTPException(422, f"unknown style_preset; choose from {list(foundry.STYLE_PRESETS)}")
    _validate_sheets(body.sheets)
    _guard(project, body.name, body.description)

    character = models.create_character(
        body.project_id, body.name, body.description,
        style_preset=body.style_preset, palette=body.palette,
        style_tokens=body.style_tokens, negative_prompt=body.negative_prompt,
        lore=lore.generate_lore(body.name, body.description,
                                style_preset=body.style_preset, language=project["language"]),
    )
    job = queue.enqueue("character_sheets",
                        {"character_id": character["id"], "sheets": body.sheets},
                        project_id=body.project_id)
    return {"character": character, "job": job}


@router.get("/{character_id}")
def get_character(character_id: str) -> dict:
    character = models.get("characters", character_id)
    if character is None:
        raise HTTPException(404, "character not found")
    return character


@router.post("/{character_id}/edit")
def edit_character(character_id: str, body: CharacterEdit) -> dict:
    character = models.get("characters", character_id)
    if character is None:
        raise HTTPException(404, "character not found")
    project = models.get("projects", character["project_id"])
    _validate_sheets(body.sheets)
    _guard(project, body.instruction)

    edits = list(character.get("edits") or [])
    edits.append({"id": new_id("edt_"), "instruction": body.instruction, "at": now()})
    character = models.update("characters", character_id, {"edits": edits})

    result: dict = {"character": character, "applied": edits[-1]}
    if body.regenerate:
        result["job"] = queue.enqueue(
            "character_sheets", {"character_id": character_id, "sheets": body.sheets},
            project_id=character["project_id"],
        )
    return result


@router.post("/{character_id}/lore")
def regenerate_lore(character_id: str) -> dict:
    """Re-roll the character's personality / backstory / abilities (rule-based, no LLM)."""
    character = models.get("characters", character_id)
    if character is None:
        raise HTTPException(404, "character not found")
    project = models.get("projects", character["project_id"])
    new_lore = lore.generate_lore(
        character["name"], character["description"],
        style_preset=character["style_preset"],
        language=(project or {}).get("language", "en"),
        seed=secrets.randbelow(2**31),          # fresh seed -> a different roll each time
    )
    models.update("characters", character_id, {"lore": new_lore})
    return new_lore


@router.get("/{character_id}/consistency")
def get_consistency(character_id: str) -> dict:
    character = models.get("characters", character_id)
    if character is None:
        raise HTTPException(404, "character not found")
    return character.get("consistency") or {"scores": {}, "passed": None,
                                            "note": "not generated yet"}
