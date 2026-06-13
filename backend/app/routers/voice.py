"""VoiceLab endpoints (spec Module B) — local CPU speech + melody.

TTS and melody are fast on CPU, so these are synchronous (no job round-trip): they
generate, persist an audio asset, and return its id/URL immediately.
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException

from .. import models, music_synth, voicelab
from ..config import settings
from ..providers.base import Capability
from ..providers.music.symbolic import melody_notes
from ..providers.registry import ProviderUnavailable, get_provider
from ..schemas import MelodyRequest, SingRequest, TTSRequest

router = APIRouter(prefix="/voice", tags=["voice"])


def _require(capability: Capability):
    try:
        return get_provider(capability)
    except ProviderUnavailable as e:
        raise HTTPException(503, str(e))


def _check_project(project_id: str | None) -> None:
    if project_id and models.get("projects", project_id) is None:
        raise HTTPException(404, "project not found")


@router.get("/voices")
def list_voices() -> dict:
    tts = get_provider(Capability.TTS, required=False)
    return {
        "available": tts is not None,
        "languages": list(settings.languages),
        "voices": {
            "en": settings.piper_voice_en,
            "fr": settings.piper_voice_fr,
        },
    }


@router.post("/tts")
async def tts(body: TTSRequest) -> dict:
    if body.language not in settings.languages:
        raise HTTPException(422, f"language must be one of {list(settings.languages)}")
    _check_project(body.project_id)
    provider = _require(Capability.TTS)
    storage = get_provider(Capability.STORAGE)

    result = await provider.synthesize(body.text, language=body.language, speed=body.speed)
    name = f"{models.new_id('tts_')}.wav"
    rel = storage.put(result.data, name=name, subdir=f"voice/{body.project_id or 'scratch'}")
    asset = models.create_asset(
        kind="audio", path=rel, project_id=body.project_id, mime=result.mime,
        sha256=hashlib.sha256(result.data).hexdigest(), provider="piper",
        meta={"kind": "speech", "language": body.language, "text": body.text,
              "voice": result.meta.get("voice"), "speed": body.speed},
    )
    return {
        "asset_id": asset["id"], "url": f"/assets/{asset['id']}",
        "mime": result.mime, "duration_s": round(voicelab.wav_duration(result.data), 3),
        "language": body.language, "voice": result.meta.get("voice"),
    }


@router.post("/sing")
async def sing(body: SingRequest) -> dict:
    if body.language not in settings.languages:
        raise HTTPException(422, f"language must be one of {list(settings.languages)}")
    _check_project(body.project_id)
    provider = _require(Capability.SVS)
    storage = get_provider(Capability.STORAGE)

    result = await provider.sing(body.lyrics, language=body.language,
                                 key=body.key, tempo=body.tempo, vibrato=body.vibrato)
    name = f"{models.new_id('sing_')}.wav"
    rel = storage.put(result.data, name=name, subdir=f"voice/{body.project_id or 'scratch'}")
    asset = models.create_asset(
        kind="audio", path=rel, project_id=body.project_id, mime=result.mime,
        sha256=hashlib.sha256(result.data).hexdigest(), provider="tts_pitch",
        meta={"kind": "singing", "language": body.language, "lyrics": body.lyrics,
              "key": body.key, "tempo": body.tempo},
    )
    return {
        "asset_id": asset["id"], "url": f"/assets/{asset['id']}",
        "mime": result.mime, "duration_s": round(voicelab.wav_duration(result.data), 3),
        "language": body.language, "key": body.key, "tempo": body.tempo,
        "note": "melody-pitched TTS (local CPU, novelty quality)",
    }


@router.post("/melody")
async def melody(body: MelodyRequest) -> dict:
    _check_project(body.project_id)
    provider = _require(Capability.MUSIC)
    storage = get_provider(Capability.STORAGE)

    result = await provider.compose(body.description, duration_s=body.duration_s,
                                    key=body.key, tempo=body.tempo)
    name = f"{models.new_id('mel_')}.mid"
    rel = storage.put(result.data, name=name, subdir=f"voice/{body.project_id or 'scratch'}")
    asset = models.create_asset(
        kind="audio", path=rel, project_id=body.project_id, mime=result.mime,
        sha256=hashlib.sha256(result.data).hexdigest(), provider="symbolic",
        meta={"kind": "melody", **result.meta, "description": body.description},
    )
    out = {"asset_id": asset["id"], "url": f"/assets/{asset['id']}",
           "mime": result.mime, "meta": result.meta}

    if body.audio:
        notes, _info = melody_notes(body.description, duration_s=body.duration_s,
                                    key=body.key, tempo=body.tempo)
        wav = music_synth.synth_wav(notes, total_s=body.duration_s)
        wav_rel = storage.put(wav, name=f"{models.new_id('mel_')}.wav",
                              subdir=f"voice/{body.project_id or 'scratch'}")
        wav_asset = models.create_asset(
            kind="audio", path=wav_rel, project_id=body.project_id, mime="audio/wav",
            sha256=hashlib.sha256(wav).hexdigest(), provider="symbolic",
            meta={"kind": "melody_audio", "description": body.description})
        out["audio_asset_id"] = wav_asset["id"]
        out["audio_url"] = f"/assets/{wav_asset['id']}"
        out["audio_duration_s"] = round(voicelab.wav_duration(wav), 2)
    return out
