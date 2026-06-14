"""Social / marketing pack — turn a finished video's topic into ready-to-post metadata.

From the project's title + lyrics, generate catchy **titles**, a **description**, **hashtags**, a
short **caption**, and a rule-based **virality score** with concrete tips. The creative text comes
from the LLM provider (OpenRouter `:free` — text only, $0, no GPU/Cloudflare), with robust
fallbacks so it still produces a usable pack offline / without a key. The virality score is a
deterministic heuristic (always works), so the panel is never empty.
"""
from __future__ import annotations

import re
from typing import Any

from .providers.base import Capability
from .providers.registry import get_provider
from .songwriter import _extract_json

_SYSTEM = ("You are a viral short-form video marketer. You write punchy, honest, original "
           "titles/captions (no clickbait lies, no real brands). Respond with VALID JSON only.")

_STOP = {"the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "at", "for", "with",
         "is", "it", "my", "your", "we", "you", "i", "this", "that", "be", "are", "as", "so",
         "up", "out", "all", "no", "yes", "oh", "la", "na", "da", "little", "let"}

_PLATFORMS = {"youtube", "tiktok", "instagram", "shorts"}


def _prompt(title: str, lyrics: str, style: str, language: str, platform: str) -> str:
    return f'''A short animated music video was made. Write its social post pack for {platform}.

Title idea: "{title}"
Style: {style or "animated music video"}
Language: {language}
Lyrics / scene text:
{lyrics[:1200]}

Return ONLY JSON with EXACTLY this shape:
{{
  "titles": ["3 to 5 catchy title options, <=70 chars each"],
  "description": "2-4 sentence description for the post (engaging, honest, no fake claims)",
  "hashtags": ["8 to 14 relevant hashtags WITHOUT the # symbol"],
  "caption": "one short punchy caption for {platform} with 1-2 emoji"
}}
No real brands or copyrighted names. Keep it original and upbeat.'''


def _keywords(text: str, k: int = 8) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z']{2,}", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w in _STOP:
            continue
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])][:k]


def virality_score(title: str, lyrics: str, hashtags: list[str]) -> dict[str, Any]:
    """Deterministic 0-100 'ready-to-post' heuristic with reasons + actionable tips."""
    score = 50
    reasons: list[str] = []
    tips: list[str] = []

    tl = len(title)
    if 20 <= tl <= 60:
        score += 12; reasons.append("title length is in the sweet spot")
    elif tl > 70:
        score -= 8; tips.append("shorten the title to under ~60 characters")
    else:
        tips.append("make the title a bit more descriptive (20-60 chars)")

    if re.search(r"\d", title):
        score += 6; reasons.append("a number in the title boosts clicks")
    else:
        tips.append("try adding a number (e.g. '3 ways…') to the title")

    if re.search(r"[\U0001F300-\U0001FAFF☀-➿]", title):
        score += 4; reasons.append("an emoji in the title adds visual pop")

    # chorus / repeated hook = sticky
    low = lyrics.lower()
    lines = [ln.strip() for ln in low.splitlines() if ln.strip()]
    if len(lines) != len(set(lines)) or "chorus" in low:
        score += 12; reasons.append("a repeated hook/chorus makes it memorable")
    else:
        tips.append("repeat a one-line hook 2-3x — repetition drives replays")

    hn = len(hashtags)
    if 5 <= hn <= 15:
        score += 8; reasons.append(f"{hn} hashtags is a healthy range")
    elif hn < 5:
        tips.append("add a few more niche hashtags (aim for 8-12)")
    else:
        tips.append("trim to ~12 hashtags; too many looks spammy")

    if any(h.lower() in ("shorts", "reels", "fyp", "viral") for h in hashtags):
        score += 4; reasons.append("includes a discovery hashtag (#shorts/#fyp)")
    else:
        tips.append("add a discovery tag like #shorts or #fyp")

    score = max(1, min(100, score))
    grade = "🔥 strong" if score >= 75 else ("👍 solid" if score >= 55 else "⚠️ needs work")
    return {"score": score, "grade": grade, "reasons": reasons[:5], "tips": tips[:4]}


def normalize_pack(data: dict, *, title: str, lyrics: str, platform: str) -> dict[str, Any]:
    titles = [str(t).strip()[:80] for t in (data.get("titles") or []) if str(t).strip()][:5]
    if not titles:
        titles = [title or "My Animated Song", f"{title} 🎵".strip(), f"{title} (Official Video)".strip()]
    description = str(data.get("description") or "").strip()
    if not description:
        description = (f"{title} — an original animated music video. "
                       "Made with AI, song + scenes generated from a single idea. "
                       "Like & subscribe for more!").strip()

    raw_tags = data.get("hashtags") or []
    tags = []
    for t in raw_tags:
        t = re.sub(r"[^A-Za-z0-9]", "", str(t))
        if t:
            tags.append(t)
    if len(tags) < 5:
        tags += [w for w in _keywords(f"{title} {lyrics}")]
    tags += ["animation", "aimusic", "musicvideo", "shorts" if platform in ("tiktok", "instagram", "shorts") else "music"]
    seen: set[str] = set()
    hashtags = []
    for t in tags:
        key = t.lower()
        if key and key not in seen:
            seen.add(key); hashtags.append(t)
    hashtags = hashtags[:14]

    caption = str(data.get("caption") or "").strip()
    if not caption:
        caption = f"{titles[0]} ✨🎶"

    return {
        "platform": platform,
        "titles": titles,
        "description": description,
        "hashtags": hashtags,
        "hashtag_string": " ".join(f"#{h}" for h in hashtags),
        "caption": caption,
        "virality": virality_score(titles[0], lyrics, hashtags),
    }


async def generate_pack(title: str, lyrics: str, *, style: str = "", language: str = "en",
                        platform: str = "youtube") -> dict[str, Any]:
    platform = platform if platform in _PLATFORMS else "youtube"
    data: dict = {}
    try:
        llm = get_provider(Capability.LLM)
        raw = await llm.complete(_prompt(title, lyrics, style, language, platform),
                                 system=_SYSTEM, temperature=0.8, max_tokens=700)
        data = _extract_json(raw)
    except Exception:  # noqa: BLE001 — no LLM/key or wonky JSON: fall back to heuristic pack
        data = {}
    return normalize_pack(data, title=title, lyrics=lyrics, platform=platform)
