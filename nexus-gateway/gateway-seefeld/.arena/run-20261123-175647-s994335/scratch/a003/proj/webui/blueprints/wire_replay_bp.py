"""Web UI blueprint for time-travel wire replay."""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from src.common import wire_replay
from webui.blueprints._helpers import require_role

wire_replay_bp = Blueprint("wire_replay", __name__)


@wire_replay_bp.route("/replay", methods=["GET"])
@require_role("admin")
def replay_index():
    device = request.args.get("device", "").strip() or None
    captures = wire_replay.list_captures(device=device, limit=100)
    return render_template("wire_replay.html", captures=captures, device=device or "")


@wire_replay_bp.route("/api/replay/<path:filename>", methods=["POST"])
@require_role("operator")
def replay_capture(filename: str):
    return jsonify(wire_replay.replay(filename))
