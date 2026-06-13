"""Scene Engine domain logic (spec Module C).

Script → shots planning (CPU, rule-based), the motion-preset library (Higgsfield-style),
and the keyframe prompt builder that reuses the Character Foundry identity lock so a
character stays on-model across every shot of an episode.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from . import foundry

# Motion presets (spec §C.6). `hint` shapes the keyframe prompt; `kind` drives the
# FFmpeg Ken Burns video provider (zoom/pan) for the free CPU animation path.
MOTION_PRESETS: dict[str, dict[str, str]] = {
    "static": {"hint": "steady eye-level shot", "kind": "static"},
    "dolly_in": {"hint": "slow dolly-in pushing toward the subject", "kind": "zoom_in"},
    "dolly_out": {"hint": "slow dolly-out pulling back to reveal the scene", "kind": "zoom_out"},
    "pan_left": {"hint": "smooth camera pan to the left", "kind": "pan_left"},
    "pan_right": {"hint": "smooth camera pan to the right", "kind": "pan_right"},
    "bounce_in": {"hint": "playful bounce-in entrance, energetic", "kind": "zoom_in"},
    "spin_reveal": {"hint": "spin reveal of the subject", "kind": "zoom_in"},
}
_CYCLE = ["dolly_in", "pan_left", "static", "pan_right", "dolly_out"]

_WORDS_PER_SECOND = 2.0
_MIN_DUR, _MAX_DUR = 2.0, 10.0


def _pick_camera(line: str, idx: int) -> str:
    s = line.strip()
    if idx == 0:
        return "dolly_in"
    if s.endswith("!"):
        return "bounce_in"
    if s.endswith("?"):
        return "static"
    return _CYCLE[idx % len(_CYCLE)]


def _duration_for(line: str) -> float:
    words = len(re.findall(r"\w+", line))
    secs = words / _WORDS_PER_SECOND + 0.8
    return round(max(_MIN_DUR, min(_MAX_DUR, secs)), 1)


def _present_characters(line: str, characters: list[dict[str, Any]]) -> list[str]:
    low = line.lower()
    return [c["id"] for c in characters
            if re.search(rf"\b{re.escape(c['name'].lower())}\b", low)]


def plan_script(script: str, characters: list[dict[str, Any]], *,
                default_background: str = "") -> list[dict[str, Any]]:
    """Segment a script/lyrics into shot proposals (one beat per non-empty line)."""
    lines = [ln.strip() for ln in script.splitlines() if ln.strip()]
    shots: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        shots.append({
            "idx": idx,
            "text": line,
            "characters": _present_characters(line, characters),
            "camera": _pick_camera(line, idx),
            "background": default_background,
            "duration_s": _duration_for(line),
        })
    return shots


def build_shot_prompt(shot: dict[str, Any], char_map: dict[str, dict[str, Any]],
                      project: dict[str, Any]) -> str:
    """Locked keyframe prompt: every present character's identity + palette, the
    background, the camera motion, and the project style."""
    present = [char_map[cid] for cid in shot.get("characters", []) if cid in char_map]
    parts: list[str] = []

    if present:
        who = []
        for c in present:
            desc = foundry.effective_description(c)
            pal = c.get("palette") or []
            who.append(f"{c['name']} ({desc}{('; palette ' + ', '.join(pal)) if pal else ''})")
        parts.append(" and ".join(who))
    else:
        parts.append("an empty scene")

    scene = shot.get("background") or "simple, uncluttered background"
    parts.append(f"Scene: {scene}")
    if shot.get("text"):
        parts.append(f"Action: {shot['text']}")

    cam = MOTION_PRESETS.get(shot.get("camera", "static"), MOTION_PRESETS["static"])
    parts.append(cam["hint"])

    style = foundry.STYLE_PRESETS.get(project.get("style_preset", ""),
                                      foundry.STYLE_PRESETS["3d_toddler_original"])
    parts.append(style)
    parts.append("cinematic keyframe, consistent character design, same characters, high detail")
    return ". ".join(parts)


def prompt_hash(prompt: str, provider_name: str) -> str:
    return hashlib.sha1(f"{provider_name}::{prompt}".encode()).hexdigest()
