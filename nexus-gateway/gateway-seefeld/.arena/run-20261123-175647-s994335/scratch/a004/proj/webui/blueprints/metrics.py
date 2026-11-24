"""Prometheus /metrics endpoint."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from flask import Blueprint

from webui.blueprints._helpers import client_ip

metrics_bp = Blueprint("metrics", __name__)

_STATUS_F = Path("logs/status.json")


def _read_status():
    if _STATUS_F.exists():
        try:
            return json.loads(_STATUS_F.read_text())
        except Exception:
            pass
    return {}


def _service_status() -> str:
    import subprocess
    for svc in ("jerumednexus-gateway", "loc200-gateway"):  # legacy fallback
        try:
            r = subprocess.run(["systemctl", "is-active", svc],
                               capture_output=True, text=True, timeout=5)
            s = r.stdout.strip()
            if s and s in ("active", "inactive", "failed"):
                return s
        except Exception:
            continue
    return "unknown"


@metrics_bp.route("/metrics", methods=["GET"])
def metrics():
    public = os.environ.get("WEBUI_METRICS_PUBLIC", "").lower() in ("1", "true", "yes")
    if not public and client_ip() not in ("127.0.0.1", "::1", "localhost"):
        return "metrics restricted to localhost (set WEBUI_METRICS_PUBLIC=1 to open)", 403

    st = _read_status()
    svc = _service_status()
    lines: list[str] = []

    def _add(name: str, help_text: str, mtype: str, value, labels=None):
        lines.append(f"# HELP jerumednexus_{name} {help_text}")
        lines.append(f"# TYPE jerumednexus_{name} {mtype}")
        if labels:
            lab = ",".join(f'{k}="{v}"' for k, v in labels.items())
            lines.append(f"jerumednexus_{name}{{{lab}}} {value}")
        else:
            lines.append(f"jerumednexus_{name} {value}")

    _add("up", "1 if the gateway systemd service is active", "gauge",
         1 if svc == "active" else 0)
    _add("running", "1 if the gateway internal loop reports running", "gauge",
         1 if st.get("running") else 0)
    _add("uptime_seconds", "Gateway uptime in seconds since last start", "gauge",
         int(st.get("uptime_seconds", 0)))
    _add("results_total", "Total HL7 messages dispatched since start", "counter",
         int(st.get("results_total", 0)))
    _add("results_today", "HL7 messages dispatched today", "gauge",
         int(st.get("results_today", 0)))
    _add("errors_today", "Delivery errors observed today", "gauge",
         int(st.get("errors_today", 0)))
    _add("queue_size", "Current gateway queue depth", "gauge",
         int(st.get("queue_size", 0)))
    _add("queue_maxsize", "Configured maximum queue size", "gauge",
         int(st.get("queue_maxsize", 0)))
    _add("queue_full_events", "Times the queue was full since last scrape", "counter",
         int(st.get("queue_full_events", 0)))

    for name, ts in (st.get("last_seen") or {}).items():
        try:
            dt = datetime.fromisoformat(ts)
            _add("device_last_seen_seconds",
                 "Unix timestamp of last frame received from device", "gauge",
                 int(dt.timestamp()), labels={"device": name})
        except Exception:
            continue
    for t in (st.get("targets") or []):
        _add("target_enabled", "1 if target is enabled in config", "gauge",
             1 if t.get("enabled") else 0,
             labels={"name": t.get("name", "?"), "type": t.get("type", "?")})
    for b in (st.get("breakers") or []):
        _add("target_breaker_state",
             "0=closed 1=half-open 2=open", "gauge",
             {"closed": 0, "half-open": 1, "open": 2}.get(
                 b.get("breaker", {}).get("state", "closed"), 0),
             labels={"name": b.get("name", "?")})

    body = "\n".join(lines) + "\n"
    return body, 200, {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"}
