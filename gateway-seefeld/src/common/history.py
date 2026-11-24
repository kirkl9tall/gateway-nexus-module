"""
Persistent dispatch history on SQLite.

Fast to write (WAL mode, one insert per message), searchable by patient_id
/ sample_id / device / target / date range without loading the whole log
into memory. Complements the in-memory `_history` (last 500) used for the
dashboard.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("loc200.history")

_DB_PATH = Path("logs/history.db")
_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False, timeout=5.0)
    _conn.execute("PRAGMA journal_mode=WAL;")
    _conn.execute("PRAGMA synchronous=NORMAL;")
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS dispatches (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ts            TEXT    NOT NULL,
            device        TEXT,
            sample_id     TEXT,
            patient_id    TEXT,
            control_id    TEXT,
            analytes      INTEGER,
            status        TEXT,
            succeeded     TEXT,
            failed        TEXT,
            errors        TEXT
        );
    """)
    # Idempotent ALTERs -- columns added after the first release.
    #   conversion_audit  JSON blob (raw→sent trail per sample)
    #   hl7               exact message that was dispatched (verbatim resend)
    #   result_json       parsed result dict (rebuild-with-current-config resend)
    _cols = [r[1] for r in _conn.execute("PRAGMA table_info(dispatches)").fetchall()]
    for _new_col in ("conversion_audit", "hl7", "result_json"):
        if _new_col not in _cols:
            try:
                _conn.execute(f"ALTER TABLE dispatches ADD COLUMN {_new_col} TEXT")
            except sqlite3.OperationalError:
                pass
    for _col, expr in [
        ("idx_ts",         "CREATE INDEX IF NOT EXISTS idx_ts         ON dispatches(ts)"),
        ("idx_sample",     "CREATE INDEX IF NOT EXISTS idx_sample     ON dispatches(sample_id)"),
        ("idx_patient",    "CREATE INDEX IF NOT EXISTS idx_patient    ON dispatches(patient_id)"),
        ("idx_device",     "CREATE INDEX IF NOT EXISTS idx_device     ON dispatches(device)"),
        ("idx_status",     "CREATE INDEX IF NOT EXISTS idx_status     ON dispatches(status)"),
    ]:
        _conn.execute(expr)
    _conn.commit()
    return _conn


def _dump_result(result: Any) -> Optional[str]:
    """
    Serialise the parsed result dict for later re-dispatch.

    ``conversion_audit`` is dropped (it has its own column) and datetimes are
    stringified -- ``default=str`` keeps this total, so a exotic payload can
    never make ``record()`` raise.
    """
    if not isinstance(result, dict):
        return None
    try:
        slim = {k: v for k, v in result.items() if k != "conversion_audit"}
        return json.dumps(slim, ensure_ascii=False, default=str)
    except Exception:
        return None


def record(entry: Dict[str, Any]) -> None:
    """Insert one dispatch record. Never raises."""
    try:
        with _lock:
            c = _get_conn()
            c.execute(
                "INSERT INTO dispatches "
                "(ts, device, sample_id, patient_id, control_id, analytes, "
                " status, succeeded, failed, errors, conversion_audit, "
                " hl7, result_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (
                    entry.get("ts") or datetime.now().isoformat(),
                    str(entry.get("device", ""))[:120],
                    str(entry.get("sample_id", ""))[:120],
                    str(entry.get("patient_id", ""))[:120],
                    str(entry.get("control_id", ""))[:80],
                    int(entry.get("analytes", 0) or 0),
                    str(entry.get("status", ""))[:20],
                    json.dumps(entry.get("succeeded") or [], ensure_ascii=False),
                    json.dumps(entry.get("failed") or [], ensure_ascii=False),
                    json.dumps(entry.get("errors") or {}, ensure_ascii=False),
                    entry.get("conversion_audit") or None,
                    entry.get("hl7") or None,
                    _dump_result(entry.get("result")),
                ),
            )
            c.commit()
    except Exception as exc:
        log.debug("history record failed: %s", exc)


def get_audit(sample_id: str) -> Optional[Dict[str, Any]]:
    """Return the most recent conversion audit stored for this sample_id."""
    if not sample_id:
        return None
    try:
        with _lock:
            c = _get_conn()
            row = c.execute(
                "SELECT conversion_audit, ts, device, patient_id, status "
                "FROM dispatches WHERE sample_id = ? AND conversion_audit IS NOT NULL "
                "ORDER BY id DESC LIMIT 1",
                (sample_id,),
            ).fetchone()
            if not row:
                return None
            try:
                audit = json.loads(row[0])
            except (TypeError, json.JSONDecodeError):
                return None
            return {
                "sample_id":  sample_id,
                "ts":         row[1],
                "device":     row[2],
                "patient_id": row[3],
                "status":     row[4],
                "audit":      audit,
            }
    except Exception as exc:
        log.warning("get_audit failed: %s", exc)
        return None


def get_payload(sample_id: str) -> Optional[Dict[str, Any]]:
    """
    Return what is needed to re-dispatch a sample: the parsed result dict
    (preferred -- lets the message be rebuilt with the *current* config) and
    the exact HL7 that was sent (fallback -- verbatim resend).

    Rows written before these columns existed return ``None`` for both, and
    the caller reports that instead of sending something half-made.
    """
    if not sample_id:
        return None
    try:
        with _lock:
            c = _get_conn()
            row = c.execute(
                "SELECT ts, device, patient_id, control_id, status, hl7, result_json "
                "FROM dispatches WHERE sample_id = ? ORDER BY id DESC LIMIT 1",
                (sample_id,),
            ).fetchone()
    except Exception as exc:
        log.warning("history.get_payload failed: %s", exc)
        return None
    if not row:
        return None
    try:
        result = json.loads(row[6]) if row[6] else None
    except (TypeError, json.JSONDecodeError):
        result = None
    return {
        "sample_id":  sample_id,
        "ts":         row[0],
        "device":     row[1],
        "patient_id": row[2],
        "control_id": row[3],
        "status":     row[4],
        "hl7":        row[5],
        "result":     result,
    }


def search(
    *,
    q: str = "",
    device: str = "",
    status: str = "",
    since: str = "",
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Free-text search across sample/patient/control id, plus filters."""
    where: list[str] = []
    args: list[Any] = []
    if q:
        where.append("(sample_id LIKE ? OR patient_id LIKE ? OR control_id LIKE ?)")
        like = f"%{q}%"
        args += [like, like, like]
    if device:
        where.append("device = ?"); args.append(device)
    if status:
        where.append("status = ?"); args.append(status)
    if since:
        where.append("ts >= ?"); args.append(since)
    sql = "SELECT * FROM dispatches"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    args += [max(1, min(limit, 1000)), max(0, offset)]

    with _lock:
        c = _get_conn()
        c.row_factory = sqlite3.Row
        rows = list(c.execute(sql, args))
        c.row_factory = None

    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        for k in ("succeeded", "failed", "errors"):
            try:
                d[k] = json.loads(d[k]) if d.get(k) else ([] if k != "errors" else {})
            except Exception:
                pass
        out.append(d)
    return out


def counts_by_status(since: str = "") -> Dict[str, int]:
    with _lock:
        c = _get_conn()
        if since:
            rows = c.execute("SELECT status, COUNT(*) FROM dispatches WHERE ts>=? GROUP BY status", (since,))
        else:
            rows = c.execute("SELECT status, COUNT(*) FROM dispatches GROUP BY status")
        return {row[0] or "?": row[1] for row in rows}


def hourly_counts(hours: int = 24) -> List[Dict[str, Any]]:
    """Return count per hour for the last N hours (for trend chart)."""
    from datetime import timedelta
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    with _lock:
        c = _get_conn()
        rows = list(c.execute(
            "SELECT substr(ts,1,13) AS hour, "
            "SUM(CASE WHEN status='OK' THEN 1 ELSE 0 END) AS ok, "
            "SUM(CASE WHEN status='PARZIALE' THEN 1 ELSE 0 END) AS partial, "
            "SUM(CASE WHEN status='ERRORE' THEN 1 ELSE 0 END) AS err "
            "FROM dispatches WHERE ts>=? GROUP BY hour ORDER BY hour",
            (since,),
        ))
    return [{"hour": r[0], "ok": r[1] or 0, "partial": r[2] or 0, "err": r[3] or 0}
            for r in rows]


# ── Read-only summaries for the Web UI overview ───────────────────────────────

def daily_counts(days: int = 7) -> List[Dict[str, Any]]:
    """One row per calendar day (oldest first) for the last ``days`` days,
    including days with no results. ``total`` counts every result received;
    ``ok`` those delivered to every target."""
    from datetime import date, timedelta
    days = max(1, min(int(days), 90))
    first = date.today() - timedelta(days=days - 1)
    with _lock:
        c = _get_conn()
        rows = c.execute(
            "SELECT substr(ts,1,10) AS d, COUNT(*), "
            "SUM(CASE WHEN status='OK' THEN 1 ELSE 0 END) "
            "FROM dispatches WHERE ts >= ? GROUP BY d",
            (first.isoformat(),),
        ).fetchall()
    by_day = {r[0]: (r[1] or 0, r[2] or 0) for r in rows}
    out = []
    for i in range(days):
        d = (first + timedelta(days=i)).isoformat()
        total, ok = by_day.get(d, (0, 0))
        out.append({"date": d, "total": total, "ok": ok})
    return out


def activity_since(since: str) -> List[Dict[str, Any]]:
    """Light rows (no HL7 payload) since an ISO timestamp, newest first:
    ts, device, status, succeeded[], failed[]."""
    with _lock:
        c = _get_conn()
        rows = c.execute(
            "SELECT ts, device, status, succeeded, failed FROM dispatches "
            "WHERE ts >= ? ORDER BY ts DESC LIMIT 5000",
            (since,),
        ).fetchall()
    out = []
    for ts, device, status, succ, fail in rows:
        try:
            succ_l = json.loads(succ) if succ else []
        except Exception:
            succ_l = []
        try:
            fail_l = json.loads(fail) if fail else []
        except Exception:
            fail_l = []
        out.append({"ts": ts, "device": device or "", "status": status or "",
                    "succeeded": succ_l, "failed": fail_l})
    return out


def last_activity() -> Optional[Dict[str, Any]]:
    """Most recent dispatch row (ts, device, status), or None."""
    with _lock:
        c = _get_conn()
        r = c.execute("SELECT ts, device, status FROM dispatches "
                      "ORDER BY ts DESC LIMIT 1").fetchone()
    return {"ts": r[0], "device": r[1] or "", "status": r[2] or ""} if r else None


def device_last_seen() -> Dict[str, str]:
    """Latest result timestamp per device, across all history."""
    with _lock:
        c = _get_conn()
        rows = c.execute("SELECT device, MAX(ts) FROM dispatches GROUP BY device").fetchall()
    return {r[0]: r[1] for r in rows if r[0]}


def list_results(*, q: str = "", device: str = "", status: str = "",
                 since: str = "", until: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    """Light list for the Results page (no HL7 payload): newest first."""
    where, args = [], []
    if q:
        where.append("(sample_id LIKE ? OR patient_id LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    if device:
        where.append("device = ?"); args.append(device)
    if status == "problem":                  # anything not fully delivered
        where.append("status != 'OK'")
    elif status:
        where.append("status = ?"); args.append(status)
    if since:
        where.append("ts >= ?"); args.append(since)
    if until:
        where.append("ts < ?"); args.append(until)
    sql = ("SELECT id, ts, device, sample_id, patient_id, analytes, status, succeeded, failed "
           "FROM dispatches")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(int(limit), 500)))
    with _lock:
        rows = _get_conn().execute(sql, args).fetchall()
    out = []
    for r in rows:
        def _list(v):
            try:
                return json.loads(v) if v else []
            except Exception:
                return []
        out.append({"id": r[0], "ts": r[1], "device": r[2] or "", "sample_id": r[3] or "",
                    "patient_id": r[4] or "", "analytes": r[5] or 0, "status": r[6] or "",
                    "succeeded": _list(r[7]), "failed": _list(r[8])})
    return out


def devices_seen() -> List[str]:
    with _lock:
        rows = _get_conn().execute(
            "SELECT DISTINCT device FROM dispatches WHERE device != '' ORDER BY device").fetchall()
    return [r[0] for r in rows]


def get_entry(entry_id: int) -> Optional[Dict[str, Any]]:
    """One dispatch with everything: parsed result, errors and the HL7 sent."""
    with _lock:
        c = _get_conn()
        c.row_factory = sqlite3.Row
        try:
            row = c.execute("SELECT * FROM dispatches WHERE id = ?", (int(entry_id),)).fetchone()
        finally:
            c.row_factory = None
    if not row:
        return None
    d = dict(row)
    for k, default in (("succeeded", []), ("failed", []), ("errors", {}), ("result_json", None)):
        try:
            d[k] = json.loads(d[k]) if d.get(k) else default
        except Exception:
            d[k] = default
    d["result"] = d.pop("result_json")
    return d
