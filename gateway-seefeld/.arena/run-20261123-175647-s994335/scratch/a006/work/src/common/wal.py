"""
Write-Ahead Log for exactly-once delivery.

Sequence:
  1. Before sending a message to the LIS, we WRITE a WAL entry:
        {uuid, ts, target, control_id, hl7_sha, state=in_flight}
  2. Send to LIS, wait for MSA ACK.
  3. On ACK: DELETE the WAL entry.
  4. On crash before ACK: at boot, we scan the WAL for `in_flight`
     entries and either
       (a) query the LIS with a Q-record for the control_id, OR
       (b) retry the send with the same control_id (LIS-side dedup).
     Then delete the entry either way.

This turns at-least-once + LIS-side dedup into effectively **exactly-once
delivery guarantee** as long as the LIS honors control_id uniqueness.

SQLite backed for atomicity + crash-safety.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
import uuid as _uuid
from pathlib import Path
from threading import Lock
from typing import Any

log = logging.getLogger("loc200.wal")

_DB = Path("logs/wal.db")
_LOCK = Lock()


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(_DB, check_same_thread=False, timeout=5.0)
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("""
        CREATE TABLE IF NOT EXISTS in_flight (
            uuid       TEXT PRIMARY KEY,
            ts         REAL NOT NULL,
            target     TEXT NOT NULL,
            control_id TEXT NOT NULL,
            hl7_sha    TEXT NOT NULL,
            state      TEXT NOT NULL,      -- 'in_flight' | 'acked' | 'nacked'
            attempts   INTEGER NOT NULL DEFAULT 0,
            payload    BLOB
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_wal_target ON in_flight(target)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_wal_ts ON in_flight(ts)")
    return c


def enter(target: str, control_id: str, hl7_body: str | bytes) -> str:
    """Register a message about to be sent. Returns a unique UUID token."""
    if isinstance(hl7_body, str):
        hl7_body = hl7_body.encode("utf-8")
    u = _uuid.uuid4().hex
    sha = hashlib.sha256(hl7_body).hexdigest()
    with _LOCK, _conn() as c:
        c.execute(
            "INSERT INTO in_flight (uuid, ts, target, control_id, hl7_sha, state, attempts, payload) "
            "VALUES (?, ?, ?, ?, ?, 'in_flight', 0, ?)",
            (u, time.time(), target, str(control_id), sha, hl7_body),
        )
    return u


def ack(uuid: str) -> None:
    """Mark delivered and remove from WAL — the message is officially at the LIS."""
    with _LOCK, _conn() as c:
        c.execute("DELETE FROM in_flight WHERE uuid = ?", (uuid,))


def nack(uuid: str) -> None:
    """Mark rejected — keep for manual inspection."""
    with _LOCK, _conn() as c:
        c.execute("UPDATE in_flight SET state='nacked', attempts=attempts+1 WHERE uuid = ?",
                  (uuid,))


def in_flight_count() -> int:
    with _LOCK, _conn() as c:
        r = c.execute("SELECT COUNT(*) FROM in_flight WHERE state='in_flight'").fetchone()
        return int(r[0]) if r else 0


def list_orphaned(older_than_seconds: int = 60) -> list[dict[str, Any]]:
    """
    Entries still in_flight after the timeout — crash residue.

    ``<=`` (not ``<``) so ``older_than_seconds=0`` means "every in_flight
    entry, right now", regardless of clock resolution. Otherwise the
    recover_at_boot() sweep races against ``time.time()`` and misses
    entries written in the same microsecond.
    """
    cutoff = time.time() - older_than_seconds
    with _LOCK, _conn() as c:
        rows = c.execute(
            "SELECT uuid, ts, target, control_id, hl7_sha, attempts "
            "FROM in_flight WHERE state='in_flight' AND ts <= ? ORDER BY ts",
            (cutoff,),
        ).fetchall()
    return [
        {"uuid": r[0], "ts": r[1], "target": r[2], "control_id": r[3],
         "hl7_sha": r[4], "attempts": r[5]}
        for r in rows
    ]


def get_payload(uuid: str) -> bytes | None:
    with _LOCK, _conn() as c:
        r = c.execute("SELECT payload FROM in_flight WHERE uuid = ?", (uuid,)).fetchone()
        return bytes(r[0]) if r else None


def recover_at_boot(replay_fn) -> dict[str, int]:
    """
    Called once at startup. For every orphaned in_flight entry,
    call replay_fn(uuid, target, control_id, payload) → 'ack' | 'skip' | 'retry'.
    """
    report = {"total": 0, "acked": 0, "skipped": 0, "retried": 0}
    for entry in list_orphaned(older_than_seconds=0):
        report["total"] += 1
        payload = get_payload(entry["uuid"])
        if payload is None:
            ack(entry["uuid"])
            report["skipped"] += 1
            continue
        try:
            action = replay_fn(entry["uuid"], entry["target"],
                               entry["control_id"], payload)
        except Exception as exc:
            log.warning("WAL replay failed for %s: %s", entry["uuid"], exc)
            action = "skip"
        if action == "ack":
            ack(entry["uuid"])
            report["acked"] += 1
        elif action == "retry":
            with _LOCK, _conn() as c:
                c.execute("UPDATE in_flight SET attempts=attempts+1 WHERE uuid = ?",
                          (entry["uuid"],))
            report["retried"] += 1
        else:
            ack(entry["uuid"])  # remove even on skip so we don't loop
            report["skipped"] += 1
    if report["total"]:
        log.warning("WAL recovery at boot: %s", report)
    return report
