"""Pollinations image provider — free cloud generation, no local GPU required.

Default image/character generator on a CPU-only machine. Real, working provider:
https://image.pollinations.ai/prompt/{prompt}

Pollinations' anonymous tier is rate-limited (≈1 concurrent request per IP) and returns
HTTP 402 when that queue is full. This client:
  * retries 402/429 with backoff (transient rate-limit, not a hard failure), and
  * sends POLLINATIONS_TOKEN (free from https://enter.pollinations.ai) when set, which
    removes the rate limit. Strongly recommended for reliable use.
"""
from __future__ import annotations

import asyncio
import urllib.parse

import httpx

from ...config import settings
from ..base import Availability, Capability, Cost, GenResult, ImageProvider, ProviderInfo

_BASE = "https://image.pollinations.ai/prompt/"
_RATE_LIMIT_CODES = {402, 429}


class PollinationsRateLimited(RuntimeError):
    pass


class PollinationsImageProvider(ImageProvider):
    info = ProviderInfo(
        name="pollinations", capability=Capability.IMAGE, kind="cloud",
        free=True, requires_gpu=False,
    )

    def availability(self) -> Availability:
        if settings.pollinations_token:
            return Availability(True, reason="free cloud (token set — no rate limit)")
        return Availability(
            True,
            reason="free keyless cloud — anonymous tier is rate-limited (~1 concurrent/IP)",
            install_hint="Set POLLINATIONS_TOKEN (free: https://enter.pollinations.ai) "
                         "to remove the rate limit.",
        )

    def estimate_cost(self, **kwargs: object) -> Cost:
        return Cost(gpu_seconds=0.0, usd=0.0)

    async def generate(self, prompt: str, *, negative: str = "", width: int = 1024,
                       height: int = 1024, seed: int | None = None,
                       reference_images: list[bytes] | None = None,
                       **kw: object) -> GenResult:
        full_prompt = prompt if not negative else f"{prompt} . avoid: {negative}"
        url = f"{_BASE}{urllib.parse.quote(full_prompt, safe='')}"
        params: dict[str, str] = {
            "width": str(width), "height": str(height),
            "model": str(kw.get("model", "flux")), "nologo": "true",
        }
        if seed is not None:
            params["seed"] = str(seed)
        if settings.pollinations_token:
            params["token"] = settings.pollinations_token

        max_attempts = int(kw.get("max_attempts", 5))
        backoff = 3.0
        last_status = None
        async with httpx.AsyncClient(timeout=120) as client:
            for attempt in range(max_attempts):
                resp = await client.get(url, params=params)
                if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
                    mime = resp.headers["content-type"].split(";")[0]
                    return GenResult(
                        data=resp.content, mime=mime, cost=Cost(),
                        meta={"provider": "pollinations", "seed": seed,
                              "prompt": full_prompt, "width": width, "height": height,
                              "attempts": attempt + 1},
                    )
                last_status = resp.status_code
                if resp.status_code in _RATE_LIMIT_CODES:
                    await asyncio.sleep(backoff)
                    backoff *= 1.6
                    continue
                resp.raise_for_status()

        raise PollinationsRateLimited(
            f"Pollinations rate-limited after {max_attempts} attempts (last status {last_status}). "
            "Set POLLINATIONS_TOKEN (free: https://enter.pollinations.ai) to remove the limit, "
            "or switch PROVIDER_IMAGE."
        )
