"""CLIP consistency + IP-similarity guard (spec §A.7, §6) — real semantic identity.

Upgrades the pHash baseline: `similarity()` is now a true CLIP image-embedding cosine
(semantic "is this the same character", not just structural framing), and `classify()`
gives zero-shot image↔text probabilities used by app/ip_guard.py to catch outputs that
*look like* a protected IP — no copyrighted reference images needed (CLIP aligns image+text).

Runs locally and free on CPU (slower) via transformers; auto-uses a GPU if present. Select
with PROVIDER_CONSISTENCY=clip (needs `requirements-ml-cpu.txt`). pHash stays the no-torch default.
"""
from __future__ import annotations

import io

from ... import gpu_util
from ...config import settings
from ..base import Availability, Capability, ConsistencyProvider, ProviderInfo
from .phash import PHashConsistencyProvider

_model = None
_proc = None


class CLIPConsistencyProvider(ConsistencyProvider):
    info = ProviderInfo(
        name="clip", capability=Capability.CONSISTENCY, kind="local",
        free=True, requires_gpu=False,   # CPU-capable (slow); GPU if present
    )

    def __init__(self) -> None:
        self._palette = PHashConsistencyProvider()   # reuse the pose-invariant color signal

    def availability(self) -> Availability:
        av = gpu_util.require_torch("transformers")
        if not av.available:
            return av
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            return Availability(False, reason="Pillow missing", install_hint="pip install Pillow")
        return Availability(True, reason=av.reason + f" — CLIP ({settings.clip_model})")

    def _load(self):
        global _model, _proc
        if _model is None:
            from transformers import CLIPModel, CLIPProcessor
            _model = CLIPModel.from_pretrained(settings.clip_model).to(gpu_util.torch_device())
            _model.eval()
            _proc = CLIPProcessor.from_pretrained(settings.clip_model)
        return _model, _proc

    @staticmethod
    def _coerce(out):
        """get_image_features returns a tensor on some transformers versions and a model-output
        object on others — pull the embedding tensor out either way."""
        import torch
        if isinstance(out, torch.Tensor):
            return out
        for attr in ("image_embeds", "text_embeds", "pooler_output"):
            v = getattr(out, attr, None)
            if v is not None:
                return v
        last = getattr(out, "last_hidden_state", None)
        if last is not None:
            return last.mean(dim=1)
        raise TypeError(f"unexpected CLIP features type: {type(out)}")

    def _image_features(self, image: bytes):
        import torch
        from PIL import Image
        model, proc = self._load()
        img = Image.open(io.BytesIO(image)).convert("RGB")
        inputs = proc(images=img, return_tensors="pt").to(gpu_util.torch_device())
        with torch.no_grad():
            feat = self._coerce(model.get_image_features(**inputs))
        return feat / feat.norm(dim=-1, keepdim=True)

    def embed(self, image: bytes) -> tuple[str, int, bytes]:
        feat = self._image_features(image)[0].cpu().numpy().astype("float32")
        return ("clip", int(feat.size), feat.tobytes())

    def similarity(self, a: bytes, b: bytes) -> float:
        import torch
        fa, fb = self._image_features(a), self._image_features(b)
        return float(torch.clamp((fa * fb).sum(), -1.0, 1.0).item())

    def palette_similarity(self, a: bytes, b: bytes) -> float:
        return self._palette.palette_similarity(a, b)

    def classify(self, image: bytes, labels: list[str]) -> list[float]:
        """Zero-shot CLIP probabilities of the image matching each text label (softmax).
        Uses the canonical CLIP forward (logits_per_image) — robust across transformers versions."""
        import torch
        from PIL import Image
        model, proc = self._load()
        img = Image.open(io.BytesIO(image)).convert("RGB")
        inputs = proc(text=labels, images=img, return_tensors="pt",
                      padding=True).to(gpu_util.torch_device())
        with torch.no_grad():
            out = model(**inputs)
        return out.logits_per_image.softmax(dim=-1)[0].cpu().tolist()
