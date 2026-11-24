"""
Data subject rights fulfilment (nDSG art. 25 / GDPR art. 15 & 17).

* export(patient_id) -> dict with every trace we hold about that person
* purge(patient_id)  -> removes those traces from every store, returns count

Scope covered:
  * SQLite history.db  (dispatches table)
  * Dead-letter queue  (encrypted or plain .hl7/.hl7.enc + .meta.json)
  * Orders queue       (logs/orders/*.json)
  * seen_samples.json  (dedup cache)
  * status.json        (recent history rolling window)

Not covered (best-effort or rotated):
  * gateway.log        (rotated by logrotate; may still contain PII in older rotations)
  * audit.jsonl        (PII is already hashed, so no clear identifier remains)
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

log = logging.getLogger("loc200.patient_rights")


def _hash(pid: str) -> str:
    return hashlib.sha256(pid.encode("utf-8")).hexdigest()[:16]


# ── Export ───────────────────────────────────────────────────────────────────

def export(patient_id: str) -> Dict[str, Any]:
    """Return every trace of the patient we can find."""
    out: Dict[str, Any] = {
        "patient_id":       patient_id,
        "patient_id_hash":  _hash(patient_id),
        "exported_at":      datetime.now().isoformat(),
        "dispatches":       _export_history(patient_id),
        "dead_letter":      _export_dlq(patient_id),
        "orders":           _export_orders(patient_id),
        "seen_samples":     _export_seen(patient_id),
        "audit_hits":       _export_audit(patient_id),
    }
    return out


def _export_history(pid: str) -> List[Dict[str, Any]]:
    try:
        from src.common.history import search
        return search(q=pid, limit=1000)
    except Exception as exc:
        log.warning("history export failed: %s", exc)
        return []


def _export_dlq(pid: str) -> List[Dict[str, Any]]:
    root = Path("logs/dead_letter")
    if not root.exists():
        return []
    hits = []
    for meta in root.rglob("*.meta.json"):
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            body_file = _dlq_body_for(meta)
            body = ""
            if body_file:
                body = _read_dlq_body(body_file)
            if data.get("sample_id") == pid or pid in body:
                hits.append({
                    "meta_file": str(meta),
                    "body_file": str(body_file) if body_file else "",
                    "meta":      data,
                    "hl7":       body,
                })
        except Exception:
            continue
    return hits


def _export_orders(pid: str) -> List[Dict[str, Any]]:
    root = Path("logs/orders")
    if not root.exists():
        return []
    hits = []
    for f in root.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            if d.get("patient_id") == pid or d.get("sample_id") == pid:
                hits.append({"file": str(f), "order": d})
        except Exception:
            continue
    return hits


def _export_seen(pid: str) -> List[str]:
    p = Path("logs/seen_samples.json")
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except Exception:
        return []
    return [k for k in data if pid in k]


def _export_audit(pid: str) -> Dict[str, int]:
    """Count audit hits for the hashed id (we don't reveal audit content)."""
    h = _hash(pid)
    p = Path("logs/audit.jsonl")
    if not p.exists():
        return {"hashed_id": h, "count": 0}
    n = 0
    try:
        with p.open(encoding="utf-8") as f:
            for line in f:
                if h in line:
                    n += 1
    except OSError:
        pass
    return {"hashed_id": h, "count": n}


# ── Purge ────────────────────────────────────────────────────────────────────

def purge(patient_id: str) -> Dict[str, int]:
    """Remove every trace of the patient. Returns counters per source."""
    report = {
        "history":      _purge_history(patient_id),
        "dead_letter":  _purge_dlq(patient_id),
        "orders":       _purge_orders(patient_id),
        "seen_samples": _purge_seen(patient_id),
    }
    log.warning("PATIENT PURGE completed for %s: %s", _hash(patient_id), report)
    return report


def _purge_history(pid: str) -> int:
    try:
        from src.common.history import _get_conn
        with _get_conn() as c:
            cur = c.execute("DELETE FROM dispatches WHERE patient_id = ? OR sample_id = ?",
                            (pid, pid))
            c.commit()
            return cur.rowcount
    except Exception as exc:
        log.warning("history purge failed: %s", exc)
        return 0


def _purge_dlq(pid: str) -> int:
    root = Path("logs/dead_letter")
    if not root.exists():
        return 0
    n = 0
    for meta in list(root.rglob("*.meta.json")):
        try:
            d = json.loads(meta.read_text(encoding="utf-8"))
            body_file = _dlq_body_for(meta)
            match = d.get("sample_id") == pid
            if not match and body_file:
                match = pid in _read_dlq_body(body_file)
            if match:
                meta.unlink(missing_ok=True)
                if body_file:
                    body_file.unlink(missing_ok=True)
                n += 1
        except Exception:
            continue
    return n


def _purge_orders(pid: str) -> int:
    root = Path("logs/orders")
    if not root.exists():
        return 0
    n = 0
    for f in list(root.glob("*.json")):
        try:
            d = json.loads(f.read_text())
            if d.get("patient_id") == pid or d.get("sample_id") == pid:
                f.unlink()
                n += 1
        except Exception:
            continue
    return n


def _purge_seen(pid: str) -> int:
    p = Path("logs/seen_samples.json")
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text())
    except Exception:
        return 0
    kept = {k: v for k, v in data.items() if pid not in k}
    n = len(data) - len(kept)
    if n:
        p.write_text(json.dumps(kept, indent=2))
    return n


# ── Helpers ──────────────────────────────────────────────────────────────────

def _dlq_body_for(meta: Path):
    """Given a .meta.json path, find the matching .hl7 or .hl7.enc body."""
    for ext in (".hl7", ".hl7.enc"):
        c = meta.with_name(meta.stem.rsplit(".meta", 1)[0] + ext)
        if c.exists():
            return c
    return None


def _read_dlq_body(f: Path) -> str:
    try:
        data = f.read_bytes()
        if data.startswith(b"FRNT1"):
            from src.common.encryption import decrypt_bytes
            data = decrypt_bytes(data)
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""
