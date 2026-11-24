"""
Retention policy manager.

Runs periodically (see start()) and deletes data older than the configured
retention window. This is our defence line for nDSG/GDPR Art. 5(1)(e)
"storage limitation" -- data must not be kept longer than needed.

Config in gateway.yaml:

  retention:
    history_days: 90        # SQLite dispatches
    dlq_days: 30            # dead-letter *.hl7 + *.meta.json
    orders_days: 7          # bidirectional orders that were not completed
    gateway_log_days: 30    # gateway.log rotations
    audit_days: 730         # audit log (regulatory: 2 years)
    seen_samples_days: 7    # dedup cache

Anything not listed uses the default. Setting a value to 0 disables purge
for that category (never purge -- use with caution).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

log = logging.getLogger("loc200.retention")

_DEFAULTS = {
    "history_days":       90,
    "dlq_days":           30,
    "orders_days":        7,
    "gateway_log_days":   30,
    "audit_days":         730,
    "seen_samples_days":  7,
    "idempotency_hours":  24,
}


def _load_config() -> Dict[str, int]:
    try:
        import yaml
        cfg = yaml.safe_load(Path("config/gateway.yaml").read_text(encoding="utf-8")) or {}
        r = cfg.get("retention") or {}
        merged = dict(_DEFAULTS)
        for k, v in r.items():
            if isinstance(v, int) and v >= 0:
                merged[k] = v
        return merged
    except Exception as exc:
        log.warning("cannot load retention config: %s", exc)
        return dict(_DEFAULTS)


# ── Individual purge routines ────────────────────────────────────────────────

def purge_history(days: int) -> int:
    """Delete rows from history.db older than N days. Returns rows deleted."""
    if days <= 0:
        return 0
    from src.common.history import _get_conn
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with _get_conn() as c:
        cur = c.execute("DELETE FROM dispatches WHERE ts < ?", (cutoff,))
        c.commit()
        return cur.rowcount


def purge_dlq(days: int) -> int:
    """Delete DLQ .hl7/.hl7.enc/.meta.json older than N days. Returns files deleted."""
    if days <= 0:
        return 0
    root = Path("logs/dead_letter")
    if not root.exists():
        return 0
    cutoff = time.time() - days * 86400
    n = 0
    for f in root.rglob("*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            try:
                f.unlink()
                n += 1
            except OSError as exc:
                log.warning("cannot delete %s: %s", f, exc)
    # Clean empty directories bottom-up
    for d in sorted(root.rglob("*"), key=lambda p: -len(p.parts)):
        if d.is_dir() and not any(d.iterdir()):
            try:
                d.rmdir()
            except OSError:
                pass
    return n


def purge_orders(days: int) -> int:
    if days <= 0:
        return 0
    root = Path("logs/orders")
    if not root.exists():
        return 0
    cutoff = time.time() - days * 86400
    n = 0
    for f in root.glob("*.json"):
        if f.stat().st_mtime < cutoff:
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
    return n


def purge_gateway_log(days: int) -> int:
    """Delete rotated gateway.log.N older than N days (never touch current file)."""
    if days <= 0:
        return 0
    root = Path("logs")
    if not root.exists():
        return 0
    cutoff = time.time() - days * 86400
    n = 0
    for f in root.glob("gateway.log.*"):
        if f.stat().st_mtime < cutoff:
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
    return n


def purge_audit(days: int) -> int:
    """Delete audit.jsonl.N older than N days."""
    if days <= 0:
        return 0
    root = Path("logs")
    cutoff = time.time() - days * 86400
    n = 0
    for f in root.glob("audit.jsonl.*"):
        if f.stat().st_mtime < cutoff:
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
    return n


def purge_seen_samples(days: int) -> int:
    if days <= 0:
        return 0
    p = Path("logs/seen_samples.json")
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text())
    except Exception:
        return 0
    cutoff = datetime.now() - timedelta(days=days)
    kept = {}
    n = 0
    for k, v in data.items():
        try:
            if datetime.fromisoformat(v) >= cutoff:
                kept[k] = v
            else:
                n += 1
        except Exception:
            n += 1
    if n:
        p.write_text(json.dumps(kept, indent=2))
    return n


# ── Orchestration ────────────────────────────────────────────────────────────

def _purge_idempotency(hours: int) -> int:
    """Idempotency keys are TTL'd — this trims the SQLite store."""
    try:
        from src.common.idempotency import purge_expired
        return purge_expired(ttl_seconds=int(hours) * 3600)
    except Exception as exc:
        log.debug("idempotency purge failed: %s", exc)
        return 0


def run_once() -> Dict[str, int]:
    """Execute all purges once. Returns a report."""
    cfg = _load_config()
    report = {
        "history":       purge_history(cfg["history_days"]),
        "dlq":           purge_dlq(cfg["dlq_days"]),
        "orders":        purge_orders(cfg["orders_days"]),
        "gateway_log":   purge_gateway_log(cfg["gateway_log_days"]),
        "audit":         purge_audit(cfg["audit_days"]),
        "seen_samples":  purge_seen_samples(cfg["seen_samples_days"]),
        "idempotency":   _purge_idempotency(cfg.get("idempotency_hours", 24)),
    }
    total = sum(report.values())
    if total:
        log.info("Retention pass: purged %s", report)
    return report


def start_background(interval_sec: int = 86400) -> None:
    """
    Start a daemon thread that runs run_once() every `interval_sec`.
    Called from Gateway.start().
    """
    import threading
    def _loop():
        # Skip first pass right after boot to avoid double-hit if gateway
        # restarts often; wait 5 min.
        time.sleep(300)
        while True:
            try:
                run_once()
            except Exception as exc:
                log.warning("retention pass failed: %s", exc)
            time.sleep(interval_sec)
    t = threading.Thread(target=_loop, name="retention-worker", daemon=True)
    t.start()
