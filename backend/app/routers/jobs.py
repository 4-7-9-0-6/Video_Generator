"""Job status, cancel, and live progress (SSE)."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .. import errors
from ..jobs import queue

router = APIRouter(prefix="/jobs", tags=["jobs"])

_TERMINAL = {"succeeded", "failed", "cancelled"}


def _enrich(job: dict) -> dict:
    """Attach a UI-friendly error message to failed jobs."""
    if job.get("status") == "failed" or job.get("error"):
        return {**job, "friendly_error": errors.humanize(job.get("error"))}
    return job


@router.get("")
def list_jobs(project_id: str | None = None) -> list[dict]:
    return [_enrich(j) for j in queue.list_jobs(project_id)]


@router.get("/{job_id}")
def get_job(job_id: str) -> dict:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return _enrich(job)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    job = queue.cancel(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@router.get("/{job_id}/stream")
async def stream_job(job_id: str) -> StreamingResponse:
    if queue.get(job_id) is None:
        raise HTTPException(404, "job not found")

    async def gen():
        last = None
        while True:
            job = queue.get(job_id)
            if job is None:
                break
            snapshot = (job["status"], round(job["progress"], 3), job["message"])
            if snapshot != last:
                last = snapshot
                payload = {"status": job["status"], "progress": job["progress"],
                           "message": job["message"], "result": job["result"], "error": job["error"]}
                if job["error"]:
                    payload["friendly_error"] = errors.humanize(job["error"])
                yield f"data: {json.dumps(payload)}\n\n"
            if job["status"] in _TERMINAL:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")
