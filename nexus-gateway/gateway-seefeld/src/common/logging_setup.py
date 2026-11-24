"""
Structured logging setup.

Text mode (default) matches the existing format; JSON mode emits one JSON
document per line -- ready for Loki / ELK / Datadog.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts":       datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level":    record.levelname,
            "logger":   record.name,
            "message":  record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Optional extra fields
        for key in ("sample_id", "device", "target", "control_id"):
            v = getattr(record, key, None)
            if v is not None:
                payload[key] = v
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", fmt: str = "text") -> None:
    """
    Wire the root logger. fmt: "text" | "json".
    LOG_FORMAT env variable overrides the argument.
    """
    fmt = (os.environ.get("LOG_FORMAT") or fmt).lower()
    lvl = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    # Reset any pre-existing handlers (e.g. from basicConfig)
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        ))
    root.addHandler(handler)
    root.setLevel(lvl)
