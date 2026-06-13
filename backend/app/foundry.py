"""Character Foundry domain logic (spec Module A).

The reuse-injection prompt builder is the CPU-level "Character Lock": with no GPU for
LoRA/IP-Adapter, identity is enforced by (a) a stable per-character seed, (b) the full
description + applied edits, (c) palette hex constraints and style tokens, and (d) a
post-generation perceptual-hash drift check that auto-regenerates off-model results.
The same builder is reused for every shot so characters stay consistent across an episode.
"""
from __future__ import annotations

import hashlib
from typing import Any

# style preset -> prompt descriptor (legally-distinct originals — spec §A.6/§A.7)
STYLE_PRESETS: dict[str, str] = {
    "3d_toddler_original": "original 3D cartoon, soft rounded toddler proportions, big "
                           "expressive eyes, smooth shading, bright friendly children's "
                           "animation style, NOT resembling any existing franchise",
    "2d_flat": "clean 2D flat vector illustration, bold outlines, flat color fills",
    "anime_chibi": "anime chibi style, small body, large head, cute, cel shaded",
    "claymation": "claymation stop-motion look, sculpted plasticine, soft studio light",
    "storybook_watercolor": "storybook watercolor illustration, soft painterly washes",
    # anime style packs (legally-distinct originals — spec §A.6/§A.7)
    "anime_shonen": "dynamic shonen anime style, bold clean cel shading, energetic action lines, "
                    "vibrant saturated colors, expressive determined eyes",
    "anime_fantasy": "fantasy anime style, painterly soft lighting, ornate costume detail, "
                     "ethereal magical atmosphere, rich color",
    "anime_cyberpunk": "cyberpunk anime style, glowing neon rim light, dark rain-slick city, "
                       "high-tech detail, chromatic reflections, moody contrast",
    "anime_cute": "cute kawaii anime style, soft pastel palette, big sparkling eyes, rounded "
                  "friendly shapes, gentle shading",
    "anime_dark": "dark anime style, dramatic high-contrast shadows, muted gritty palette, "
                  "intense moody atmosphere, sharp detailed linework",
}

# (key, prompt fragment, framing)
TURNAROUND_VIEWS = [
    ("front", "front view, facing camera", "full body"),
    ("three_quarter", "3/4 view, turned slightly", "full body"),
    ("side", "side profile view", "full body"),
    ("back", "back view, facing away", "full body"),
]
EXPRESSIONS = [
    ("happy", "happy, big smile", "head and shoulders close-up"),
    ("sad", "sad, downturned mouth", "head and shoulders close-up"),
    ("surprised", "surprised, wide eyes, open mouth", "head and shoulders close-up"),
    ("sleepy", "sleepy, half-closed eyes, yawning", "head and shoulders close-up"),
    ("singing", "singing, mouth open mid-song", "head and shoulders close-up"),
]
POSES = [
    ("standing", "standing pose, arms relaxed", "full body"),
    ("sitting", "sitting on the floor", "full body"),
    ("jumping", "jumping, mid-air, joyful", "full body"),
    ("waving", "waving one hand hello", "full body"),
    ("holding_object", "holding a small toy in both hands", "full body"),
]


def identity_seed(character_id: str) -> int:
    """Stable base seed so every render of this character starts from the same point."""
    return int(hashlib.sha1(character_id.encode()).hexdigest(), 16) % (2**31)


def effective_description(character: dict[str, Any]) -> str:
    """Base description with instruction edits applied in order (latest wins)."""
    desc = character["description"]
    edits = character.get("edits") or []
    if edits:
        desc = desc + ". " + ". ".join(e["instruction"].strip().rstrip(".") for e in edits)
    return desc


def build_character_prompt(character: dict[str, Any], *, pose: str = "",
                           framing: str = "full body",
                           scene: str = "", neutral_bg: bool = True) -> str:
    """Reuse-injection prompt: identity + palette + style, plus pose/scene context.

    `scene` is used by the Scene Engine later (shot backgrounds); for Foundry sheets it
    is empty and a neutral background is requested instead.
    """
    style = STYLE_PRESETS.get(character["style_preset"], STYLE_PRESETS["3d_toddler_original"])
    palette = character.get("palette") or []
    tokens = character.get("style_tokens") or []
    parts = [effective_description(character)]
    if pose:
        parts.append(pose)
    if scene:
        parts.append(scene)
    elif neutral_bg:
        parts.append("neutral solid background")
    parts.append(framing)
    parts.append(style)
    if tokens:
        parts.append(", ".join(tokens))
    if palette:
        parts.append("strict color palette: " + ", ".join(palette))
    parts.append("consistent character design, same character, high detail")
    return ". ".join(p for p in parts if p)


def all_sheet_items(which: list[str] | None = None):
    """Yield (sheet, key, fragment, framing) for requested sheets (default: all)."""
    which = which or ["turnaround", "expressions", "poses"]
    groups = {"turnaround": TURNAROUND_VIEWS, "expressions": EXPRESSIONS, "poses": POSES}
    for sheet in which:
        for key, fragment, framing in groups[sheet]:
            yield sheet, key, fragment, framing
