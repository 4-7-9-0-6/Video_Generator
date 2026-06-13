"""ACE-Step (singing) + SadTalker (lip-sync) GPU providers — registration + graceful no-GPU.
The real models run only on a GPU (see docs/FREE_GPU.md); here we verify they register and
report unavailable cleanly on this CPU box without crashing the app."""
from __future__ import annotations

from app.providers import registry
from app.providers.base import Capability


def test_acestep_registered_and_gpu_only():
    fac = registry._FACTORIES[Capability.SVS.value]
    assert "acestep_local" in fac
    p = fac["acestep_local"]()
    assert p.info.requires_gpu is True
    av = p.availability()
    assert av.available is False and av.install_hint        # no GPU here -> graceful


def test_sadtalker_registered_and_gpu_only():
    fac = registry._FACTORIES[Capability.LIPSYNC.value]
    assert "sadtalker_local" in fac
    p = fac["sadtalker_local"]()
    assert p.info.requires_gpu is True
    av = p.availability()
    assert av.available is False and av.install_hint


def test_acestep_tags_builder():
    from app.providers.svs.acestep_local import ACEStepSVSProvider
    tags = ACEStepSVSProvider._tags("C", 100, mood="lullaby")
    assert "100 BPM" in tags and "C key" in tags and "lullaby" in tags


def test_probe_includes_new_gpu_providers():
    rows = registry.probe_all()
    names = {(r["capability"], r["provider"]) for r in rows}
    assert ("svs", "acestep_local") in names
    assert ("lipsync", "sadtalker_local") in names
