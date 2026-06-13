"""Onboarding templates (spec §7 Phase 6) — one click from zero to a renderable episode.

Instantiating a template scaffolds a project, its character(s) (kicking off sheet
generation), and a planned shot list. All template content is ORIGINAL (legally distinct),
in keeping with the copyright guard.
"""
from __future__ import annotations

from typing import Any

from . import models, scene
from .jobs import queue

# An original nursery rhyme (not a copyrighted one), naming the character each line so
# the shot planner detects her presence in every beat.
_MILA_RHYME = """Mila wakes up with the morning sun.
Mila stretches high, it's time for fun!
Mila waves hello to the birds in the tree.
Mila skips outside, as happy as can be.
Mila splashes puddles, one, two, three!
Mila sings a song for you and me."""

TEMPLATES: dict[str, dict[str, Any]] = {
    "nursery_rhyme": {
        "id": "nursery_rhyme",
        "title": "Nursery Rhyme Episode",
        "description": "A 6-line original rhyme starring a toddler — character, script, and "
                       "shots pre-filled. Render keyframes and export to a finished video.",
        "project": {"name": "Mila's Morning — Nursery Rhyme", "language": "en",
                    "style_preset": "3d_toddler_original", "fps": 24,
                    "width": 1920, "height": 1080},
        "characters": [{
            "name": "Mila",
            "description": "a cheerful 4-year-old girl with two curly brown pigtails, big "
                           "brown eyes, a yellow t-shirt with a star, blue shorts, and red sneakers",
            "palette": ["#FFD23F", "#3A86FF", "#FF5C5C", "#6B4423"],
            "style_preset": "3d_toddler_original",
        }],
        "script": _MILA_RHYME,
        "default_background": "a sunny backyard with green grass and colorful flowers",
    },
}


def list_templates() -> list[dict[str, Any]]:
    return [{"id": t["id"], "title": t["title"], "description": t["description"]}
            for t in TEMPLATES.values()]


def instantiate(template_id: str) -> dict[str, Any]:
    t = TEMPLATES[template_id]
    project = models.create_project(**t["project"])

    characters: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    for spec in t["characters"]:
        ch = models.create_character(
            project["id"], spec["name"], spec["description"],
            style_preset=spec.get("style_preset", "3d_toddler_original"),
            palette=spec.get("palette", []))
        characters.append(ch)
        jobs.append(queue.enqueue(
            "character_sheets",
            {"character_id": ch["id"], "sheets": ["turnaround", "expressions", "poses"]},
            project_id=project["id"]))

    proposals = scene.plan_script(t["script"], characters,
                                  default_background=t["default_background"])
    shots = [models.create_shot(project["id"], p["idx"], p["text"], characters=p["characters"],
                                camera=p["camera"], background=p["background"],
                                duration_s=p["duration_s"])
             for p in proposals]

    return {"project": project, "characters": characters, "shots": shots, "jobs": jobs}
