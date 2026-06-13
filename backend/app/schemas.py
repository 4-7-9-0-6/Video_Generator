"""Pydantic request models for the API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    style_preset: str = "3d_toddler_original"
    language: str = "en"
    fps: int = 24
    width: int = 1920
    height: int = 1080


class CharacterCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    style_preset: str = "3d_toddler_original"
    palette: list[str] = Field(default_factory=list)
    style_tokens: list[str] = Field(default_factory=list)
    negative_prompt: str = ""
    sheets: list[str] = Field(default_factory=lambda: ["turnaround", "expressions", "poses"])


class CharacterEdit(BaseModel):
    """Instruction-based edit, e.g. 'change her t-shirt to green' (spec §A.5)."""
    instruction: str = Field(min_length=1, max_length=500)
    sheets: list[str] = Field(default_factory=lambda: ["turnaround", "expressions", "poses"])
    regenerate: bool = True


class TTSRequest(BaseModel):
    """VoiceLab speech (spec §B.1)."""
    text: str = Field(min_length=1, max_length=5000)
    project_id: str | None = None
    language: str = "en"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class FromPromptRequest(BaseModel):
    """One-shot: a topic prompt → a complete song-video project (lyrics+chorus, characters,
    scenes). The LLM writes the song; the rest of the pipeline builds the video."""
    prompt: str = Field(min_length=1, max_length=2000)
    style_preset: str = "anime_cyberpunk"
    language: str = "en"
    scenes: int = Field(default=8, ge=2, le=16)
    safe_mode: bool = False          # general content by default (not just child-safe)
    render: bool = True              # also enqueue character-sheet generation
    default_background: str = ""


class PlanRequest(BaseModel):
    """Script → shots (spec §C.1)."""
    script: str = Field(min_length=1, max_length=20000)
    default_background: str = ""
    replace: bool = True


class ShotPatch(BaseModel):
    text: str | None = None
    characters: list[str] | None = None
    camera: str | None = None
    background: str | None = None
    duration_s: float | None = Field(default=None, ge=0.5, le=60.0)


class ShotInsert(BaseModel):
    """Insert a transcript line (spec §D transcript editing)."""
    text: str = Field(min_length=1, max_length=2000)
    after_id: str | None = None          # insert after this shot; None = append
    characters: list[str] = Field(default_factory=list)
    camera: str = "static"
    background: str = ""
    duration_s: float = Field(default=4.0, ge=0.5, le=60.0)


class ReorderRequest(BaseModel):
    order: list[str]                      # full permutation of the project's shot ids


class MelodyRequest(BaseModel):
    """VoiceLab melody-from-text (spec §B.2c). Produces a MIDI the SVS will sing."""
    description: str = Field(min_length=1, max_length=500)
    project_id: str | None = None
    key: str = "C"
    tempo: int = Field(default=100, ge=40, le=220)
    duration_s: float = Field(default=20.0, ge=2.0, le=120.0)
    audio: bool = False          # also render a playable WAV (numpy synth), not just MIDI


class ThumbnailRequest(BaseModel):
    """YouTube thumbnail proposals (1280x720) — character-locked hero art + bold title."""
    title: str | None = Field(default=None, max_length=120)
    count: int = Field(default=3, ge=1, le=6)
    character_id: str | None = None      # which character to feature; None = first in project
    background: str = ""


class SingRequest(BaseModel):
    """Singing Voice Synthesis (spec §B.2) — sing lyrics to an auto-composed melody."""
    lyrics: str = Field(min_length=1, max_length=2000)
    project_id: str | None = None
    language: str = "en"
    key: str = "C"
    tempo: int = Field(default=100, ge=40, le=220)
    vibrato: float = Field(default=0.3, ge=0.0, le=1.0)


class ExportRequest(BaseModel):
    """Episode export (spec Module D / §C.5)."""
    preset: str = "youtube_1080p"
    voice: bool = True
    sing: bool = False           # override: sing the lyrics (melody-pitched) instead of speaking
    sing_key: str = "auto"       # "auto" (from lyrics) or a key like "C" / "A minor"
    sing_tempo: int = Field(default=0, ge=0, le=220)   # 0 = auto (from lyrics mood)
    sing_vibrato: float = Field(default=0.3, ge=0.0, le=1.0)
    lipsync: bool = False        # audio-driven mouth flap (CPU; replaces Ken Burns on that shot)
    subtitles: bool = True
    word_subtitles: bool = True
    music: bool = False
    music_auto: bool = True      # derive mood/tempo/key from the lyrics (ignores music_description)
    music_description: str = "gentle cheerful children's nursery music"
    music_tempo: int = Field(default=96, ge=40, le=200)
    smart_reframe: bool = True   # content-aware crop to the export aspect (e.g. 16:9 -> 9:16 Shorts)
