"""GPU compatibility shim for the free-tier cards (T4/P100, CUDA compute capability < 8.0).

These cards lack a usable half-precision convolution kernel for some shapes, so ACE-Step's and
LTX-Video's VAE/vocoder decodes crash with "GET was unable to find an engine to execute this
computation" (cuDNN has no bf16 engine, and the native bf16 conv path is missing too).

Importing this module wraps ``torch.nn.functional.conv2d`` so half-precision (fp16/bf16) convs on
CUDA run in fp32 — which always has a kernel — then casts the result back. The convs affected are
small and run once per clip, so the cost is negligible; the big diffusion transformers are
attention-based and untouched. No-op on Ampere+ GPUs, on CPU, or if torch is absent, and safe to
import more than once.

Both ``scripts/gpu_render.py`` and ``scripts/_sing_once.py`` import this at startup so the fix is
active in every process that touches the GPU.
"""
from __future__ import annotations


def apply() -> None:
    try:
        import torch
        import torch.nn.functional as F
    except Exception:  # noqa: BLE001 — no torch (CPU box): nothing to patch
        return
    try:
        if not (torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] < 8):
            return
    except Exception:  # noqa: BLE001 — broken driver during the capability probe
        return
    if getattr(F.conv2d, "_tf_fp32_wrapped", False):
        return  # already applied
    torch.backends.cudnn.enabled = False
    _orig = F.conv2d

    def _conv2d_fp32(inp, weight, bias=None, *a, **k):
        if inp.is_cuda and inp.dtype in (torch.float16, torch.bfloat16):
            b = bias.float() if bias is not None else None
            return _orig(inp.float(), weight.float(), b, *a, **k).to(inp.dtype)
        return _orig(inp, weight, bias, *a, **k)

    _conv2d_fp32._tf_fp32_wrapped = True
    F.conv2d = _conv2d_fp32


apply()
