"""Configuration. Reads a .env file (no external deps) into a typed Settings object.

Provider selection lives here: PROVIDER_<CAPABILITY> env vars map a capability to a
provider name. Empty/unset means the capability is disabled until configured.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader — only sets keys that aren't already in the environment."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(_BACKEND_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (_BACKEND_DIR / path).resolve()


@dataclass(frozen=True)
class Settings:
    backend_dir: Path = _BACKEND_DIR
    data_dir: Path = field(default_factory=lambda: _resolve(_env("TOONFORGE_DATA_DIR", "./data")))
    db_path: Path = field(default_factory=lambda: _resolve(_env("TOONFORGE_DB_PATH", "./data/toonforge.sqlite3")))
    host: str = field(default_factory=lambda: _env("TOONFORGE_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(_env("TOONFORGE_PORT", "8000")))

    languages: tuple[str, ...] = field(
        default_factory=lambda: tuple(x for x in _env("TOONFORGE_LANGUAGES", "en,fr").split(",") if x)
    )
    default_language: str = field(default_factory=lambda: _env("TOONFORGE_DEFAULT_LANGUAGE", "en"))

    # capability -> provider name
    providers: dict[str, str] = field(
        default_factory=lambda: {
            "image": _env("PROVIDER_IMAGE", "sdcpp"),
            "tts": _env("PROVIDER_TTS", "piper"),
            "align": _env("PROVIDER_ALIGN", "faster_whisper"),
            "music": _env("PROVIDER_MUSIC", "symbolic"),
            "assembly": _env("PROVIDER_ASSEMBLY", "ffmpeg"),
            "consistency": _env("PROVIDER_CONSISTENCY", "phash"),
            "video": _env("PROVIDER_VIDEO", ""),
            "svs": _env("PROVIDER_SVS", "tts_pitch"),
            "lipsync": _env("PROVIDER_LIPSYNC", ""),
            "llm": _env("PROVIDER_LLM", "openrouter"),
        }
    )

    # cloud keys
    pollinations_token: str = field(default_factory=lambda: _env("POLLINATIONS_TOKEN"))
    higgsfield_api_key: str = field(default_factory=lambda: _env("HIGGSFIELD_API_KEY"))
    # Cloudflare Workers AI — free modern Flux (no GPU, no card, ~10k neurons/day)
    cloudflare_account_id: str = field(default_factory=lambda: _env("CLOUDFLARE_ACCOUNT_ID"))
    cloudflare_api_token: str = field(default_factory=lambda: _env("CLOUDFLARE_API_TOKEN"))
    cloudflare_image_model: str = field(default_factory=lambda: _env("CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell"))
    cloudflare_steps: int = field(default_factory=lambda: int(_env("CLOUDFLARE_STEPS", "6")))
    # OpenRouter LLM (free `:free` models) — the only cloud capability, for songwriting
    openrouter_api_key: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))
    openrouter_model: str = field(default_factory=lambda: _env("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"))
    openrouter_api_base: str = field(default_factory=lambda: _env("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1"))
    higgsfield_api_base: str = field(default_factory=lambda: _env("HIGGSFIELD_API_BASE", "https://api.higgsfield.ai"))

    # piper
    piper_models_dir: Path = field(default_factory=lambda: _resolve(_env("PIPER_MODELS_DIR", "./models/piper")))
    piper_voice_en: str = field(default_factory=lambda: _env("PIPER_VOICE_EN", "en_US-amy-medium"))
    piper_voice_fr: str = field(default_factory=lambda: _env("PIPER_VOICE_FR", "fr_FR-siwis-medium"))

    whisper_model: str = field(default_factory=lambda: _env("WHISPER_MODEL", "base"))

    # local SD-Turbo (stable-diffusion.cpp) — offline CPU image generation
    sdcpp_steps: int = field(default_factory=lambda: int(_env("SDCPP_STEPS", "4")))
    sdcpp_cfg: float = field(default_factory=lambda: float(_env("SDCPP_CFG", "1.0")))
    sdcpp_max_side: int = field(default_factory=lambda: int(_env("SDCPP_MAX_SIDE", "640")))
    sdcpp_threads: int = field(default_factory=lambda: int(_env("SDCPP_THREADS", str(os.cpu_count() or 4))))
    # filename substring that selects a dedicated anime model for anime_* styles (if installed)
    sd_anime_model: str = field(default_factory=lambda: _env("SD_ANIME_MODEL", "anime"))

    # GPU-phase providers (flux/ltx/xtts/musicgen) — used only when PROVIDER_*=*_local on a CUDA host
    gpu_usd_per_hour: float = field(default_factory=lambda: float(_env("GPU_USD_PER_HOUR", "0.0")))
    gpu_offload: bool = field(default_factory=lambda: _env("GPU_OFFLOAD", "0") in ("1", "true", "True"))
    flux_model: str = field(default_factory=lambda: _env("FLUX_MODEL", "black-forest-labs/FLUX.1-schnell"))
    flux_steps: int = field(default_factory=lambda: int(_env("FLUX_STEPS", "4")))
    ltx_model: str = field(default_factory=lambda: _env("LTX_MODEL", "Lightricks/LTX-Video"))
    ltx_steps: int = field(default_factory=lambda: int(_env("LTX_STEPS", "40")))
    # LTX attention memory grows with (frames x width x height)^2. These caps keep a single
    # attention matrix within a 16 GB T4; the final clip is scaled back to the export size by
    # ffmpeg, so only motion detail is affected. Raise them on a bigger GPU.
    ltx_max_width: int = field(default_factory=lambda: int(_env("LTX_MAX_WIDTH", "640")))
    ltx_max_height: int = field(default_factory=lambda: int(_env("LTX_MAX_HEIGHT", "384")))
    ltx_max_frames: int = field(default_factory=lambda: int(_env("LTX_MAX_FRAMES", "49")))
    xtts_model: str = field(default_factory=lambda: _env("XTTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2"))
    xtts_speaker_wav: str = field(default_factory=lambda: _env("XTTS_SPEAKER_WAV", ""))
    musicgen_model: str = field(default_factory=lambda: _env("MUSICGEN_MODEL", "facebook/musicgen-small"))
    clip_model: str = field(default_factory=lambda: _env("CLIP_MODEL", "openai/clip-vit-base-patch32"))
    ip_guard_threshold: float = field(default_factory=lambda: float(_env("IP_GUARD_THRESHOLD", "0.5")))
    # ACE-Step (GPU singing) + SadTalker (GPU lip-sync) — used by scripts/gpu_render.py on free GPU
    acestep_checkpoint_dir: str = field(default_factory=lambda: _env("ACESTEP_CHECKPOINT_DIR"))
    acestep_duration_s: float = field(default_factory=lambda: float(_env("ACESTEP_DURATION_S", "45")))
    acestep_steps: int = field(default_factory=lambda: int(_env("ACESTEP_STEPS", "27")))
    acestep_guidance: float = field(default_factory=lambda: float(_env("ACESTEP_GUIDANCE", "15")))
    sadtalker_dir: str = field(default_factory=lambda: _env("SADTALKER_DIR"))

    # quality gates (spec section 6)
    consistency_min_score: float = field(default_factory=lambda: float(_env("CONSISTENCY_MIN_SCORE", "0.85")))
    lipsync_max_offset_ms: int = field(default_factory=lambda: int(_env("LIPSYNC_MAX_OFFSET_MS", "80")))

    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir().mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
