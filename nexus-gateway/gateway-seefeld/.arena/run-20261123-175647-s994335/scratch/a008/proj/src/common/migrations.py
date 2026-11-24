"""
Lightweight forward-only SQLite schema migrations.

Every migration is a Python function taking a `sqlite3.Connection`, listed
in `MIGRATIONS` in strict order. On boot the gateway compares the current
`schema_version` in `_schema` against the highest known migration and
applies any missing steps inside a single transaction each.

We deliberately avoid alembic — the schema is small (5 tables) and a
30-line runner is easier to review for medical audits than an external
dependency.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Callable

log = logging.getLogger("loc200.migrations")

MigrationFn = Callable[[sqlite3.Connection], None]


def _m001_initial(c: sqlite3.Connection) -> None:
    c.executescript("""
        CREATE TABLE IF NOT EXISTS dispatches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          REAL    NOT NULL,
            patient_id  TEXT,
            sample_id   TEXT,
            device      TEXT,
            target      TEXT,
            status      TEXT,
            payload_sha TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_dispatches_ts ON dispatches(ts);
        CREATE INDEX IF NOT EXISTS idx_dispatches_sample ON dispatches(sample_id);
    """)


def _m002_audit(c: sqlite3.Connection) -> None:
    c.executescript("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ts       REAL    NOT NULL,
            actor    TEXT,
            action   TEXT,
            detail   TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts);
    """)


def _m003_add_error_code(c: sqlite3.Connection) -> None:
    """Add error_code column to dispatches for the E1xxx taxonomy."""
    cols = [r[1] for r in c.execute("PRAGMA table_info(dispatches)").fetchall()]
    if "error_code" not in cols:
        c.execute("ALTER TABLE dispatches ADD COLUMN error_code TEXT")


MIGRATIONS: list[tuple[int, MigrationFn]] = [
    (1, _m001_initial),
    (2, _m002_audit),
    (3, _m003_add_error_code),
]


def apply(db_path: Path) -> int:
    """
    Apply any missing migrations. Returns the version now on disk.
    Idempotent: safe to call on every boot.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS _schema (
                version   INTEGER PRIMARY KEY,
                applied_at REAL NOT NULL
            )
        """)
        current = int(c.execute("SELECT COALESCE(MAX(version), 0) FROM _schema").fetchone()[0])
        for version, fn in MIGRATIONS:
            if version <= current:
                continue
            log.info("Applying migration %d (%s)", version, fn.__name__)
            try:
                c.execute("BEGIN")
                fn(c)
                c.execute("INSERT INTO _schema (version, applied_at) VALUES (?, strftime('%s','now'))",
                          (version,))
                c.execute("COMMIT")
                current = version
            except Exception as exc:
                c.execute("ROLLBACK")
                log.error("Migration %d failed: %s", version, exc)
                raise
        return current
