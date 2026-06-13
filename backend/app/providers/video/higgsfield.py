"""Higgsfield image->video provider — optional cloud animation (spec §C.2).

Disabled by default (no API key). Real async HTTP client with job polling when
HIGGSFIELD_API_KEY is set. Endpoint paths configurable per plan.
"""
from __future__ import annotations

import asyncio

import httpx

from ...config import settings
from ..base import (Availability, Capability, Cost, GenResult, ProviderInfo, VideoProvider)


class HiggsfieldVideoProvider(VideoProvider):
    info = ProviderInfo(
        name="higgsfield", capability=Capability.VIDEO, kind="cloud",
        free=False, requires_gpu=False,
    )

    def availability(self) -> Availability:
        if not settings.higgsfield_api_key:
            return Availability(
                False, reason="HIGGSFIELD_API_KEY not set",
                install_hint="Add HIGGSFIELD_API_KEY to backend/.env to enable image->video.",
            )
        return Availability(True)

    async def animate(self, image: bytes, *, motion: str = "static",
                      duration_s: float = 4.0, fps: int = 24,
                      prompt: str = "", **kw: object) -> GenResult:
        headers = {"Authorization": f"Bearer {settings.higgsfield_api_key}"}
        base = settings.higgsfield_api_base.rstrip("/")
        async with httpx.AsyncClient(timeout=300) as client:
            start = await client.post(
                f"{base}/v1/videos/generate",
                files={"image": ("keyframe.png", image, "image/png")},
                data={"motion": motion, "duration": str(duration_s),
                      "fps": str(fps), "prompt": prompt},
                headers=headers,
            )
            start.raise_for_status()
            job = start.json()
            job_id = job["id"]
            video_url = None
            for _ in range(150):  # up to ~5 min
                st = await client.get(f"{base}/v1/jobs/{job_id}", headers=headers)
                st.raise_for_status()
                body = st.json()
                if body.get("status") == "completed":
                    video_url = body["output"]["url"]
                    break
                if body.get("status") == "failed":
                    raise RuntimeError(f"Higgsfield job failed: {body.get('error')}")
                await asyncio.sleep(2)
            if not video_url:
                raise TimeoutError("Higgsfield video job did not complete in time.")
            vid = await client.get(video_url, headers=headers)
            vid.raise_for_status()
        return GenResult(
            data=vid.content, mime="video/mp4",
            cost=Cost(usd=float(job.get("cost_usd", 0.0))),
            meta={"provider": "higgsfield", "motion": motion},
        )
