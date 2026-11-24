"""
Privacy helpers -- PII hashing + configurable log filter.

By default we HASH patient_id, sample_id and patient_name in every log line
before it goes to disk or journald. To disable for debug (never in prod):
  LOG_PII=1

Also provides:
  * hash_pii(value)      -- one-way SHA-256 truncated (16 hex chars)
  * install_log_filter() -- attaches PII filter to the root logger
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Optional

_HASH_LEN = 16


def hash_pii(value: Optional[str]) -> str:
    """Deterministic short hash of a PII value, safe to store in logs."""
    if value is None or value == "":
        return ""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:_HASH_LEN]


def log_pii_enabled() -> bool:
    """Return True if LOG_PII=1 (never in production)."""
    return os.environ.get("LOG_PII", "").lower() in ("1", "true", "yes")


# Patterns that identify PII in log messages.
# We replace `sample=PAT-42` with `sample=<hash>`, etc.
_PII_PATTERNS = [
    # key=value where key names a PII field
    re.compile(r"(patient[_-]?id|sample[_-]?id|patient[_-]?name)"
               r"([=:]\s*)([^\s,;]+)", re.IGNORECASE),
    # HL7 PID segment inline (rare in logs but possible)
    re.compile(r"(PID\|[^|]*\|)([^|]+)(\|)", re.IGNORECASE),
]


def redact(text: str) -> str:
    """Replace PII substrings with their hash (fast enough for hot log path)."""
    if log_pii_enabled():
        return text
    out = text
    for pat in _PII_PATTERNS:
        out = pat.sub(
            lambda m: f"{m.group(1)}{m.group(2)}<{hash_pii(m.group(3))}>"
                       if len(m.groups()) == 3 else m.group(0),
            out,
        )
    return out


class PIIFilter(logging.Filter):
    """Log filter that redacts PII from every log record's message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            record.msg = redact(msg)
            record.args = ()
        except Exception:
            pass
        return True


def install_log_filter() -> None:
    """Attach the PII filter to the root logger (idempotent)."""
    root = logging.getLogger()
    for f in root.filters:
        if isinstance(f, PIIFilter):
            return
    root.addFilter(PIIFilter())
