"""
Append-only audit log for nDSG / GDPR compliance.

Events are written to logs/audit.jsonl (one JSON object per line).
Patient identifiers are never logged — only hashed sample references.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("loc200.audit")

_AUDIT_FILE = Path("logs/audit.jsonl")
_RETENTION_DAYS = 90
_AUDIT_MAX_BYTES = 10 * 1024 * 1024   # 10 MiB per file
_AUDIT_KEEP_ROTATIONS = 12            # keep audit.jsonl.1 .. .12


def _rotate_if_needed() -> None:
    try:
        if not _AUDIT_FILE.exists():
            return
        if _AUDIT_FILE.stat().st_size < _AUDIT_MAX_BYTES:
            return
        # Shift .N -> .N+1, dropping the oldest
        for i in range(_AUDIT_KEEP_ROTATIONS - 1, 0, -1):
            src = _AUDIT_FILE.with_suffix(f".jsonl.{i}")
            dst = _AUDIT_FILE.with_suffix(f".jsonl.{i+1}")
            if src.exists():
                try:
                    src.replace(dst)
                except OSError:
                    pass
        _AUDIT_FILE.replace(_AUDIT_FILE.with_suffix(".jsonl.1"))
    except OSError:
        pass


class AuditEvent(str, Enum):
    LOGIN_SUCCESS = "login.success"
    LOGIN_FAILURE = "login.failure"
    LOGOUT = "logout"
    CONFIG_READ = "config.read"
    CONFIG_SAVE = "config.save"
    PASSWORD_CHANGE = "password.change"
    MESSAGE_SENT = "message.sent"
    MESSAGE_FAILED = "message.failed"
    DEVICE_CONNECTED = "device.connected"
    SERVICE_ACTION = "service.action"
    SETUP_COMPLETE = "setup.complete"


def _hash_ref(value: str) -> str:
    if not value or value == "?":
        return ""
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def audit(
    event: AuditEvent | str,
    *,
    actor: str = "system",
    ip: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """Append an audit event. Never raises — failures are logged only."""
    try:
        _AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event.value if isinstance(event, AuditEvent) else event,
            "actor": actor,
        }
        if ip:
            record["ip"] = ip
        if detail:
            safe = {}
            for k, v in detail.items():
                if k in ("patient_id", "patient_name", "sample_id"):
                    safe[k] = _hash_ref(str(v))
                else:
                    safe[k] = v
            record["detail"] = safe
        _rotate_if_needed()
        with _AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.debug("Audit write failed: %s", exc)


def audit_message_sent(
    device: str,
    sample_id: str,
    target: str,
    analytes: int,
) -> None:
    audit(AuditEvent.MESSAGE_SENT, detail={
        "device": device,
        "sample_id": sample_id,
        "target": target,
        "analytes": analytes,
    })


def audit_message_failed(device: str, sample_id: str, target: str, error: str) -> None:
    audit(AuditEvent.MESSAGE_FAILED, detail={
        "device": device,
        "sample_id": sample_id,
        "target": target,
        "error": error[:200],
    })


def read_recent(limit: int = 100) -> list[dict]:
    if not _AUDIT_FILE.exists():
        return []
    lines = _AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    result = []
    for line in lines[-limit:]:
        try:
            result.append(json.loads(line))
        except Exception:
            continue
    return list(reversed(result))
