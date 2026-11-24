"""
Liveness vs readiness probes — Kubernetes-style, but useful on plain
systemd too.

  /livez  — the process is running and the event loop is not stuck.
            NEVER checks external deps. Kills only true process crashes.
  /readyz — every enabled device reader is connected AND at least one
            LIS target is reachable AND DLQ is not stalled.

External load balancers should route traffic based on /readyz, but
systemd/kubelet should restart based on /livez.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def livez() -> tuple[int, dict[str, Any]]:
    """Cheap: only proves the loop turns."""
    return 200, {"status": "alive", "ts": time.time()}


def readyz() -> tuple[int, dict[str, Any]]:
    """Expensive: aggregate state of every subsystem."""
    reasons: list[str] = []
    detail: dict[str, Any] = {"ts": time.time()}

    # 1) Device readers connected
    health_path = Path("logs/health.json")
    if health_path.exists():
        try:
            import json
            health = json.loads(health_path.read_text())
            devices = health.get("devices", {})
            detail["devices"] = devices
            offline = [d for d, s in devices.items() if s.get("state") not in ("ok", "connected")]
            if offline:
                reasons.append(f"devices offline: {','.join(offline)}")
        except Exception as exc:
            reasons.append(f"health.json unreadable: {exc}")

    # 2) Circuit breakers open
    breakers = Path("logs/breakers.json")
    if breakers.exists():
        try:
            import json
            b = json.loads(breakers.read_text())
            open_targets = [k for k, v in b.items() if v.get("state") == "open"]
            if open_targets:
                reasons.append(f"breakers open: {','.join(open_targets)}")
            detail["breakers"] = b
        except Exception:
            pass

    # 3) DLQ backlog
    dlq = Path("logs/dead_letter")
    if dlq.exists():
        files = list(dlq.glob("*.meta.json"))
        detail["dlq_backlog"] = len(files)
        if len(files) > 500:
            reasons.append(f"DLQ backlog {len(files)} > 500")

    if reasons:
        return 503, {"status": "unready", "reasons": reasons, **detail}
    return 200, {"status": "ready", **detail}
