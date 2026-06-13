"""CLIP IP-similarity guard — registration + graceful no-op on the no-torch (pHash) default.
The real CLIP scoring needs torch (cpu-ml/gpu image), so it's verified there, not in CI."""
from __future__ import annotations

import io

from PIL import Image

from app import ip_guard
from app.providers import registry
from app.providers.base import Capability
from app.providers.consistency.phash import PHashConsistencyProvider


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (120, 80, 200)).save(buf, "PNG")
    return buf.getvalue()


def test_clip_provider_registered():
    assert "clip" in registry._FACTORIES[Capability.CONSISTENCY.value]
    p = registry._FACTORIES[Capability.CONSISTENCY.value]["clip"]()
    assert p.info.name == "clip" and p.info.requires_gpu is False


def test_clip_unavailable_without_torch_but_no_crash():
    p = registry._FACTORIES[Capability.CONSISTENCY.value]["clip"]()
    av = p.availability()                       # this box has no torch -> unavailable, gracefully
    assert av.available is False and av.install_hint


def test_ip_guard_is_noop_for_phash():
    # the default pHash provider can't do zero-shot CLIP -> guard reports unavailable, never flags
    res = ip_guard.check_image(_png(), PHashConsistencyProvider())
    assert res["available"] is False and res["flagged"] is False


def test_ip_guard_supported_detects_classify():
    class FakeClip:
        def classify(self, image, labels):
            # pretend the image looks strongly like the first label (a protected IP)
            n = len(labels)
            return [0.9] + [0.1 / (n - 1)] * (n - 1)

    res = ip_guard.check_image(_png(), FakeClip(), threshold=0.5)
    assert res["available"] is True and res["flagged"] is True
    assert res["top_ip"] == ip_guard.KNOWN_IPS[0][0] and res["score"] > 0.5


def test_ip_guard_passes_original_design():
    class OriginalClip:
        def classify(self, image, labels):
            # all the mass on the LAST labels (the "original character" anchors)
            n = len(labels)
            probs = [0.0] * n
            probs[-1] = 1.0
            return probs

    res = ip_guard.check_image(_png(), OriginalClip(), threshold=0.5)
    assert res["available"] is True and res["flagged"] is False
