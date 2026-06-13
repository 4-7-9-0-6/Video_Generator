"""Provider abstraction — the moat (spec §4: "non-negotiable").

Every AI capability is an interface with at least one real implementation. Providers
self-report availability so the app never hard-crashes on a missing model/key/GPU,
and self-report cost so the UI can show GPU-seconds and $ before a render.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Capability(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    TTS = "tts"
    SVS = "svs"
    MUSIC = "music"
    LIPSYNC = "lipsync"
    ALIGN = "align"
    CONSISTENCY = "consistency"
    STORAGE = "storage"
    ASSEMBLY = "assembly"
    LLM = "llm"


@dataclass(frozen=True)
class Cost:
    gpu_seconds: float = 0.0
    usd: float = 0.0


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    capability: Capability
    kind: str            # "local" | "cloud"
    free: bool
    requires_gpu: bool
    languages: tuple[str, ...] = ()


@dataclass
class Availability:
    available: bool
    reason: str = ""
    install_hint: str = ""


@dataclass
class GenResult:
    data: bytes
    mime: str
    cost: Cost = field(default_factory=Cost)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class WordStamp:
    word: str
    start: float
    end: float


class BaseProvider(ABC):
    info: ProviderInfo

    @abstractmethod
    def availability(self) -> Availability: ...

    def estimate_cost(self, **kwargs: Any) -> Cost:  # noqa: ARG002
        return Cost()


# --- capability interfaces ---

class ImageProvider(BaseProvider):
    @abstractmethod
    async def generate(self, prompt: str, *, negative: str = "", width: int = 1024,
                       height: int = 1024, seed: int | None = None,
                       reference_images: list[bytes] | None = None,
                       **kw: Any) -> GenResult: ...


class VideoProvider(BaseProvider):
    @abstractmethod
    async def animate(self, image: bytes, *, motion: str = "static",
                      duration_s: float = 4.0, fps: int = 24,
                      prompt: str = "", **kw: Any) -> GenResult: ...


class TTSProvider(BaseProvider):
    @abstractmethod
    async def synthesize(self, text: str, *, language: str = "en", voice: str = "",
                         speed: float = 1.0, pitch: float = 0.0,
                         emotion: str = "neutral", **kw: Any) -> GenResult: ...


class SVSProvider(BaseProvider):
    @abstractmethod
    async def sing(self, lyrics: str, *, melody_midi: bytes | None = None,
                   language: str = "en", voice: str = "", key: str = "C",
                   tempo: int = 100, vibrato: float = 0.3, breathiness: float = 0.2,
                   **kw: Any) -> GenResult: ...


class MusicProvider(BaseProvider):
    @abstractmethod
    async def compose(self, description: str, *, duration_s: float = 30.0,
                      key: str = "C", tempo: int = 100, **kw: Any) -> GenResult: ...


class LipSyncProvider(BaseProvider):
    @abstractmethod
    async def apply(self, video: bytes, audio: bytes, **kw: Any) -> GenResult: ...


class AlignProvider(BaseProvider):
    @abstractmethod
    async def align(self, audio: bytes, *, text: str = "",
                    language: str = "en") -> list[WordStamp]: ...


class ConsistencyProvider(BaseProvider):
    """Character drift + IP-similarity guard (spec §A.7, §6). Returns a vector and a
    0..1 similarity (1.0 = identical). On CPU this is perceptual-hash based; swap to
    CLIP/ArcFace when a GPU is available — same interface."""

    @abstractmethod
    def embed(self, image: bytes) -> tuple[str, int, bytes]:  # (space, dim, vector_bytes)
        ...

    @abstractmethod
    def similarity(self, a: bytes, b: bytes) -> float:
        """Whole-image structural similarity (pHash). High only for near-identical framings."""

    @abstractmethod
    def palette_similarity(self, a: bytes, b: bytes) -> float:
        """Color/palette similarity — robust to pose/view changes, so it's the cross-view
        identity-drift signal on CPU (a character keeps its colors across poses)."""


class LLMProvider(BaseProvider):
    """Text generation (spec: prompt-enhancement, song/script writing). The only cloud-by-
    default capability — used for the creative *text*, while images/voice/music/video stay
    local. A free OpenRouter `:free` model satisfies this at $0."""

    @abstractmethod
    async def complete(self, prompt: str, *, system: str = "", temperature: float = 0.7,
                       max_tokens: int = 2048, **kw: Any) -> str: ...


class StorageProvider(BaseProvider):
    @abstractmethod
    def put(self, data: bytes, *, name: str, subdir: str = "") -> str:  # returns rel path
        ...

    @abstractmethod
    def open(self, rel_path: str) -> bytes: ...

    @abstractmethod
    def abs_path(self, rel_path: str) -> str: ...


class AssemblyProvider(BaseProvider):
    @abstractmethod
    async def mux(self, *, video_path: str | None, audio_paths: list[str],
                  out_name: str, fps: int = 24) -> str: ...

    @abstractmethod
    async def burn_subtitles(self, *, video_path: str, srt_path: str,
                             out_name: str) -> str: ...
