"""
JSON-line structured logging with OTel trace correlation.

Formatter emits one JSON object per line:
{
  "ts":       "2026-08-27T12:34:56.789Z",
  "level":    "INFO",
  "logger":   "loc200.sysmex",
  "msg":      "Parsed sample",
  "trace_id": "0af7651916cd43dd8448eb211c80319c",   # if OTel span active
  "span_id":  "b7ad6b7169203331",
  "device":   "sysmex_xq320",
  "sample_hash": "a6bc44b3c00172bd",
  ...arbitrary extra kwargs...
}

Turn on with LOG_FORMAT=json (default = text). Loki/CloudWatch/ELK
ingest directly.
"""
from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timezone
from typing import Any


class JsonLineFormatter(logging.Formatter):
    """Serialize each LogRecord as one JSON line."""

    _STD_FIELDS = {
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts":      datetime.fromtimestamp(record.created, tz=timezone.utc)
                              .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
        }
        # OTel trace correlation (if present)
        trace_id = getattr(record, "otelTraceID", None) or _current_trace_id()
        span_id  = getattr(record, "otelSpanID",  None) or _current_span_id()
        if trace_id:
            payload["trace_id"] = trace_id
        if span_id:
            payload["span_id"] = span_id
        # Extra kwargs the caller passed via `extra=`
        for k, v in record.__dict__.items():
            if k in self._STD_FIELDS or k.startswith("_"):
                continue
            if k in payload:
                continue
            try:
                json.dumps(v)   # ensure serializable
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = repr(v)
        if record.exc_info:
            payload["exc"] = "".join(traceback.format_exception(*record.exc_info)).strip()
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _current_trace_id() -> str | None:
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.trace_id:
            return f"{ctx.trace_id:032x}"
    except Exception:
        pass
    return None


def _current_span_id() -> str | None:
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.span_id:
            return f"{ctx.span_id:016x}"
    except Exception:
        pass
    return None


def configure_root(level: str = "INFO", *, force_format: str | None = None) -> None:
    """
    Wire up root logger to emit JSON lines to stdout when LOG_FORMAT=json,
    plain text otherwise. Safe to call at module import — idempotent.
    """
    fmt = str(force_format or os.environ.get("LOG_FORMAT", "text")).lower()
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_jerumednexus_configured", False):
            return
    handler = logging.StreamHandler()
    if fmt == "json":
        handler.setFormatter(JsonLineFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
    handler._jerumednexus_configured = True
    root.addHandler(handler)
    root.setLevel(level)
