"""
Dead-letter queue.

When a message fails ALL retries on ALL enabled targets, or when a message
is dropped due to queue backpressure, we persist it under
``logs/dead_letter/YYYY/MM/DD/`` so it can be replayed manually.

Each entry produces two files:

  <control-id>.hl7        -- the raw HL7 message
  <control-id>.meta.json  -- context: timestamp, sample id, targets, errors
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

log = logging.getLogger("loc200.dead_letter")

_DLQ_ROOT = Path("logs/dead_letter")


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:80] or "unknown"


def _encryption_on() -> bool:
    """Read config once; default True (encryption is safer)."""
    if os.environ.get("DLQ_ENCRYPTION", "").lower() in ("0", "false", "no"):
        return False
    return True


def write_dead_letter(
    *,
    hl7_body: str,
    control_id: str,
    sample_id: str = "",
    device: str = "",
    targets: Optional[Iterable[str]] = None,
    errors: Optional[Dict[str, str]] = None,
    reason: str = "",
) -> Optional[Path]:
    """
    Persist a failed message to the DLQ.  Returns the .hl7 path or None on error.

    Body is encrypted at rest (Fernet) if `cryptography` is available and
    encryption is enabled -- file has extension `.hl7.enc` in that case.

    Never raises -- DLQ failure must not take down the gateway.
    """
    try:
        now = datetime.now()
        day_dir = _DLQ_ROOT / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}"
        day_dir.mkdir(parents=True, exist_ok=True)

        cid = _slug(control_id) if control_id else uuid.uuid4().hex[:16].upper()

        # Decide extension based on encryption availability
        encrypt = _encryption_on()
        if encrypt:
            from src.common.encryption import encrypt_bytes, is_available
            encrypt = is_available()
        ext = ".hl7.enc" if encrypt else ".hl7"

        base = day_dir / cid
        hl7_path  = base.with_suffix(ext)
        meta_path = base.with_suffix(".meta.json")

        # If a file with this name already exists, add a suffix
        if hl7_path.exists():
            hl7_path  = day_dir / f"{cid}_{now:%H%M%S%f}{ext}"
            meta_path = hl7_path.with_suffix(".meta.json")

        # atomic write
        tmp = hl7_path.with_suffix(ext + ".tmp")
        if encrypt:
            from src.common.encryption import encrypt_bytes
            tmp.write_bytes(encrypt_bytes(hl7_body.encode("utf-8", errors="replace")))
        else:
            tmp.write_text(hl7_body, encoding="utf-8", errors="replace")
        os.replace(tmp, hl7_path)

        meta: Dict[str, Any] = {
            "ts":         now.isoformat(),
            "control_id": control_id,
            "sample_id":  sample_id,
            "device":     device,
            "targets":    list(targets or []),
            "errors":     errors or {},
            "reason":     reason,
        }
        tmp2 = meta_path.with_suffix(".meta.json.tmp")
        tmp2.write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        os.replace(tmp2, meta_path)

        log.warning("Dead-letter written: %s (%s)", hl7_path.name, reason or "?")
        return hl7_path
    except Exception as exc:
        log.error("DLQ write failed: %s", exc)
        return None


def list_dead_letters(limit: int = 100) -> list[Dict[str, Any]]:
    """List recent DLQ entries (metadata only, newest first)."""
    entries: list[tuple[float, Path]] = []
    if not _DLQ_ROOT.exists():
        return []
    for meta in _DLQ_ROOT.rglob("*.meta.json"):
        try:
            entries.append((meta.stat().st_mtime, meta))
        except OSError:
            continue
    entries.sort(reverse=True)
    out = []
    for _mtime, meta in entries[:limit]:
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            data["_path"] = str(meta.with_suffix(".hl7"))
            data["_size"] = meta.with_suffix(".hl7").stat().st_size \
                            if meta.with_suffix(".hl7").exists() else 0
            out.append(data)
        except Exception:
            continue
    return out


def read_dead_letter(control_id: str) -> Optional[str]:
    """Return the raw HL7 body of a DLQ entry, or None if not found."""
    cid = _slug(control_id)
    for pattern in ("*.hl7", "*.hl7.enc"):
        for f in _DLQ_ROOT.rglob(pattern):
            # stem strips only one extension; enc files have stem "<cid>.hl7"
            stem = f.stem
            if stem.endswith(".hl7"):
                stem = stem[:-4]
            if stem.startswith(cid):
                try:
                    data = f.read_bytes()
                    if data.startswith(b"FRNT1"):
                        from src.common.encryption import decrypt_bytes
                        data = decrypt_bytes(data)
                    return data.decode("utf-8", errors="replace")
                except Exception:
                    return None
    return None
