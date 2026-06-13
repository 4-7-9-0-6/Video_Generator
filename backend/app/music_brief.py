"""Lyrics -> music brief: pick a fitting mood/tempo/key from the words alone, so a user can
paste lyrics and get sensible backing music with no manual description (spec §B.2/§B.3).

Rule-based and bilingual (EN + FR), free and local — no model needed. The `description` it
returns feeds the symbolic melody composer, which reads "minor" for sad moods and uses the
`key`/`tempo` directly. This is "lyrics in -> fitting music out", not lyrics-as-vocals.
"""
from __future__ import annotations

import re
from collections import Counter

# each mood maps a set of EN/FR keyword stems to concrete music params
_MOODS = [
    {
        "name": "lullaby", "tempo": 68, "key": "A minor",
        "description": "gentle soft minor-key lullaby, music box and soft piano, soothing and slow",
        "words": {"sleep", "sleepy", "night", "goodnight", "moon", "star", "stars", "dream",
                  "dreams", "hush", "lullaby", "bed", "quiet", "twinkle", "rest", "pillow",
                  "dormir", "dors", "nuit", "lune", "étoile", "étoiles", "rêve", "chut",
                  "berceuse", "lit", "calme", "brille"},
    },
    {
        "name": "playful", "tempo": 122, "key": "C",
        "description": "cheerful upbeat major-key children's tune, ukulele, glockenspiel and hand claps",
        "words": {"play", "happy", "jump", "jumping", "fun", "dance", "dancing", "sun", "sunny",
                  "smile", "laugh", "run", "clap", "hooray", "yay", "wiggle", "giggle", "bounce",
                  "jouer", "joue", "content", "saute", "danse", "soleil", "sourire", "rire",
                  "tape", "youpi"},
    },
    {
        "name": "adventure", "tempo": 134, "key": "D",
        "description": "energetic adventurous major-key kids music, light drums and bright brass",
        "words": {"adventure", "fast", "race", "explore", "fly", "flying", "rocket", "journey",
                  "brave", "hero", "quest", "sail", "ride", "zoom",
                  "aventure", "vite", "course", "explorer", "voler", "fusée", "voyage", "héros"},
    },
    {
        "name": "learning", "tempo": 104, "key": "C",
        "description": "friendly educational major-key children's music, marimba and light percussion",
        "words": {"learn", "count", "counting", "color", "colors", "colour", "shape", "shapes",
                  "abc", "number", "numbers", "letter", "letters", "two", "three", "four", "five",
                  "apprendre", "compter", "couleur", "couleurs", "forme", "formes", "chiffre",
                  "lettre", "deux", "trois"},
    },
    {
        "name": "tender", "tempo": 80, "key": "A minor",
        "description": "tender gentle minor-key melody, soft strings and piano, warm and a little sad",
        "words": {"sad", "cry", "crying", "miss", "alone", "rain", "sorry", "tear", "tears",
                  "lonely", "lost", "triste", "pleure", "manque", "seul", "pluie", "pardon",
                  "larme", "larmes"},
    },
]
_DEFAULT = {"name": "cheerful", "tempo": 100, "key": "C",
            "description": "gentle cheerful children's nursery music, soft and warm"}


def music_brief(lyrics: str) -> dict:
    """Return {mood, description, tempo, key, match_score} derived from the lyrics."""
    text = lyrics or ""
    wc = Counter(re.findall(r"[a-zà-ÿ']+", text.lower()))
    best, best_score = None, 0
    for mood in _MOODS:
        score = sum(wc[w] for w in mood["words"])
        if score > best_score:
            best, best_score = mood, score
    chosen = best if (best and best_score > 0) else _DEFAULT
    # energy nudge: exclamation marks speed it up a little (capped)
    tempo = int(chosen["tempo"] + min(16, 2 * text.count("!")))
    return {"mood": chosen["name"], "description": chosen["description"],
            "tempo": tempo, "key": chosen["key"], "match_score": best_score}
