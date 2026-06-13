"""ToonForge FastAPI app. Boots the DB, starts the in-process job worker, mounts routers."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .db import init_db
from .jobs.worker import worker
from .routers import (assets, characters, export, generate, health, jobs, meta, projects,
                      scene, templates, thumbnails, voice)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    worker.start()
    try:
        yield
    finally:
        await worker.stop()


app = FastAPI(title="ToonForge Studio", version=__version__, lifespan=lifespan)

# Local single-user dev: allow the Next.js frontend (localhost) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"], allow_headers=["*"],
)

for r in (health.router, meta.router, templates.router, projects.router,
          characters.router, jobs.router, assets.router, voice.router,
          scene.router, export.router, thumbnails.router, generate.router):
    app.include_router(r)


@app.get("/", tags=["system"])
def root() -> dict:
    return {"app": "ToonForge Studio", "version": __version__, "docs": "/docs"}
