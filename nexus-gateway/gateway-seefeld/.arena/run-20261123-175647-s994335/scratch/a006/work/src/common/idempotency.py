"""
Idempotency-Key middleware for the ingest API.

RFC-9110-compatible pattern: the client sends `Idempotency-Key: <opaque>`
on POST /api/ingest. We remember (key → response body + status) for 24h.
A retry with the same key returns the same recorded response — no
duplicate dispatch, no duplicate DLQ entry, no double-charging the LIS.

Backed by SQLite so it survives restarts. TTL 24h by default (configurable
via `idempotency_ttl_seconds` in gateway.yaml).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Any

_DB = Path("logs/idempotency.db")
_LOCK = Lock()
_TTL_DEFAULT = 24 * 3600


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(_DB)
    c.execute(
        "CREATE TABLE IF NOT EXISTS keys ("
        "  key      TEXT PRIMARY KEY,"
        "  body_sha TEXT NOT NULL,"
        "  status   INTEGER NOT NULL,"
        "  response TEXT NOT NULL,"
        "  created  REAL NOT NULL"
        ")"
    )
    return c


def _hash_body(body: bytes | str) -> str:
    if isinstance(body, str):
        body = body.encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def get(key: str, body: bytes | str) -> tuple[int, dict[str, Any]] | None:
    """Return the previously-recorded (status, response) for this key, or None."""
    if not key:
        return None
    body_sha = _hash_body(body)
    with _LOCK, _conn() as c:
        row = c.execute("SELECT body_sha, status, response FROM keys WHERE key = ?",
                        (key,)).fetchone()
        if not row:
            return None
        stored_sha, status, resp = row
        if stored_sha != body_sha:
            # Same key, different body — client bug. Refuse per RFC 9110.
            return status, {"error": "E5001",
                            "message": "idempotency key reused with different body"}
        try:
            return status, json.loads(resp)
        except json.JSONDecodeError:
            return status, {"raw": resp}


def store(key: str, body: bytes | str, status: int, response: dict[str, Any]) -> None:
    if not key:
        return
    body_sha = _hash_body(body)
    payload = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
    with _LOCK, _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO keys (key, body_sha, status, response, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, body_sha, status, payload, time.time()),
        )


def purge_expired(ttl_seconds: int = _TTL_DEFAULT) -> int:
    """Called by the retention background worker."""
    cutoff = time.time() - ttl_seconds
    with _LOCK, _conn() as c:
        cur = c.execute("DELETE FROM keys WHERE created < ?", (cutoff,))
        c.commit()
        return cur.rowcount
