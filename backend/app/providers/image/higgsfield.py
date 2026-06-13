"""Higgsfield image provider — optional higher-quality cloud generation.

Disabled by default (no API key). When HIGGSFIELD_API_KEY is set, this makes a real
HTTP call to the Higgsfield API. Endpoint paths are configurable via HIGGSFIELD_API_BASE
because they vary by plan; adjust to match your account's docs.

Note: the Higgsfield *MCP* server connected in a Claude session is a separate channel
(driven by the assistant, not this standalone app). This client is for the app itself.
"""
from __future__ import annotations

import asyncio

import httpx

from ...config import settings
from ..base import Availability, Capability, Cost, GenResult, ImageProvider, ProviderInfo


class HiggsfieldImageProvider(ImageProvider):
    info = ProviderInfo(
        name="higgsfield", capability=Capability.IMAGE, kind="cloud",
        free=False, requires_gpu=False,
    )

    def availability(self) -> Availability:
        if not settings.higgsfield_api_key:
            return Availability(
                False, reason="HIGGSFIELD_API_KEY not set",
                install_hint="Add HIGGSFIELD_API_KEY to backend/.env to enable.",
            )
        return Availability(True)

    async def generate(self, prompt: str, *, negative: str = "", width: int = 1024,
                       height: int = 1024, seed: int | None = None,
                       reference_images: list[bytes] | None = None,
                       **kw: object) -> GenResult:
        headers = {"Authorization": f"Bearer {settings.higgsfield_api_key}"}
        payload = {
            "prompt": prompt, "negative_prompt": negative,
            "width": width, "height": height, "seed": seed,
        }
        base = settings.higgsfield_api_base.rstrip("/")
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(f"{base}/v1/images/generate", json=payload, headers=headers)
            resp.raise_for_status()
            body = resp.json()
            image_url = body.get("url") or body["data"][0]["url"]
            # poll-free path: fetch the produced image bytes
            for _ in range(60):
                img = await client.get(image_url, headers=headers)
                if img.status_code == 200 and img.content:
                    break
                await asyncio.sleep(2)
            img.raise_for_status()
            data = img.content
        return GenResult(
            data=data, mime=img.headers.get("content-type", "image/png").split(";")[0],
            cost=Cost(usd=float(body.get("cost_usd", 0.0))),
            meta={"provider": "higgsfield", "seed": seed},
        )
