"""Typed data-access helpers over the SQLite schema in db.py.

Plain functions (a thin repository) keep the dependency surface tiny while still
giving callers structured dict rows. JSON columns are (de)serialized here.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .db import session

_JSON_COLS = {
    "characters": {"palette", "style_tokens", "sheets", "edits", "consistency", "lore"},
    "voices": {"params"},
    "shots": {"characters"},
    "assets": {"meta"},
    "jobs": {"payload", "result"},
}


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}" if prefix else uuid.uuid4().hex[:12]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode(table: str, row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    for col in _JSON_COLS.get(table, set()):
        if col in d and isinstance(d[col], str):
            try:
                d[col] = json.loads(d[col])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def _encode(table: str, data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    for col in _JSON_COLS.get(table, set()):
        if col in out and not isinstance(out[col], str):
            out[col] = json.dumps(out[col])
    return out


# ---------- generic ----------

def insert(table: str, data: dict[str, Any]) -> dict[str, Any]:
    data = _encode(table, data)
    cols = ", ".join(data)
    ph = ", ".join("?" for _ in data)
    with session() as c:
        c.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph})", tuple(data.values()))
    return get(table, data["id"])


def get(table: str, row_id: str) -> dict[str, Any] | None:
    with session() as c:
        row = c.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    return _decode(table, row)


def update(table: str, row_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    if not changes:
        return get(table, row_id)
    changes = _encode(table, changes)
    if "updated_at" not in changes and _has_column(table, "updated_at"):
        changes["updated_at"] = now()
    sets = ", ".join(f"{k} = ?" for k in changes)
    with session() as c:
        c.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*changes.values(), row_id))
    return get(table, row_id)


def list_where(table: str, where: str = "", params: tuple = (), order: str = "") -> list[dict[str, Any]]:
    sql = f"SELECT * FROM {table}"
    if where:
        sql += f" WHERE {where}"
    if order:
        sql += f" ORDER BY {order}"
    with session() as c:
        rows = c.execute(sql, params).fetchall()
    return [_decode(table, r) for r in rows]  # type: ignore[misc]


def delete(table: str, row_id: str) -> None:
    with session() as c:
        c.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))


_COLUMN_CACHE: dict[str, set[str]] = {}


def _has_column(table: str, col: str) -> bool:
    if table not in _COLUMN_CACHE:
        with session() as c:
            rows = c.execute(f"PRAGMA table_info({table})").fetchall()
        _COLUMN_CACHE[table] = {r["name"] for r in rows}
    return col in _COLUMN_CACHE[table]


# ---------- typed constructors ----------

def create_project(name: str, *, style_preset: str = "3d_toddler_original",
                   language: str = "en", fps: int = 24, width: int = 1920,
                   height: int = 1080, safe_mode: bool = True) -> dict[str, Any]:
    ts = now()
    return insert("projects", {
        "id": new_id("prj_"), "name": name, "style_preset": style_preset,
        "language": language, "fps": fps, "width": width, "height": height,
        "safe_mode": 1 if safe_mode else 0, "created_at": ts, "updated_at": ts,
    })


def create_character(project_id: str, name: str, description: str, *,
                     style_preset: str = "3d_toddler_original",
                     palette: list[str] | None = None,
                     style_tokens: list[str] | None = None,
                     negative_prompt: str = "",
                     lore: dict | None = None) -> dict[str, Any]:
    ts = now()
    return insert("characters", {
        "id": new_id("chr_"), "project_id": project_id, "name": name,
        "description": description, "style_preset": style_preset,
        "palette": palette or [], "style_tokens": style_tokens or [],
        "negative_prompt": negative_prompt, "sheets": {}, "lore": lore or {},
        "ip_flagged": 0, "created_at": ts, "updated_at": ts,
    })


def create_shot(project_id: str, idx: int, text: str, *,
                characters: list[str] | None = None, camera: str = "static",
                background: str = "", duration_s: float = 4.0) -> dict[str, Any]:
    ts = now()
    return insert("shots", {
        "id": new_id("sht_"), "project_id": project_id, "idx": idx, "text": text,
        "characters": characters or [], "camera": camera, "background": background,
        "duration_s": duration_s, "status": "draft", "created_at": ts, "updated_at": ts,
    })


def create_asset(*, kind: str, path: str, project_id: str | None = None,
                 mime: str = "application/octet-stream", sha256: str | None = None,
                 provider: str | None = None, cost_usd: float = 0.0,
                 gpu_seconds: float = 0.0, meta: dict | None = None) -> dict[str, Any]:
    return insert("assets", {
        "id": new_id("ast_"), "project_id": project_id, "kind": kind, "path": path,
        "mime": mime, "sha256": sha256, "provider": provider, "cost_usd": cost_usd,
        "gpu_seconds": gpu_seconds, "meta": meta or {}, "created_at": now(),
    })


def create_embedding(*, space: str, dim: int, vector: bytes,
                     asset_id: str | None = None,
                     character_id: str | None = None) -> dict[str, Any]:
    row_id = new_id("emb_")
    with session() as c:
        c.execute(
            "INSERT INTO embeddings (id, space, dim, vector, asset_id, character_id, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (row_id, space, dim, vector, asset_id, character_id, now()),
        )
    return {"id": row_id, "space": space, "dim": dim, "asset_id": asset_id,
            "character_id": character_id}
