"""Perceptual-hash consistency / IP-similarity baseline — real, CPU-only.

Character drift (spec §6) and the copyright guard (spec §A.7) both need an image
similarity score with no GPU. This is a self-contained DCT perceptual hash (Pillow +
numpy only — no scipy/imagehash, so it installs cleanly on Python 3.14): identical art
-> 1.0, unrelated art -> ~0.5. Swap to CLIP/ArcFace embeddings behind this same
interface when a GPU is available.
"""
from __future__ import annotations

import io
from functools import lru_cache

from ..base import Availability, Capability, ConsistencyProvider, ProviderInfo

_IMG_SIZE = 32      # downscale target before DCT
_HASH_SIZE = 8      # low-frequency block -> 64-bit hash


@lru_cache(maxsize=1)
def _dct_matrix(n: int):
    import numpy as np
    k = np.arange(n).reshape(-1, 1)
    x = np.arange(n).reshape(1, -1)
    m = np.cos(np.pi * (2 * x + 1) * k / (2 * n))
    m[0] *= 1.0 / np.sqrt(2)
    return (m * np.sqrt(2.0 / n)).astype("float64")


class PHashConsistencyProvider(ConsistencyProvider):
    info = ProviderInfo(
        name="phash", capability=Capability.CONSISTENCY, kind="local",
        free=True, requires_gpu=False,
    )

    def availability(self) -> Availability:
        try:
            import numpy  # noqa: F401
            from PIL import Image  # noqa: F401
            return Availability(True)
        except ImportError as e:
            return Availability(False, reason=str(e), install_hint="pip install Pillow numpy")

    def _bits(self, image: bytes):
        import numpy as np
        from PIL import Image
        img = (Image.open(io.BytesIO(image)).convert("L")
               .resize((_IMG_SIZE, _IMG_SIZE), Image.Resampling.LANCZOS))
        arr = np.asarray(img, dtype="float64")
        d = _dct_matrix(_IMG_SIZE)
        dct = d @ arr @ d.T
        block = dct[:_HASH_SIZE, :_HASH_SIZE]
        med = np.median(block[1:, 1:])      # exclude DC term from the threshold
        return (block > med).flatten()

    def embed(self, image: bytes) -> tuple[str, int, bytes]:
        bits = self._bits(image).astype("uint8")
        return ("phash", int(bits.size), bits.tobytes())

    def similarity(self, a: bytes, b: bytes) -> float:
        import numpy as np
        ba, bb = self._bits(a), self._bits(b)
        hamming = int(np.count_nonzero(ba != bb))
        return max(0.0, 1.0 - hamming / ba.size)

    def _hist(self, image: bytes):
        import numpy as np
        from PIL import Image
        img = (Image.open(io.BytesIO(image)).convert("RGB")
               .resize((64, 64), Image.Resampling.LANCZOS))
        arr = np.asarray(img, dtype="int64").reshape(-1, 3)
        q = arr // 64                                   # 4 bins/channel -> 64-bin histogram
        idx = q[:, 0] * 16 + q[:, 1] * 4 + q[:, 2]
        hist = np.bincount(idx, minlength=64).astype("float64")
        n = np.linalg.norm(hist)
        return hist / n if n else hist

    def palette_similarity(self, a: bytes, b: bytes) -> float:
        import numpy as np
        ha, hb = self._hist(a), self._hist(b)
        return float(np.clip(np.dot(ha, hb), 0.0, 1.0))
