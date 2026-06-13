"""Shared helpers for the GPU-phase providers (flux/ltx/xtts/musicgen).

Every GPU provider lazy-imports torch and reports availability through here, so the app
boots and the CPU stack keeps working on a machine with no GPU / no torch — the provider
just reports itself unavailable with a clear hint. Cost is reported in GPU-seconds and $
(from GPU_USD_PER_HOUR) so the cost meter is meaningful on a rented GPU.
"""
from __future__ import annotations

from .providers.base import Availability, Cost

_GPU_HINT = ("Run on an NVIDIA GPU host and `pip install -r requirements-gpu.txt` "
            "(see docs/GPU_DEPLOY.md). This machine has no CUDA GPU.")


def torch_cuda() -> tuple[bool, str]:
    """(cuda_available, device_name_or_reason)."""
    try:
        import torch
    except ImportError:
        return False, "torch not installed"
    try:
        if not torch.cuda.is_available():
            return False, "no CUDA GPU detected"
        return True, torch.cuda.get_device_name(0)
    except Exception as e:  # noqa: BLE001 — a broken driver shouldn't crash the probe
        return False, f"CUDA check failed: {e}"


def require_gpu(*extra_imports: str) -> Availability:
    """For providers that are only practical on a GPU (flux/ltx). Fails without CUDA."""
    ok, msg = torch_cuda()
    if not ok:
        return Availability(False, reason=msg, install_hint=_GPU_HINT)
    for mod in extra_imports:
        try:
            __import__(mod)
        except ImportError:
            return Availability(False, reason=f"{mod} not installed",
                                install_hint="pip install -r requirements-gpu.txt")
    return Availability(True, reason=f"local GPU: {msg}")


def require_torch(*extra_imports: str) -> Availability:
    """For providers that run on CPU (free) and just go faster on a GPU (music/voice clone).
    Needs torch + the extra libs; CUDA is optional."""
    try:
        import torch
    except ImportError:
        return Availability(False, reason="torch not installed",
                            install_hint="pip install -r requirements-ml-cpu.txt (CPU, free) "
                                         "or -r requirements-gpu.txt (GPU)")
    for mod in extra_imports:
        try:
            __import__(mod)
        except ImportError:
            return Availability(False, reason=f"{mod} not installed",
                                install_hint="pip install -r requirements-ml-cpu.txt")
    if torch.cuda.is_available():
        return Availability(True, reason=f"local GPU: {torch.cuda.get_device_name(0)}")
    return Availability(True, reason="local CPU (free; slower than GPU)")


def torch_device() -> str:
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


def gpu_cost(seconds: float) -> Cost:
    from .config import settings
    rate = settings.gpu_usd_per_hour
    return Cost(gpu_seconds=round(seconds, 2), usd=round(seconds / 3600.0 * rate, 4))
