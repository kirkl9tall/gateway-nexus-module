"""Fleet Console blueprint."""
from __future__ import annotations

from flask import Blueprint, render_template

from src.common import fleet_mode
from webui.blueprints._helpers import require_role

fleet_bp = Blueprint("fleet", __name__)


@fleet_bp.route("/fleet", methods=["GET"])
@require_role("admin")
def fleet_console():
    return render_template("fleet_console.html",
                            enabled=fleet_mode.is_enabled(),
                            tenants=fleet_mode.list_tenants())
