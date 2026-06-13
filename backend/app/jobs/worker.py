"""In-process async worker. Started on FastAPI startup, stopped on shutdown.

Claims queued jobs, runs the matching handler, retries on failure (up to max_attempts),
then marks failed with the error so the UI can offer a one-click fix. No full-pipeline
restart is ever required — each job is independent and resumable.
"""
from __future__ import annotations

import asyncio
import logging
import traceback

from .handlers import HANDLERS, JobContext
from . import queue

log = logging.getLogger("toonforge.worker")


class Worker:
    def __init__(self, poll_interval: float = 0.5) -> None:
        self.poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="toonforge-worker")
            log.info("worker started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
            self._task = None
            log.info("worker stopped")

    async def _run(self) -> None:
        while not self._stop.is_set():
            job = queue.claim_next()
            if job is None:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    pass
                continue
            await self._execute(job)

    async def _execute(self, job: dict) -> None:
        handler = HANDLERS.get(job["type"])
        if handler is None:
            queue.fail_or_retry(job["id"], f"no handler for job type '{job['type']}'")
            return
        ctx = JobContext(job["id"])
        try:
            result = await handler(job, ctx)
            queue.succeed(job["id"], result)
            log.info("job %s (%s) succeeded", job["id"], job["type"])
        except Exception as e:  # noqa: BLE001 — surface error, retry per policy
            err = f"{e.__class__.__name__}: {e}"
            outcome = queue.fail_or_retry(job["id"], err)
            log.warning("job %s (%s) %s: %s\n%s", job["id"], job["type"], outcome, err,
                        traceback.format_exc())


worker = Worker()
