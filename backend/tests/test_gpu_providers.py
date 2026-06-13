"""GPU-phase providers — verify they register and degrade GRACEFULLY on a no-GPU box.

These don't run a GPU model here; the point is that importing/instantiating them and probing
availability never crashes the CPU app, and that they report a clear 'unavailable' + hint.
"""
from __future__ import annotations

import pytest

from app import gpu_util
from app.providers import registry
from app.providers.base import Capability


def test_gpu_util_reports_no_gpu_with_hint():
    av = gpu_util.require_gpu()
    assert av.available is False              # this box has no CUDA GPU
    assert av.install_hint                    # tells the user how to enable it


def test_gpu_cost_uses_rate(monkeypatch):
    import types
    # Settings is frozen; swap the module binding gpu_cost() reads at call time
    monkeypatch.setattr("app.config.settings", types.SimpleNamespace(gpu_usd_per_hour=0.40))
    cost = gpu_util.gpu_cost(3600.0)
    assert cost.gpu_seconds == 3600.0 and cost.usd == 0.40
    assert gpu_util.gpu_cost(1800.0).usd == 0.20


# flux/ltx need a real GPU (CPU is impractical); music/voice run on CPU too (free, slower)
GPU_ONLY = [(Capability.IMAGE, "flux_local"), (Capability.VIDEO, "ltx_local")]
CPU_CAPABLE = [(Capability.TTS, "xtts_local"), (Capability.MUSIC, "musicgen_local")]
ALL_LOCAL = GPU_ONLY + CPU_CAPABLE


@pytest.mark.parametrize("cap,name", ALL_LOCAL)
def test_provider_registered_and_imports(cap, name):
    factory = registry._FACTORIES[cap.value][name]
    provider = factory()                      # importing + instantiating must not need a GPU
    assert provider.info.name == name


def test_gpu_only_providers_flag_requires_gpu():
    for cap, name in GPU_ONLY:
        assert registry._FACTORIES[cap.value][name]().info.requires_gpu is True
    for cap, name in CPU_CAPABLE:
        assert registry._FACTORIES[cap.value][name]().info.requires_gpu is False


@pytest.mark.parametrize("cap,name", ALL_LOCAL)
def test_availability_is_graceful_without_torch(cap, name):
    # this box has neither a GPU nor torch installed -> unavailable, with a hint, no crash
    provider = registry._FACTORIES[cap.value][name]()
    av = provider.availability()
    assert av.available is False
    assert av.reason and av.install_hint


def test_probe_all_includes_gpu_providers_without_crashing():
    rows = registry.probe_all()
    names = {(r["capability"], r["provider"]) for r in rows}
    for cap, name in ALL_LOCAL:
        assert (cap.value, name) in names
    # none of them should be 'selected' on the default CPU config
    assert not any(r["selected"] and r["provider"].endswith("_local")
                   for r in rows)


def test_video_disabled_by_default_keeps_cpu_compose_path():
    # PROVIDER_VIDEO is empty on the CPU box -> compose uses Ken Burns, not a GPU clip
    assert registry.get_provider(Capability.VIDEO, required=False) is None
