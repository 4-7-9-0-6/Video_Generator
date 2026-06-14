"""Free-tier usage guard — track Cloudflare image + Kaggle GPU consumption so the user stays
inside the free limits.

Derived from existing rows (no extra tracking table):
- Cloudflare images today  = local image assets whose provider starts with "cloudflare", since
  local midnight UTC (proxy for the ~10k-neuron/day free Workers AI tier).
- Kaggle renders this week  = `gpu_video` jobs in the last 7 days; each ≈ KAGGLE_MINUTES_PER_RENDER
  minutes of the ~30 GPU-hours/week free quota.

Best-effort (Cloudflare calls made *inside* a Kaggle kernel aren't counted locally), but enough to
warn before you exhaust a free tier. All limits are env-configurable.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from . import models
from .config import settings


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def cloudflare_images_today() -> int:
    start = _utc_now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    return len(models.list_where("assets", "provider LIKE 'cloudflare%' AND created_at >= ?", (start,)))


def kaggle_renders_this_week() -> int:
    since = (_utc_now() - timedelta(days=7)).isoformat()
    return len(models.list_where("jobs", "type = 'gpu_video' AND created_at >= ?", (since,)))


def summary() -> dict[str, Any]:
    cf_used = cloudflare_images_today()
    cf_budget = max(1, settings.cloudflare_daily_image_budget)
    k_used = kaggle_renders_this_week()
    k_per = max(1, settings.kaggle_minutes_per_render)
    k_budget = max(1, settings.kaggle_weekly_gpu_minutes)
    k_used_min = k_used * k_per
    k_left_min = max(0, k_budget - k_used_min)
    return {
        "cloudflare": {
            "images_today": cf_used,
            "daily_budget": cf_budget,
            "remaining": max(0, cf_budget - cf_used),
            "near_limit": cf_used >= cf_budget * 0.8,
            "over_limit": cf_used >= cf_budget,
        },
        "kaggle": {
            "renders_this_week": k_used,
            "minutes_used": k_used_min,
            "weekly_budget_minutes": k_budget,
            "remaining_minutes": k_left_min,
            "est_renders_left": k_left_min // k_per,
            "minutes_per_render": k_per,
            "near_limit": k_used_min >= k_budget * 0.8,
            "over_limit": k_used_min >= k_budget,
        },
    }


def kaggle_warning() -> str:
    """A short warning if a new GPU render would push the user near/over the weekly free quota."""
    k = summary()["kaggle"]
    if k["over_limit"]:
        return (f"You've likely used your ~{k['weekly_budget_minutes'] // 60}h free Kaggle GPU "
                f"this week ({k['renders_this_week']} renders). This may queue or fail until it resets.")
    if k["near_limit"]:
        return (f"Approaching your weekly free Kaggle GPU limit (~{k['est_renders_left']} renders left).")
    return ""
