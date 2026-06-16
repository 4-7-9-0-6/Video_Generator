"""Capability -> provider resolution.

Factories are lazy: a heavy ML provider is only imported when actually selected, so
the API boots even if optional ML wheels (piper/faster-whisper) aren't installed.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..config import settings
from .base import Availability, BaseProvider, Capability

# capability -> { provider_name -> factory() }
_FACTORIES: dict[str, dict[str, Callable[[], BaseProvider]]] = {
    Capability.IMAGE.value: {
        "sdcpp": lambda: _imp("image.sdcpp", "SDCppImageProvider"),
        "flux_local": lambda: _imp("image.flux_local", "FluxLocalImageProvider"),
        "cloudflare": lambda: _imp("image.cloudflare", "CloudflareImageProvider"),
        "pollinations": lambda: _imp("image.pollinations", "PollinationsImageProvider"),
        "higgsfield": lambda: _imp("image.higgsfield", "HiggsfieldImageProvider"),
        "mock": lambda: _imp("image.mock", "MockImageProvider"),
    },
    Capability.VIDEO.value: {
        "ffmpeg_kenburns": lambda: _imp("video.ffmpeg_kenburns", "FFmpegKenBurnsVideoProvider"),
        "depth_parallax": lambda: _imp("video.depth_parallax", "DepthParallaxVideoProvider"),
        "ltx_local": lambda: _imp("video.ltx_local", "LTXLocalVideoProvider"),
        "higgsfield": lambda: _imp("video.higgsfield", "HiggsfieldVideoProvider"),
    },
    Capability.TTS.value: {
        "piper": lambda: _imp("tts.piper", "PiperTTSProvider"),
        "xtts_local": lambda: _imp("tts.xtts_local", "XTTSLocalProvider"),
    },
    Capability.MUSIC.value: {
        "symbolic": lambda: _imp("music.symbolic", "SymbolicMusicProvider"),
        "musicgen_local": lambda: _imp("music.musicgen_local", "MusicGenLocalProvider"),
    },
    Capability.SVS.value: {
        "tts_pitch": lambda: _imp("svs.tts_pitch", "TTSPitchSVSProvider"),
        "acestep_local": lambda: _imp("svs.acestep_local", "ACEStepSVSProvider"),
    },
    Capability.LIPSYNC.value: {
        "sadtalker_local": lambda: _imp("lipsync.sadtalker_local", "SadTalkerLipSyncProvider"),
    },
    Capability.LLM.value: {
        "openrouter": lambda: _imp("llm.openrouter", "OpenRouterLLMProvider"),
        "mock": lambda: _imp("llm.mock", "MockLLMProvider"),
    },
    Capability.ALIGN.value: {
        "faster_whisper": lambda: _imp("align.faster_whisper", "FasterWhisperAlignProvider"),
    },
    Capability.CONSISTENCY.value: {
        "phash": lambda: _imp("consistency.phash", "PHashConsistencyProvider"),
        "clip": lambda: _imp("consistency.clip", "CLIPConsistencyProvider"),
    },
    Capability.STORAGE.value: {
        "local_fs": lambda: _imp("storage.local_fs", "LocalFSStorageProvider"),
    },
    Capability.ASSEMBLY.value: {
        "ffmpeg": lambda: _imp("assembly.ffmpeg", "FFmpegAssemblyProvider"),
    },
}

# Storage has no env knob — it's always local_fs at this stage.
_DEFAULTS = {Capability.STORAGE.value: "local_fs"}

_cache: dict[str, BaseProvider] = {}


def _imp(module: str, cls: str) -> BaseProvider:
    mod = __import__(f"app.providers.{module}", fromlist=[cls])
    return getattr(mod, cls)()


def _selected_name(capability: str) -> str:
    if capability in _DEFAULTS:
        return _DEFAULTS[capability]
    return settings.providers.get(capability, "")


def get_provider(capability: str | Capability, *, required: bool = True) -> BaseProvider | None:
    cap = capability.value if isinstance(capability, Capability) else capability
    name = _selected_name(cap)
    if not name:
        if required:
            raise ProviderUnavailable(f"No provider configured for capability '{cap}'.")
        return None

    key = f"{cap}:{name}"
    if key not in _cache:
        factory = _FACTORIES.get(cap, {}).get(name)
        if factory is None:
            raise ProviderUnavailable(f"Unknown provider '{name}' for capability '{cap}'.")
        _cache[key] = factory()
    provider = _cache[key]

    avail = provider.availability()
    if not avail.available:
        if required:
            raise ProviderUnavailable(
                f"Provider '{name}' ({cap}) is not ready: {avail.reason}"
                + (f"\n  Fix: {avail.install_hint}" if avail.install_hint else "")
            )
        return None
    return provider


def probe_all() -> list[dict[str, Any]]:
    """Availability of every registered provider — used by setup_check and /providers."""
    out: list[dict[str, Any]] = []
    for cap, providers in _FACTORIES.items():
        selected = _selected_name(cap)
        for name in providers:
            try:
                p = _FACTORIES[cap][name]()
                a = p.availability()
                info = p.info
                out.append({
                    "capability": cap, "provider": name, "selected": name == selected,
                    "available": a.available, "reason": a.reason,
                    "install_hint": a.install_hint, "kind": info.kind,
                    "free": info.free, "requires_gpu": info.requires_gpu,
                })
            except Exception as e:  # noqa: BLE001 — probing must never crash
                out.append({
                    "capability": cap, "provider": name, "selected": name == selected,
                    "available": False, "reason": f"import error: {e}",
                    "install_hint": "", "kind": "?", "free": None, "requires_gpu": None,
                })
    return out


class ProviderUnavailable(RuntimeError):
    pass
