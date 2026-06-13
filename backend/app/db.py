"""SQLite engine + explicit schema. Stdlib only — guaranteed to run on Python 3.14.

This is the §8 "database schema" deliverable. It maps 1:1 onto Postgres later;
`embeddings.vector` (BLOB) becomes a pgvector column.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator

from .config import settings

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    style_preset  TEXT NOT NULL DEFAULT '3d_toddler_original',
    language      TEXT NOT NULL DEFAULT 'en',
    fps           INTEGER NOT NULL DEFAULT 24,
    width         INTEGER NOT NULL DEFAULT 1920,
    height        INTEGER NOT NULL DEFAULT 1080,
    safe_mode     INTEGER NOT NULL DEFAULT 1,          -- children's-content safe mode ON
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS characters (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,                      -- user prompt
    style_preset    TEXT NOT NULL DEFAULT '3d_toddler_original',
    palette         TEXT NOT NULL DEFAULT '[]',         -- JSON list of hex colors
    style_tokens    TEXT NOT NULL DEFAULT '[]',         -- JSON list
    negative_prompt TEXT NOT NULL DEFAULT '',
    embedding_id    TEXT,                               -- identity embedding (FK to embeddings)
    sheets          TEXT NOT NULL DEFAULT '{}',         -- JSON {turnaround:[asset_id], expressions:{...}, poses:{...}}
    edits           TEXT NOT NULL DEFAULT '[]',         -- JSON list of applied instruction edits
    consistency     TEXT NOT NULL DEFAULT '{}',         -- JSON drift report (per-view scores vs identity)
    lore            TEXT NOT NULL DEFAULT '{}',         -- JSON {personality, backstory, abilities[]}
    ip_flagged      INTEGER NOT NULL DEFAULT 0,         -- copyright guard result
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS voices (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    provider      TEXT NOT NULL,
    language      TEXT NOT NULL DEFAULT 'en',
    age           TEXT NOT NULL DEFAULT 'child',        -- child|teen|adult
    is_clone      INTEGER NOT NULL DEFAULT 0,
    consent_ref   TEXT,                                 -- consent record id (cloning requires this)
    params        TEXT NOT NULL DEFAULT '{}',           -- JSON: pitch, speed, emotion, vibrato...
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shots (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    idx           INTEGER NOT NULL,                     -- order in episode
    text          TEXT NOT NULL DEFAULT '',             -- script line / lyric
    characters    TEXT NOT NULL DEFAULT '[]',           -- JSON list of character ids
    camera        TEXT NOT NULL DEFAULT 'static',       -- motion preset name
    background    TEXT NOT NULL DEFAULT '',
    duration_s    REAL NOT NULL DEFAULT 4.0,
    keyframe_id   TEXT,                                 -- asset id (image)
    clip_id       TEXT,                                 -- asset id (video)
    prompt_hash   TEXT,                                 -- render cache key
    status        TEXT NOT NULL DEFAULT 'draft',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id            TEXT PRIMARY KEY,
    project_id    TEXT REFERENCES projects(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,                        -- image|video|audio|subtitle|other
    path          TEXT NOT NULL,                        -- relative to data/assets
    mime          TEXT NOT NULL DEFAULT 'application/octet-stream',
    sha256        TEXT,
    provider      TEXT,
    cost_usd      REAL NOT NULL DEFAULT 0,
    gpu_seconds   REAL NOT NULL DEFAULT 0,
    meta          TEXT NOT NULL DEFAULT '{}',           -- JSON
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    project_id    TEXT REFERENCES projects(id) ON DELETE CASCADE,
    type          TEXT NOT NULL,                        -- character_turnaround | shot_keyframe | ...
    status        TEXT NOT NULL DEFAULT 'queued',       -- queued|running|succeeded|failed|cancelled
    progress      REAL NOT NULL DEFAULT 0,              -- 0..1
    message       TEXT NOT NULL DEFAULT '',
    payload       TEXT NOT NULL DEFAULT '{}',           -- JSON input
    result        TEXT NOT NULL DEFAULT '{}',           -- JSON output
    error         TEXT NOT NULL DEFAULT '',
    attempts      INTEGER NOT NULL DEFAULT 0,
    max_attempts  INTEGER NOT NULL DEFAULT 3,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS embeddings (
    id            TEXT PRIMARY KEY,
    space         TEXT NOT NULL,                        -- phash | clip | arcface
    dim           INTEGER NOT NULL,
    vector        BLOB NOT NULL,                        -- numpy bytes (pgvector replacement)
    asset_id      TEXT REFERENCES assets(id) ON DELETE CASCADE,
    character_id  TEXT REFERENCES characters(id) ON DELETE CASCADE,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status   ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_shots_project ON shots(project_id, idx);
CREATE INDEX IF NOT EXISTS idx_assets_proj   ON assets(project_id);
CREATE INDEX IF NOT EXISTS idx_emb_char      ON embeddings(character_id);
"""


def connect() -> sqlite3.Connection:
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# Idempotent column additions for DBs created before a column existed.
_MIGRATIONS: list[tuple[str, str, str]] = [
    ("characters", "edits", "TEXT NOT NULL DEFAULT '[]'"),
    ("characters", "consistency", "TEXT NOT NULL DEFAULT '{}'"),
    ("characters", "lore", "TEXT NOT NULL DEFAULT '{}'"),
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for table, column, ddl in _MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    settings.ensure_dirs()
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _apply_migrations(conn)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
