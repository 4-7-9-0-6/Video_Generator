"""Deterministic mock LLM — OFFLINE TESTS ONLY. Returns a fixed, valid song JSON so the
songwriter + prompt-to-video flow can be tested without a network/key. PROVIDER_LLM=mock."""
from __future__ import annotations

import json

from ..base import Availability, Capability, LLMProvider, ProviderInfo

_SONG = {
    "title": "Circuit Heart",
    "mood": "adventure",
    "characters": [
        {"name": "Volt", "description": "a brave small robot with a glowing blue chest core, "
                                        "rounded friendly body, big expressive optic eyes"},
        {"name": "Mira", "description": "a kind girl engineer with short teal hair and goggles"},
    ],
    "lines": [
        {"section": "intro", "text": "In a city of steel and rain,", "characters": ["Volt"]},
        {"section": "verse", "text": "A little robot wakes again.", "characters": ["Volt"]},
        {"section": "verse", "text": "Mira calls him from the dark,", "characters": ["Mira", "Volt"]},
        {"section": "chorus", "text": "Rise up, little machine, light the night!", "characters": ["Volt"]},
        {"section": "chorus", "text": "Rise up, little machine, light the night!", "characters": ["Volt", "Mira"]},
        {"section": "verse", "text": "Through the wires and neon glow,", "characters": ["Volt"]},
        {"section": "chorus", "text": "Rise up, little machine, light the night!", "characters": ["Volt", "Mira"]},
    ],
}


class MockLLMProvider(LLMProvider):
    info = ProviderInfo(name="mock", capability=Capability.LLM, kind="local",
                        free=True, requires_gpu=False)

    def availability(self) -> Availability:
        return Availability(True, reason="deterministic test LLM")

    async def complete(self, prompt: str, *, system: str = "", temperature: float = 0.7,
                       max_tokens: int = 2048, **kw: object) -> str:
        return json.dumps(_SONG)
