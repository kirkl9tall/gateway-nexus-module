"""
QR code onboarding — every device profile page renders a QR that encodes
a signed URL like:

    https://<pi-ip>:8088/verify/<device_id>?token=<hmac>

Scanned from the technician's phone → opens the device verify page
filtered on that device → shows connectivity + first-frame status.

The QR is generated on-the-fly via `qrcode` (pure Python, no runtime dep
on external services). If not installed, an SVG "install qrcode package"
placeholder is shown instead.
"""
from __future__ import annotations

import hmac
import hashlib
import io
import socket
import time

from flask import Blueprint, Response, current_app, jsonify, request

from webui.blueprints._helpers import require_role

qr_bp = Blueprint("qr", __name__)


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return request.host.split(":")[0] or "127.0.0.1"


def _sign(device_id: str, secret: bytes, ttl_s: int = 3600) -> tuple[str, str]:
    exp = int(time.time()) + ttl_s
    payload = f"{device_id}:{exp}"
    sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    return payload, sig


def _verify(payload: str, sig: str, secret: bytes) -> bool:
    try:
        device_id, exp_str = payload.split(":", 1)
        if int(exp_str) < time.time():
            return False
        expected = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False


def _get_secret() -> bytes:
    """Reuse Flask's own secret_key — always present."""
    return (current_app.secret_key or b"changeme").encode() \
        if isinstance(current_app.secret_key, str) else (current_app.secret_key or b"changeme")


@qr_bp.route("/api/device/<device_id>/qr.svg", methods=["GET"])
@require_role("operator")
def api_qr(device_id: str):
    """Return an SVG QR code image for the device onboarding URL."""
    payload, sig = _sign(device_id, _get_secret())
    host = _lan_ip()
    # Match whatever scheme/port the operator hit us on; otherwise the QR
    # points at a port nothing is bound to.
    scheme = request.scheme or "http"
    try:
        port = int(request.host.split(":")[-1]) if ":" in (request.host or "") else \
               (443 if scheme == "https" else 80)
    except ValueError:
        port = 8443 if scheme == "https" else 8080
    default_port = 443 if scheme == "https" else 80
    port_part = "" if port == default_port else f":{port}"
    url = f"{scheme}://{host}{port_part}/onboard/{device_id}?p={payload}&s={sig}"
    try:
        import qrcode
        import qrcode.image.svg
        img = qrcode.make(url, image_factory=qrcode.image.svg.SvgImage,
                          box_size=8, border=2)
        buf = io.BytesIO()
        img.save(buf)
        return Response(buf.getvalue(), mimetype="image/svg+xml")
    except ImportError:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
            '<rect width="100%" height="100%" fill="#eef"/>'
            f'<text x="10" y="90" font-size="12">QR non disponibile.</text>'
            f'<text x="10" y="110" font-size="10">pip install qrcode[pil]</text>'
            f'<text x="10" y="130" font-size="8">{url[:32]}...</text>'
            "</svg>"
        )
        return Response(svg, mimetype="image/svg+xml")


@qr_bp.route("/onboard/<device_id>", methods=["GET"])
def onboard(device_id: str):
    """Landing page opened by phone after scanning the QR."""
    from flask import render_template
    payload = request.args.get("p", "")
    sig = request.args.get("s", "")
    if not _verify(payload, sig, _get_secret()):
        return jsonify({"ok": False, "error": "signature invalid or expired",
                        "code": "E4003_TOKEN_EXPIRED"}), 403
    try:
        import json
        from pathlib import Path
        health = json.loads(Path("logs/health.json").read_text(encoding="utf-8"))
        dev_status = health.get("devices", {}).get(device_id, {})
    except Exception:
        dev_status = {}
    return render_template("onboard.html",
                            device_id=device_id,
                            status=dev_status.get("state", "waiting"))
