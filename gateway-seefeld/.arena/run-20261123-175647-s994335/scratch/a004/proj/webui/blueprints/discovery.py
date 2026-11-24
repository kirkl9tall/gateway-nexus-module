"""Plug-and-play device discovery endpoints."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.discovery.service import DiscoveryService
from src.security.audit import AuditEvent, audit
from webui.blueprints._helpers import client_ip, csrf_check, require_local, require_role

discovery_bp = Blueprint("discovery", __name__)

_discovery = DiscoveryService()


@discovery_bp.route("/api/devices/discovered", methods=["GET"])
@require_role("viewer")
def api_devices_discovered():
    return jsonify({
        "devices": _discovery.snapshot(),
        "pending": _discovery.pending(),
    })


@discovery_bp.route("/api/devices/discover", methods=["POST"])
@require_role("operator")
def api_devices_discover():
    if not csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    body = request.get_json(silent=True) or {}
    from webui.blueprints._helpers import run_async
    snapshot = run_async(_discovery.scan_once(
        tcp_range=body.get("tcp_range"),
        tcp_ports=body.get("tcp_ports"),
    ))
    return jsonify({"ok": True, "devices": snapshot})


@discovery_bp.route("/api/devices/activate", methods=["POST"])
@require_role("admin")
def api_devices_activate():
    if not csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    body = request.get_json(force=True)
    key = body.get("key")
    device_type = body.get("device_type")
    display_name = body.get("display_name")
    if not key:
        return jsonify({"ok": False, "error": "'key' required"}), 400
    from webui.blueprints._helpers import run_async
    ok = run_async(_discovery.activate(key, device_type=device_type,
                                       display_name=display_name))
    if ok:
        audit(AuditEvent.DEVICE_CONNECTED, ip=client_ip(),
              detail={"key": key, "device_type": device_type,
                      "display_name": display_name})
    return jsonify({"ok": ok})


@discovery_bp.route("/api/devices/notify_added", methods=["POST"])
@require_local
def api_devices_notify_added():
    devnode = request.form.get("dev") or (request.get_json(silent=True) or {}).get("dev", "")
    if not devnode:
        return jsonify({"ok": False, "error": "'dev' required"}), 400
    from webui.blueprints._helpers import run_async
    run_async(_discovery.notify_added(
        f"/dev/{devnode}" if not devnode.startswith("/") else devnode))
    return jsonify({"ok": True})


@discovery_bp.route("/api/devices/notify_removed", methods=["POST", "GET"])
@require_local
def api_devices_notify_removed():
    devnode = request.args.get("dev") or request.form.get("dev", "")
    if not devnode:
        return jsonify({"ok": False, "error": "'dev' required"}), 400
    _discovery.notify_removed(
        f"/dev/{devnode}" if not devnode.startswith("/") else devnode)
    return jsonify({"ok": True})
