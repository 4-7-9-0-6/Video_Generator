"""Rule-based character lore — personality, backstory, abilities — WITHOUT an LLM.

Detects an archetype + theme + elemental keywords from the description and assembles text from
curated phrase banks, with per-character variety seeded deterministically from the name +
description. Local, free, no Ollama. (An LLM could later replace this behind `generate_lore`.)
"""
from __future__ import annotations

import hashlib
import random
import re

# archetype -> (keywords, personality traits, ability phrases)
_ARCHETYPES: dict[str, dict] = {
    "warrior": {
        "kw": ["warrior", "fighter", "knight", "soldier", "samurai", "swordsman", "blade",
               "armor", "berserker", "gladiator", "duelist"],
        "traits": ["disciplined", "fearless", "fiercely loyal", "stoic", "relentless", "honor-bound"],
        "abilities": ["master swordsmanship", "an unbreakable guard stance", "razor-sharp battle instinct"],
    },
    "mage": {
        "kw": ["mage", "wizard", "witch", "sorcerer", "sorceress", "magic", "spell", "arcane",
               "enchant", "mystic", "caster"],
        "traits": ["endlessly curious", "calm under pressure", "secretive", "brilliant", "patient"],
        "abilities": ["devastating arcane bolts", "elemental spellweaving", "protective wards"],
    },
    "machine": {
        "kw": ["robot", "cyborg", "android", "mech", "machine", "droid", "robotic", "synthetic",
               "ai", "augmented", "chrome"],
        "traits": ["calculating", "precise", "unflinching", "coldly analytical", "tireless"],
        "abilities": ["overclocked reflexes", "integrated weapon systems", "tactical data-sight"],
    },
    "rogue": {
        "kw": ["rogue", "thief", "assassin", "ninja", "spy", "stealth", "shadow", "phantom",
               "trickster"],
        "traits": ["cunning", "quiet", "lightning-quick", "independent", "sharp-witted"],
        "abilities": ["a silent killing strike", "shadowstep evasion", "uncanny sleight of hand"],
    },
    "healer": {
        "kw": ["healer", "priest", "priestess", "medic", "cleric", "saint", "shrine", "monk"],
        "traits": ["gentle", "endlessly patient", "selfless", "wise", "warm"],
        "abilities": ["restorative light", "a cleansing aura", "a life-binding link"],
    },
    "hero": {
        "kw": ["hero", "champion", "savior", "protector", "guardian", "chosen", "captain"],
        "traits": ["brave", "stubbornly hopeful", "determined", "kind-hearted", "inspiring"],
        "abilities": ["a rallying battle cry", "a never-say-die second wind", "an unyielding will"],
    },
    "villain": {
        "kw": ["villain", "evil", "demon", "tyrant", "corrupt", "dark lord", "overlord",
               "fiend", "cursed"],
        "traits": ["ruthless", "ambitious", "ice-cold", "commanding", "manipulative"],
        "abilities": ["a dread-inducing aura", "a dominating presence", "forbidden, world-bending power"],
    },
}
_DEFAULT_ARCH = {
    "traits": ["curious", "free-spirited", "resourceful", "easygoing", "observant"],
    "abilities": ["keen survival skills", "an adaptable fighting style", "an uncanny streak of luck"],
}

# theme -> flavor (also inferred from anime style presets)
_THEMES: dict[str, dict] = {
    "cyberpunk": {"kw": ["cyberpunk", "neon", "cyber", "hacker", "dystopia", "android", "chrome"],
                  "place": "the neon-drowned megacity of Neo-Sankai", "era": "a wired, rain-slick future"},
    "fantasy": {"kw": ["fantasy", "magic", "kingdom", "dragon", "elf", "sword", "realm", "knight"],
                "place": "the high kingdom of Aldenmoor", "era": "an age of magic and steel"},
    "dark": {"kw": ["dark", "grim", "demon", "curse", "shadow", "blood", "abyss"],
             "place": "the ash-grey ruins of the Fallen Reach", "era": "a world long since broken"},
    "cute": {"kw": ["cute", "kawaii", "cozy", "sweet", "pastel", "magical girl"],
             "place": "the bright little town of Hoshigaoka", "era": "a sunny, gentle age"},
    "shonen": {"kw": ["shonen", "tournament", "rival", "academy", "guild", "adventure"],
               "place": "the bustling Hero Academy district", "era": "an age of rising young fighters"},
}
_DEFAULT_THEME = {"place": "a distant, unnamed land", "era": "a forgotten age"}

_ELEMENTS = {
    "fire": ["fire", "flame", "ember", "blaze", "inferno"], "ice": ["ice", "frost", "snow", "glacial"],
    "lightning": ["lightning", "thunder", "electric", "storm", "volt"],
    "shadow": ["shadow", "dark", "void", "night"], "light": ["light", "holy", "radiant", "solar"],
    "wind": ["wind", "gale", "sky", "air"], "water": ["water", "tide", "ocean", "rain"],
    "earth": ["earth", "stone", "rock", "iron", "metal"], "psychic": ["psychic", "mind", "telepath"],
    "tech": ["tech", "laser", "plasma", "nano", "cyber", "robotic"],
}

_STYLE_THEME = {
    "anime_cyberpunk": "cyberpunk", "anime_fantasy": "fantasy", "anime_dark": "dark",
    "anime_cute": "cute", "anime_shonen": "shonen", "anime_chibi": "cute",
}


def _seed(name: str, description: str) -> int:
    return int(hashlib.sha1(f"{name}|{description}".encode()).hexdigest(), 16)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def _match(word: str, toks: set[str], low: str) -> bool:
    # multi-word keywords need a substring match; single words match whole-word only
    # (so "air" doesn't match "hair", "ai" doesn't match "kawaii")
    return (word in low) if (" " in word or "-" in word) else (word in toks)


def _detect(text: str, banks: dict, key: str = "kw") -> str | None:
    toks, low = _tokens(text), text.lower()
    best, score = None, 0
    for namek, spec in banks.items():
        hits = sum(1 for w in spec[key] if _match(w, toks, low))
        if hits > score:
            best, score = namek, hits
    return best


def generate_lore(name: str, description: str, *, style_preset: str = "",
                  language: str = "en", seed: int | None = None) -> dict:
    """Return {personality, backstory, abilities[], archetype, theme, elements[]}.
    `seed` overrides the deterministic name+description seed (used to re-roll variety)."""
    rng = random.Random(seed if seed is not None else _seed(name, description))
    text = f"{description} {style_preset}"

    arch_key = _detect(text, _ARCHETYPES) or "wanderer"
    arch = _ARCHETYPES.get(arch_key, _DEFAULT_ARCH)
    theme_key = _STYLE_THEME.get(style_preset) or _detect(text, _THEMES) or "wanderer"
    theme = _THEMES.get(theme_key, _DEFAULT_THEME)
    _toks = _tokens(text)
    elements = [el for el, kws in _ELEMENTS.items() if any(k in _toks for k in kws)]

    # personality: 3 distinct traits + a quirk sentence
    traits = rng.sample(arch["traits"], k=min(3, len(arch["traits"])))
    quirks = ["never backs down from a dare", "keeps a small good-luck charm close",
              "speaks little but means every word", "hides a soft heart behind a sharp tone",
              "is always the first to laugh", "trusts slowly but loves fiercely"]
    personality = (f"{name} is {_join(traits)}. " + rng.choice(quirks).capitalize() + ".")

    # backstory: origin -> turning point -> goal
    origins = [
        f"Raised in {theme['place']}, {name} grew up an outsider with more questions than answers",
        f"Born into {theme['era']}, {name} learned early that the world rarely plays fair",
        f"Found alone as a child in {theme['place']}, {name} was taken in and trained in secret",
    ]
    turns = [
        "until a single, terrible night changed everything",
        "until a chance meeting set them on a far greater path",
        "until the day their quiet life was torn apart",
        "until an old promise finally came due",
    ]
    goals = [
        f"Now {name} travels onward, determined to protect the people the world forgot.",
        f"Now {name} fights to undo the wrong that started it all.",
        f"Now {name} chases a destiny only they can see — whatever the cost.",
        f"Now {name} seeks the truth buried at the heart of {theme['place']}.",
    ]
    backstory = f"{rng.choice(origins)}, {rng.choice(turns)}. {rng.choice(goals)}"

    # abilities: archetype skills + an elemental power + a named signature move
    abilities = rng.sample(arch["abilities"], k=min(2, len(arch["abilities"])))
    if elements:
        el = rng.choice(elements)
        abilities.append(f"{el} manipulation")
        sig = rng.choice(["Surge", "Requiem", "Ascension", "Edge", "Veil", "Drive"])
        abilities.append(f"signature move: \"{el.capitalize()} {sig}\"")
    else:
        abilities.append(rng.choice(["a hidden inner power that surfaces in dire moments",
                                     "a signature technique no one else can copy"]))

    return {
        "personality": personality,
        "backstory": backstory,
        "abilities": abilities,
        "archetype": arch_key,
        "theme": theme_key,
        "elements": elements,
    }


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " and " + items[-1]
