"""User management (admin only)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from src.security import roles as _roles
from src.security import totp as _totp
from src.security.audit import AuditEvent, audit
from webui.blueprints._helpers import client_ip, csrf_check, require_role

users_bp = Blueprint("users", __name__)


def _self_or_admin(name: str) -> bool:
    """A user may manage their own TOTP; admins may manage anyone's."""
    return session.get("username") == name or session.get("role") == "admin"


@users_bp.route("/api/users", methods=["GET"])
@require_role("admin")
def api_users_list():
    return jsonify({
        "users":   _roles.list_users(),
        "current": {"name": session.get("username"), "role": session.get("role")},
    })


@users_bp.route("/api/users", methods=["POST"])
@require_role("admin")
def api_users_create():
    if not csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    body = request.get_json(force=True)
    try:
        _roles.create_user(
            (body.get("name") or "").strip(),
            body.get("password", ""),
            (body.get("role") or "viewer").strip(),
        )
        audit(AuditEvent.PASSWORD_CHANGE, actor=session.get("username", "?"),
              ip=client_ip(), detail={"created": body.get("name")})
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@users_bp.route("/api/users/<name>", methods=["DELETE"])
@require_role("admin")
def api_users_delete(name: str):
    if not csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    if name == session.get("username"):
        return jsonify({"ok": False, "error": "cannot delete yourself"}), 400
    try:
        _roles.delete_user(name)
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@users_bp.route("/api/users/<name>/role", methods=["POST"])
@require_role("admin")
def api_users_role(name: str):
    if not csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    role = (request.get_json(force=True).get("role") or "").strip()
    try:
        _roles.set_role(name, role)
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


# ── Admin password reset ────────────────────────────────────────────────────
# Lets an admin reset another user's password from the WebUI, without the
# CLI dance (`python main.py --reset-password`). The current user cannot
# reset their own password here — they use /settings for that, which
# requires knowing the old password.

@users_bp.route("/api/users/<name>/password", methods=["POST"])
@require_role("admin")
def api_users_reset_password(name: str):
    if not csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    body = request.get_json(force=True, silent=True) or {}
    new_pw = body.get("password", "")
    if name == session.get("username"):
        return jsonify({"ok": False,
                        "error": "Usa /settings per cambiare la tua password"}), 400
    try:
        _roles.update_password(name, new_pw)
        audit(AuditEvent.PASSWORD_CHANGE, actor=session.get("username", "?"),
              ip=client_ip(), detail={"reset_for": name})
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


# ── TOTP (2FA) endpoints ────────────────────────────────────────────────────

@users_bp.route("/api/users/<name>/totp/enroll", methods=["POST"])
def api_totp_enroll(name: str):
    if not _self_or_admin(name):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    if not csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    info = _totp.enroll(name)
    if info is None:
        return jsonify({"ok": False,
                        "error": "TOTP non disponibile (pyotp mancante o utente inesistente)"}), 400
    info["qr"] = _totp.qr_data_uri(info["provisioning_uri"])
    audit(AuditEvent.PASSWORD_CHANGE, actor=session.get("username", "?"),
          ip=client_ip(), detail={"totp_enroll": name})
    return jsonify({"ok": True, **info})


@users_bp.route("/api/users/<name>/totp/verify", methods=["POST"])
def api_totp_verify(name: str):
    if not _self_or_admin(name):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    if not csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    code = (request.get_json(force=True, silent=True) or {}).get("code", "").strip()
    if _totp.confirm(name, code):
        audit(AuditEvent.PASSWORD_CHANGE, actor=session.get("username", "?"),
              ip=client_ip(), detail={"totp_confirmed": name})
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Codice OTP non valido"}), 400


@users_bp.route("/api/users/<name>/totp/disable", methods=["POST"])
def api_totp_disable(name: str):
    if not _self_or_admin(name):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    if not csrf_check():
        return jsonify({"ok": False, "error": "CSRF token invalido"}), 400
    if _totp.disable(name):
        audit(AuditEvent.PASSWORD_CHANGE, actor=session.get("username", "?"),
              ip=client_ip(), detail={"totp_disabled": name})
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Utente non trovato"}), 404


@users_bp.route("/api/users/<name>/totp/status", methods=["GET"])
def api_totp_status(name: str):
    if not _self_or_admin(name):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return jsonify({"ok": True, "enabled": _totp.has_totp(name)})
