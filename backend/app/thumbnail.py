"""YouTube thumbnail proposals (1280x720) — character-locked hero art + bold title.

A thumbnail = an eye-catching, character-consistent hero image (reusing the same
Character Lock prompt as shots, so the star looks like themselves) composited with a
punchy, outlined title via PIL — all local, all free. `build_variants` proposes N distinct
framings (emotion / subject side / accent); `compose` is a pure image op (offline-testable).
"""
from __future__ import annotations

import io
from typing import Any

from . import foundry

THUMB_W, THUMB_H = 1280, 720

# distinct hero treatments — varied so the 3 proposals don't look the same
_EMOTIONS = [
    "big joyful smile, sparkling eyes",
    "surprised excited expression, wide eyes, open mouth",
    "laughing happily, full of energy",
    "curious wonder, looking up",
    "proud confident grin",
    "playful wink",
]
_ACCENTS = [
    (255, 209, 0),   # sunny yellow
    (255, 92, 124),  # coral pink
    (64, 196, 255),  # sky blue
    (124, 224, 122), # mint green
    (186, 130, 255), # soft purple
    (255, 148, 64),  # orange
]
_THUMB_PUNCH = ("vibrant saturated colors, dramatic rim lighting, bold dynamic composition, "
                "sharp focus, clean simple background with strong color, eye-catching, "
                "high-energy youtube thumbnail")


def _accent_for(character: dict[str, Any] | None, i: int) -> tuple[int, int, int]:
    """On-brand but varied: rotate through the character's palette colors per variant,
    falling back to the bright accent set when no usable palette is set."""
    parsed = [rgb for hexc in ((character or {}).get("palette") or [])
              if (rgb := _hex_to_rgb(hexc)) is not None]
    if parsed:
        return parsed[i % len(parsed)]
    return _ACCENTS[i % len(_ACCENTS)]


def _hex_to_rgb(s: str) -> tuple[int, int, int] | None:
    s = s.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return None
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return None


def default_title(project: dict[str, Any]) -> str:
    return str(project.get("name") or "My Episode")


def build_variants(project: dict[str, Any], character: dict[str, Any] | None,
                   title: str, count: int, background: str = "") -> list[dict[str, Any]]:
    """Return `count` thumbnail recipes: prompt + seed + composition for each proposal."""
    count = max(1, min(count, len(_EMOTIONS)))
    style = foundry.STYLE_PRESETS.get(project.get("style_preset", ""),
                                      foundry.STYLE_PRESETS["3d_toddler_original"])
    base_seed = foundry.identity_seed(character["id"]) if character else 1234
    variants: list[dict[str, Any]] = []
    for i in range(count):
        side = "right" if i % 2 == 0 else "left"
        emotion = _EMOTIONS[i % len(_EMOTIONS)]
        bg = background or "bright colorful playful background"
        if character:
            hero = foundry.build_character_prompt(
                character, pose=f"{emotion}, head and shoulders close-up, "
                                 f"positioned on the {side} side of the frame",
                framing="close-up portrait", scene=bg,
            )
        else:
            hero = f"{bg}. {emotion}. close-up. {style}"
        prompt = f"{hero}. {_THUMB_PUNCH}"
        variants.append({
            "prompt": prompt,
            "negative": (character or {}).get("negative_prompt", ""),
            "seed": base_seed + 1000 + i * 7,
            "subject_side": side,
            "text_side": "left" if side == "right" else "right",
            "accent": _accent_for(character, i),
            "title": title,
            "emotion": emotion,
        })
    return variants


# ---------- PIL compositing (pure, offline) ----------

def _load_font(size: int):
    from PIL import ImageFont
    for path in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                 "C:/Windows/Fonts/impact.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1 scalable default
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_title(draw, text: str, max_w: int, max_h: int) -> tuple[Any, list[str]]:
    """Largest bold font (with wrapping) whose block fits the text box."""
    for size in range(120, 33, -6):
        font = _load_font(size)
        lines = _wrap(draw, text, font, max_w)
        line_h = (font.getbbox("Ag")[3] - font.getbbox("Ag")[1]) + size // 5
        if line_h * len(lines) <= max_h and all(
                draw.textlength(ln, font=font) <= max_w for ln in lines):
            return font, lines
    font = _load_font(34)
    return font, _wrap(draw, text, font, max_w)


def compose(hero_png: bytes, title: str, *, subject_side: str = "right",
            accent: tuple[int, int, int] = (255, 209, 0),
            text_side: str = "left") -> bytes:
    """Composite a 1280x720 thumbnail: hero art, legibility gradient, accent bar, bold title."""
    from PIL import Image, ImageDraw

    hero = Image.open(io.BytesIO(hero_png)).convert("RGB")
    hero = _cover(hero, THUMB_W, THUMB_H)
    img = hero.copy()

    # legibility gradient on the text side (so white title pops over any art)
    grad = Image.new("L", (THUMB_W, 1))
    for x in range(THUMB_W):
        f = (1 - x / THUMB_W) if text_side == "left" else (x / THUMB_W)
        grad.putpixel((x, 0), int(225 * max(0.0, f - 0.15)))
    grad = grad.resize((THUMB_W, THUMB_H))
    shade = Image.new("RGB", (THUMB_W, THUMB_H), (0, 0, 0))
    img = Image.composite(shade, img, grad)

    draw = ImageDraw.Draw(img)
    margin = 56
    box_w = int(THUMB_W * 0.56)
    x0 = margin if text_side == "left" else THUMB_W - margin - box_w
    font, lines = _fit_title(draw, title.upper(), box_w, int(THUMB_H * 0.62))

    line_h = (font.getbbox("Ag")[3] - font.getbbox("Ag")[1]) + font.size // 5
    total_h = line_h * len(lines)
    y = (THUMB_H - total_h) // 2

    # accent bar beside the title block
    bar_x = x0 - 22 if text_side == "left" else x0 + box_w + 6
    draw.rectangle([bar_x, y, bar_x + 14, y + total_h], fill=accent)

    stroke = max(3, font.size // 12)
    for ln in lines:
        lw = draw.textlength(ln, font=font)
        lx = x0 if text_side == "left" else x0 + box_w - lw
        draw.text((lx + 4, y + 5), ln, font=font, fill=(0, 0, 0))  # drop shadow
        draw.text((lx, y), ln, font=font, fill=(255, 255, 255),
                  stroke_width=stroke, stroke_fill=(20, 20, 20))
        y += line_h

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _cover(img, w: int, h: int):
    """Resize+center-crop so the image fully covers w x h (no letterboxing)."""
    from PIL import Image
    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    nw, nh = max(w, int(src_w * scale)), max(h, int(src_h * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))
