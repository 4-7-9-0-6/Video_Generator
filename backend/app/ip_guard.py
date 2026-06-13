"""Image-based IP-similarity guard (spec §A.7) — catches generated characters that *look
like* a protected IP, complementing the prompt name-blocklist in safety.py.

Method: zero-shot CLIP classification. We score the generated image against text labels for
well-known protected characters AND a few "original character" anchors, then softmax. If a
protected label wins with enough confidence, we flag it. No copyrighted reference images are
stored — CLIP's image↔text alignment does the work. Only active when the consistency provider
is CLIP (`classify`); on the pHash default this is a graceful no-op.
"""
from __future__ import annotations

# (label shown to the user, CLIP text prompt) for well-known protected characters
KNOWN_IPS: list[tuple[str, str]] = [
    ("Mickey Mouse", "Mickey Mouse, the Disney cartoon mouse with round black ears"),
    ("Minnie Mouse", "Minnie Mouse, Disney cartoon mouse with a bow"),
    ("Elsa (Frozen)", "Elsa from Disney Frozen, ice queen with a blue dress and braid"),
    ("Peppa Pig", "Peppa Pig, the pink cartoon pig"),
    ("CoComelon JJ", "JJ from CoComelon, a 3D cartoon baby"),
    ("Bluey", "Bluey, the blue cartoon dog puppy"),
    ("Paw Patrol pup", "a Paw Patrol cartoon rescue puppy in uniform"),
    ("SpongeBob", "SpongeBob SquarePants, the yellow square sponge"),
    ("Pikachu", "Pikachu, the yellow Pokemon with red cheeks"),
    ("Super Mario", "Super Mario, Nintendo plumber with red hat and moustache"),
    ("Minion", "a Minion from Despicable Me, yellow capsule creature with goggles"),
    ("Hello Kitty", "Hello Kitty, white cat with a red bow"),
]
# anchors so an original design has somewhere to land (avoids forcing a false IP match)
_ANCHORS: list[tuple[str, str]] = [
    ("original", "an original cartoon character, not from any franchise"),
    ("original", "a generic 3D toddler cartoon character"),
    ("original", "a simple children's storybook illustration character"),
]


def supported(provider: object) -> bool:
    return callable(getattr(provider, "classify", None))


def check_image(image: bytes, provider: object, *, threshold: float = 0.5) -> dict:
    """Return {available, flagged, top_ip, score, scores}. No-op (available=False) unless the
    provider supports zero-shot CLIP classification."""
    if not supported(provider):
        return {"available": False, "flagged": False, "top_ip": None, "score": 0.0}

    labels = KNOWN_IPS + _ANCHORS
    try:
        probs = provider.classify(image, [p for _, p in labels])  # type: ignore[attr-defined]
    except Exception as e:  # noqa: BLE001 — the guard must never break generation
        return {"available": False, "flagged": False, "top_ip": None, "score": 0.0,
                "error": str(e)}

    ip_n = len(KNOWN_IPS)
    best_i = max(range(len(probs)), key=lambda i: probs[i])   # overall winner (incl. anchors)
    # flag only when a protected IP beats every "original" anchor and clears the threshold,
    # so a generic original design (which lands on an anchor) is never flagged
    flagged = best_i < ip_n and probs[best_i] >= threshold
    ip_scores = sorted(((KNOWN_IPS[i][0], probs[i]) for i in range(ip_n)),
                       key=lambda x: x[1], reverse=True)
    top_ip, top_score = ip_scores[0]
    return {
        "available": True,
        "flagged": flagged,
        "top_ip": top_ip,
        "score": round(top_score, 4),
        "ip_mass": round(float(sum(probs[:ip_n])), 4),
        "scores": {name: round(s, 4) for name, s in ip_scores[:5]},
    }
