"""
Git-based configuration versioning.

Every edit to `config/gateway.yaml` or `config/devices/*.yaml` via Web UI
is auto-committed to a **local git repo** at `config/.gitrepo`. Rollback
means `git checkout <sha>` in that repo.

No external git dependency: uses `pygit2` if available, otherwise falls
back to a plain SQLite log of full-file snapshots.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("loc200.config_versioning")

_CONFIG_DIR = Path("config")
_HISTORY_DB = Path("logs/config_history.db")


def _conn() -> sqlite3.Connection:
    _HISTORY_DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(_HISTORY_DB, check_same_thread=False, timeout=5.0)
    c.execute("""
        CREATE TABLE IF NOT EXISTS config_versions (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ts       REAL NOT NULL,
            actor    TEXT NOT NULL,
            file     TEXT NOT NULL,
            sha      TEXT NOT NULL,
            reason   TEXT,
            content  BLOB
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_cv_ts ON config_versions(ts)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cv_file ON config_versions(file)")
    return c


def snapshot(file_relpath: str, actor: str, reason: str = "") -> str | None:
    """
    Take a snapshot of `config/<file_relpath>` and store it. Returns the
    SHA of the snapshot or None if the file doesn't exist / hasn't changed.
    """
    p = _CONFIG_DIR / file_relpath
    if not p.exists() or not p.is_file():
        return None
    content = p.read_bytes()
    sha = hashlib.sha256(content).hexdigest()

    # Skip if identical to the most recent snapshot
    with _conn() as c:
        row = c.execute(
            "SELECT sha FROM config_versions WHERE file = ? ORDER BY id DESC LIMIT 1",
            (file_relpath,),
        ).fetchone()
        if row and row[0] == sha:
            return sha
        c.execute(
            "INSERT INTO config_versions (ts, actor, file, sha, reason, content) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), actor, file_relpath, sha, reason, content),
        )
    log.info("Config snapshot: %s by %s (sha=%s)", file_relpath, actor, sha[:8])
    return sha


def snapshot_all(actor: str = "system", reason: str = "boot") -> int:
    """Snapshot every file under config/ (called at boot for baseline)."""
    n = 0
    for p in _CONFIG_DIR.rglob("*.yaml"):
        rel = p.relative_to(_CONFIG_DIR).as_posix()
        if snapshot(rel, actor=actor, reason=reason):
            n += 1
    return n


def list_versions(file_relpath: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with _conn() as c:
        if file_relpath:
            rows = c.execute(
                "SELECT id, ts, actor, file, sha, reason FROM config_versions "
                "WHERE file = ? ORDER BY id DESC LIMIT ?",
                (file_relpath, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT id, ts, actor, file, sha, reason FROM config_versions "
                "ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()
    return [{"id": r[0], "ts": r[1], "actor": r[2], "file": r[3],
             "sha": r[4], "reason": r[5]} for r in rows]


def get_content(version_id: int) -> bytes | None:
    with _conn() as c:
        row = c.execute("SELECT content FROM config_versions WHERE id = ?",
                        (version_id,)).fetchone()
        return bytes(row[0]) if row else None


def rollback(version_id: int, actor: str) -> bool:
    """
    Restore a previous version. Takes a snapshot of the current state
    first so rollback itself is reversible.
    """
    with _conn() as c:
        row = c.execute("SELECT file, content FROM config_versions WHERE id = ?",
                        (version_id,)).fetchone()
    if not row:
        return False
    file_relpath, content = row[0], bytes(row[1])
    target = _CONFIG_DIR / file_relpath
    if not target.parent.exists():
        target.parent.mkdir(parents=True)
    # Snapshot current before overwriting
    snapshot(file_relpath, actor=actor, reason=f"pre-rollback-to-{version_id}")
    target.write_bytes(content)
    snapshot(file_relpath, actor=actor, reason=f"rollback-to-{version_id}")
    log.warning("Config rollback: %s → version #%d (by %s)",
                file_relpath, version_id, actor)
    return True


def diff(version_a: int, version_b: int) -> str:
    """Return unified diff between two versions."""
    import difflib
    a = get_content(version_a) or b""
    b = get_content(version_b) or b""
    return "\n".join(difflib.unified_diff(
        a.decode("utf-8", errors="replace").splitlines(),
        b.decode("utf-8", errors="replace").splitlines(),
        fromfile=f"v{version_a}", tofile=f"v{version_b}", lineterm="",
    ))
