"""Content + IP safety (spec §A.7, §security). CPU-only, no model required.

- Name/brand blocklist: refuse prompts that name protected characters/franchises.
- Safe-mode keyword guard: block violent/scary terms for children's-content mode.
The CLIP-similarity output check is added when a GPU/CLIP provider is available; the
pHash consistency provider already gives a coarse image-similarity guard in the meantime.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Non-exhaustive starter blocklist of protected names/franchises.
PROTECTED_NAMES = {
    "mickey mouse", "minnie", "elsa", "frozen", "peppa pig", "cocomelon", "jj cocomelon",
    "bluey", "paw patrol", "spongebob", "pikachu", "pokemon", "mario", "luigi", "sonic",
    "spider-man", "spiderman", "batman", "superman", "hello kitty", "winnie the pooh",
    "baby shark", "disney", "pixar", "marvel", "nintendo", "barbie", "minions", "shrek",
}

UNSAFE_TERMS = {
    "blood", "gore", "kill", "weapon", "gun", "knife", "violence", "scary", "horror",
    "nude", "sexual", "drug",
}


@dataclass
class SafetyResult:
    ok: bool
    reason: str = ""
    matched: tuple[str, ...] = ()


def _hits(text: str, terms: set[str]) -> list[str]:
    low = text.lower()
    return [t for t in terms if re.search(rf"\b{re.escape(t)}\b", low)]


def check_ip(*texts: str) -> SafetyResult:
    joined = " ".join(texts)
    hits = _hits(joined, PROTECTED_NAMES)
    if hits:
        return SafetyResult(False,
                            reason="Names a protected character/brand. Use an original design.",
                            matched=tuple(hits))
    return SafetyResult(True)


def check_safe_mode(*texts: str) -> SafetyResult:
    joined = " ".join(texts)
    hits = _hits(joined, UNSAFE_TERMS)
    if hits:
        return SafetyResult(False,
                            reason="Blocked by children's-content safe mode.",
                            matched=tuple(hits))
    return SafetyResult(True)
