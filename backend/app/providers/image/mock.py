"""Deterministic mock image provider — for OFFLINE TESTS ONLY (not a real generator).

Renders a reproducible image from `identity_key` (a stable per-character gradient) plus a
small per-seed marker. This lets the Character Foundry pipeline — drift checks, consistency
report, asset storage — be tested without a network/GPU. Select with PROVIDER_IMAGE=mock.
"""
from __future__ import annotations

import hashlib
import io

from ..base import Availability, Capability, Cost, GenResult, ImageProvider, ProviderInfo


class MockImageProvider(ImageProvider):
    info = ProviderInfo(
        name="mock", capability=Capability.IMAGE, kind="local",
        free=True, requires_gpu=False,
    )

    def availability(self) -> Availability:
        try:
            import numpy  # noqa: F401
            from PIL import Image  # noqa: F401
            return Availability(True, reason="deterministic test provider")
        except ImportError as e:
            return Availability(False, reason=str(e), install_hint="pip install Pillow numpy")

    async def generate(self, prompt: str, *, negative: str = "", width: int = 768,
                       height: int = 1024, seed: int | None = None,
                       reference_images: list[bytes] | None = None,
                       **kw: object) -> GenResult:
        import numpy as np
        from PIL import Image, ImageDraw

        identity = str(kw.get("identity_key") or prompt)
        h = hashlib.sha256(identity.encode()).digest()
        c1 = np.array([h[0], h[1], h[2]], dtype="float64")
        c2 = np.array([h[3], h[4], h[5]], dtype="float64")

        # vertical gradient dominated by identity -> high cross-view perceptual similarity
        t = np.linspace(0.0, 1.0, height).reshape(height, 1, 1)
        grad = (c1.reshape(1, 1, 3) * (1 - t) + c2.reshape(1, 1, 3) * t)
        arr = np.broadcast_to(grad, (height, width, 3)).astype("uint8").copy()
        img = Image.fromarray(arr, "RGB")

        # small per-seed marker so renders differ at pixel level (negligible low-freq impact)
        s = int(seed or 0)
        x = (s * 53) % max(1, width - 64)
        y = (s * 97) % max(1, height - 64)
        ImageDraw.Draw(img).rectangle([x, y, x + 64, y + 64],
                                      fill=(h[6], h[7], h[8]))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return GenResult(data=buf.getvalue(), mime="image/png", cost=Cost(),
                         meta={"provider": "mock", "seed": seed, "identity": identity})
