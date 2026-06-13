"""Cloudflare Workers AI image provider — FREE modern Flux, no GPU, no credit card.

The genuinely-free path to current-quality images: Cloudflare's free tier gives ~10,000
neurons/day (dozens of Flux images) running FLUX.1 [schnell] in their cloud. Key-gated and
free within the daily budget. Get a token: https://dash.cloudflare.com → Workers AI → API token
(needs the account id too). Then in backend/.env:
    CLOUDFLARE_ACCOUNT_ID=...
    CLOUDFLARE_API_TOKEN=...
    PROVIDER_IMAGE=cloudflare
"""
from __future__ import annotations

import base64
import io

import httpx

from ...config import settings
from ..base import Availability, Capability, Cost, GenResult, ImageProvider, ProviderInfo


class CloudflareImageProvider(ImageProvider):
    info = ProviderInfo(
        name="cloudflare", capability=Capability.IMAGE, kind="cloud",
        free=True, requires_gpu=False,
    )

    def availability(self) -> Availability:
        if not settings.cloudflare_account_id or not settings.cloudflare_api_token:
            return Availability(
                False, reason="CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN not set",
                install_hint="Free, no card: dash.cloudflare.com → Workers AI → create an API "
                             "token, then set CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN in .env",
            )
        return Availability(True, reason=f"free cloud Flux ({settings.cloudflare_image_model}, "
                                         "~10k neurons/day)")

    def estimate_cost(self, **kwargs: object) -> Cost:
        return Cost(gpu_seconds=0.0, usd=0.0)   # free within the daily neuron budget

    async def generate(self, prompt: str, *, negative: str = "", width: int = 1024,
                       height: int = 1024, seed: int | None = None,
                       reference_images: list[bytes] | None = None,
                       **kw: object) -> GenResult:
        model = str(kw.get("model") or settings.cloudflare_image_model)
        url = (f"https://api.cloudflare.com/client/v4/accounts/"
               f"{settings.cloudflare_account_id}/ai/run/{model}")
        body: dict = {"prompt": prompt, "steps": int(kw.get("steps", settings.cloudflare_steps))}
        if seed is not None:
            body["seed"] = int(seed)
        headers = {"Authorization": f"Bearer {settings.cloudflare_api_token}"}

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
                data = resp.content                          # some models return raw bytes
            else:
                resp.raise_for_status()
                payload = resp.json()
                if not payload.get("success", True):
                    raise RuntimeError(f"Cloudflare AI error: {payload.get('errors')}")
                b64 = payload["result"]["image"]             # flux-schnell -> base64 jpeg
                data = base64.b64decode(b64)

        data = self._fit(data, width, height)
        return GenResult(data=data, mime="image/png", cost=Cost(),
                         meta={"provider": "cloudflare", "model": model, "seed": seed,
                               "out_size": [width, height]})

    @staticmethod
    def _fit(img_bytes: bytes, width: int, height: int) -> bytes:
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        if img.size != (width, height):
            img = img.resize((width, height), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
