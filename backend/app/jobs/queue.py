"""SQLite-backed job queue (no Redis/Celery — single-user/local).

Jobs are durable rows; the in-process worker (worker.py) claims and runs them. Safe for
one worker. To scale out later, replace claim_next() with SELECT ... FOR UPDATE SKIP LOCKED
on Postgres — callers don't change.
"""
from __future__ import annotations

from typing import Any

from .. import models
from ..db import session


def enqueue(job_type: str, payload: dict[str, Any], *,
            project_id: str | None = None, max_attempts: int = 3) -> dict[str, Any]:
    ts = models.now()
    return models.insert("jobs", {
        "id": models.new_id("job_"), "project_id": project_id, "type": job_type,
        "status": "queued", "progress": 0.0, "message": "queued",
        "payload": payload, "result": {}, "error": "", "attempts": 0,
        "max_attempts": max_attempts, "created_at": ts, "updated_at": ts,
    })


def claim_next() -> dict[str, Any] | None:
    """Atomically move the oldest queued job to running and return it."""
    with session() as c:
        row = c.execute(
            "SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        job_id = row["id"]
        c.execute(
            "UPDATE jobs SET status='running', attempts = attempts + 1,"
            " message='running', updated_at=? WHERE id=? AND status='queued'",
            (models.now(), job_id),
        )
        changed = c.total_changes
    if changed == 0:
        return None
    return models.get("jobs", job_id)


def set_progress(job_id: str, progress: float, message: str = "") -> None:
    models.update("jobs", job_id, {"progress": max(0.0, min(1.0, progress)),
                                   "message": message})


def succeed(job_id: str, result: dict[str, Any]) -> None:
    models.update("jobs", job_id, {"status": "succeeded", "progress": 1.0,
                                   "result": result, "message": "done", "error": ""})


def fail_or_retry(job_id: str, error: str) -> str:
    """Returns 'queued' if it will retry, else 'failed'."""
    job = models.get("jobs", job_id)
    assert job is not None
    if job["attempts"] < job["max_attempts"]:
        models.update("jobs", job_id, {"status": "queued", "message": "retrying",
                                       "error": error})
        return "queued"
    models.update("jobs", job_id, {"status": "failed", "error": error,
                                   "message": "failed"})
    return "failed"


def cancel(job_id: str) -> dict[str, Any] | None:
    job = models.get("jobs", job_id)
    if job and job["status"] in ("queued", "running"):
        return models.update("jobs", job_id, {"status": "cancelled", "message": "cancelled"})
    return job


def get(job_id: str) -> dict[str, Any] | None:
    return models.get("jobs", job_id)


def list_jobs(project_id: str | None = None) -> list[dict[str, Any]]:
    if project_id:
        return models.list_where("jobs", "project_id = ?", (project_id,), "created_at DESC")
    return models.list_where("jobs", order="created_at DESC")
