"""
Live topology map — devices → gateway → LIS with animated data-flow dots.

Uses Server-Sent Events (SSE) so we don't need a websocket lib as
runtime dep. Every 1 s we push a snapshot; the browser SVG animates dots
along the path when a new dispatch is detected.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, render_template

from webui.blueprints._helpers import require_role

topology_bp = Blueprint("topology", __name__)


def _snapshot() -> dict[str, Any]:
    """Return one snapshot of the topology state (devices, gateway, targets)."""
    data: dict[str, Any] = {"ts": time.time(), "devices": [], "targets": [], "flows": []}

    # Devices
    try:
        health = json.loads(Path("logs/health.json").read_text(encoding="utf-8"))
        for name, info in (health.get("devices") or {}).items():
            data["devices"].append({
                "name":  name,
                "state": info.get("state", "unknown"),
                "last_seen": info.get("last_seen"),
            })
    except Exception:
        pass

    # Targets
    try:
        breakers = json.loads(Path("logs/breakers.json").read_text(encoding="utf-8"))
        for name, info in breakers.items():
            data["targets"].append({
                "name":  name,
                "state": info.get("state", "closed"),
                "p95_ms": info.get("p95_ms", 0),
            })
    except Exception:
        pass

    # Recent flows (last 5s of dispatches)
    try:
        status = json.loads(Path("logs/status.json").read_text(encoding="utf-8"))
        # Il filtro era calcolato e mai applicato, e la cronologia non aveva
        # nemmeno un campo `ts`: la pagina mostrava come "in transito" flussi
        # vecchi di ore. Ora il tempo c'e' e il filtro si applica davvero.
        cutoff = time.time() - 5
        for entry in (status.get("history") or [])[-20:]:
            ts = entry.get("ts") or 0
            if ts < cutoff:
                continue
            # I destinatari raggiunti stanno in `succeeded`: `target` non e'
            # mai esistito nella voce, quindi compariva sempre "?".
            for destinatario in (entry.get("succeeded") or ["?"]):
                data["flows"].append({
                    "device":  entry.get("device", "?"),
                    "target":  destinatario,
                    "ts":      ts,
                    "status":  entry.get("status", "ok"),
                })
    except Exception:
        pass

    return data


@topology_bp.route("/topology", methods=["GET"])
@require_role("admin")
def topology_page():
    return render_template("topology.html")


@topology_bp.route("/api/topology/stream", methods=["GET"])
@require_role("viewer")
def topology_stream():
    def generate():
        while True:
            snap = _snapshot()
            yield f"data: {json.dumps(snap)}\n\n"
            time.sleep(1.0)

    return Response(generate(), mimetype="text/event-stream",
                     headers={"Cache-Control": "no-cache",
                              "X-Accel-Buffering": "no"})


@topology_bp.route("/api/topology/snapshot", methods=["GET"])
@require_role("viewer")
def topology_snapshot():
    from flask import jsonify
    return jsonify(_snapshot())
