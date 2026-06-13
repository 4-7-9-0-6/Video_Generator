"""Prompt → song plan (lyrics + chorus + characters + scenes) via the LLM provider.

Turns a one-line topic into a structured, singable plan the rest of the pipeline can build a
complete music video from. The LLM writes the creative TEXT; everything visual/audio stays
local. Output is validated/normalized so a wonky LLM response can't break the pipeline.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .providers.base import Capability
from .providers.registry import get_provider

_SECTIONS = {"intro", "verse", "chorus", "bridge", "outro"}
_MOODS = {"lullaby", "playful", "adventure", "learning", "tender", "epic"}

_SYSTEM = ("You are a professional songwriter and music-video storyboard director. "
           "You write ORIGINAL songs only — never reference real brands, franchises, or "
           "existing characters. Respond with VALID JSON and nothing else.")


def _user_prompt(topic: str, language: str, style: str, n: int) -> str:
    return f'''Write an original song + music-video plan for this idea:
"{topic}"

Language for the lyrics: {language}
Visual style of the video: {style}

Return ONLY a JSON object with EXACTLY this shape:
{{
  "title": "short catchy title",
  "mood": one of {sorted(_MOODS)},
  "characters": [
    {{"name": "OneWordName", "description": "vivid VISUAL description for an image model (look, colors, outfit)"}}
  ],
  "lines": [
    {{"section": "verse|chorus|intro|bridge|outro", "text": "one short singable line", "characters": ["Name"]}}
  ]
}}

Rules:
- 1 to 3 characters, original designs.
- Include a CHORUS line that REPEATS at least twice with the SAME text (a hook).
- {n} to {n + 4} lines total, each short and singable.
- Every line lists which character(s) are on screen (use the names above).
- No real-world brands or copyrighted characters.'''


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    # strip ```json ... ``` fences if present
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    else:
        a, b = raw.find("{"), raw.rfind("}")
        if a != -1 and b != -1:
            raw = raw[a:b + 1]
    return json.loads(raw)


def normalize_song(data: dict, *, fallback_title: str = "Untitled") -> dict:
    """Validate + coerce the LLM JSON into a safe, well-formed song plan."""
    title = str(data.get("title") or fallback_title).strip()[:120]
    mood = str(data.get("mood") or "playful").lower()
    if mood not in _MOODS:
        mood = "playful"

    characters: list[dict] = []
    for c in (data.get("characters") or [])[:3]:
        name = str(c.get("name") or "").strip()
        desc = str(c.get("description") or "").strip()
        if name and desc:
            characters.append({"name": name, "description": desc})
    if not characters:
        characters = [{"name": "Hero", "description": "an original cartoon main character"}]
    valid_names = {c["name"] for c in characters}

    lines: list[dict] = []
    for ln in (data.get("lines") or []):
        text = str(ln.get("text") or "").strip()
        if not text:
            continue
        section = str(ln.get("section") or "verse").lower()
        if section not in _SECTIONS:
            section = "verse"
        present = [n for n in (ln.get("characters") or []) if n in valid_names]
        lines.append({"section": section, "text": text,
                      "characters": present or [characters[0]["name"]]})
    if not lines:
        lines = [{"section": "verse", "text": title, "characters": [characters[0]["name"]]}]

    has_chorus = any(line["section"] == "chorus" for line in lines)
    return {"title": title, "mood": mood, "characters": characters,
            "lines": lines, "has_chorus": has_chorus}


async def write_song(topic: str, *, language: str = "en", style: str = "anime_cyberpunk",
                     scenes: int = 8) -> dict:
    llm = get_provider(Capability.LLM)
    raw = await llm.complete(_user_prompt(topic, language, style, scenes),
                             system=_SYSTEM, temperature=0.85, max_tokens=1600)
    try:
        data = _extract_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"LLM did not return valid JSON: {e}\n--- raw ---\n{raw[:500]}")
    return normalize_song(data, fallback_title=topic[:60])
