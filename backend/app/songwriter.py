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


# ---- lyrics -> cast (keep the user's exact words; the LLM only adds characters + scenes) ----

_CAST_SYSTEM = ("You are a music-video casting director and storyboard artist. You are given "
                "EXISTING song lyrics that must NOT be changed. You invent ORIGINAL characters "
                "(never real brands/franchises) and design scenes that fit the lyrics. Respond "
                "with VALID JSON and nothing else.")


def _cast_prompt(lines: list[str], language: str, style: str) -> str:
    numbered = "\n".join(f"{i + 1}. {ln}" for i, ln in enumerate(lines))
    return f'''These are EXISTING song lyrics. DO NOT change, add, or remove any words.
Cast original characters and design a scene for each line.

Lyrics (numbered):
{numbered}

Language: {language}
Visual style: {style}

Return ONLY JSON with this shape:
{{
  "title": "short catchy title for this song",
  "mood": one of {sorted(_MOODS)},
  "characters": [
    {{"name": "OneWordName", "description": "vivid VISUAL description for an image model (look, colors, outfit)"}}
  ],
  "lines": [
    {{"n": 1, "section": "verse|chorus|intro|bridge|outro", "characters": ["Name"], "background": "short scene/setting for this line"}}
  ]
}}
Rules:
- 1 to 3 original characters that suit these lyrics (no real brands/franchises).
- Give EVERY numbered line an entry with its on-screen character(s) and a background.
- Mark repeated hook lines as "chorus".'''


def cast_song_from_lyrics(lines: list[str], data: dict) -> dict:
    """Build a song plan from the USER'S lines (verbatim) + the LLM's casting/scenes. The line
    TEXT is always the user's original — the LLM only contributes characters, mood, backgrounds."""
    title = str(data.get("title") or (lines[0][:40] if lines else "Song")).strip()[:120]
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
    valid = {c["name"] for c in characters}

    meta_by_n: dict[int, dict] = {}
    for ln in (data.get("lines") or []):
        try:
            meta_by_n[int(ln.get("n"))] = ln
        except (TypeError, ValueError):
            continue

    counts: dict[str, int] = {}
    for ln in lines:
        counts[ln.lower()] = counts.get(ln.lower(), 0) + 1

    out_lines: list[dict] = []
    for i, text in enumerate(lines):
        m = meta_by_n.get(i + 1, {})
        section = str(m.get("section") or "").lower()
        if section not in _SECTIONS:
            section = "chorus" if counts[text.lower()] > 1 else "verse"
        present = [n for n in (m.get("characters") or []) if n in valid] or [characters[0]["name"]]
        out_lines.append({"section": section, "text": text, "characters": present,
                          "background": str(m.get("background") or "").strip()})

    return {"title": title, "mood": mood, "characters": characters, "lines": out_lines,
            "has_chorus": any(ln["section"] == "chorus" for ln in out_lines)}


async def cast_from_lyrics(lyrics: str, *, language: str = "en",
                           style: str = "anime_cyberpunk") -> dict:
    """Paste your poem/lyrics -> a full song plan (characters + scenes + mood) that KEEPS your
    exact words. LLM does the casting (free text); falls back to a basic cast if no LLM/key."""
    lines = [ln.strip() for ln in lyrics.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("no lyrics provided")
    data: dict = {}
    try:
        llm = get_provider(Capability.LLM)
        raw = await llm.complete(_cast_prompt(lines, language, style),
                                 system=_CAST_SYSTEM, temperature=0.7, max_tokens=1600)
        data = _extract_json(raw)
    except Exception:  # noqa: BLE001 — no LLM/key or bad JSON: fall back to a basic cast
        data = {}
    return cast_song_from_lyrics(lines, data)
