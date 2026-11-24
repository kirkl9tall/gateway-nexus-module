"""
2FA / TOTP for admin accounts.

Uses pyotp (optional dep) + qrcode for enrollment.
Each user has an optional `totp_secret` in webui_users.json.

Enrollment flow:
  1. POST /api/users/<name>/totp/enroll  -> returns provisioning URI + QR
  2. User scans with Authenticator app (Google/Microsoft/Aegis...)
  3. User posts back the first 6-digit code to confirm
  4. Secret stored; next login requires the OTP
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from src.common.paths import config_dir

log = logging.getLogger("loc200.totp")

_USERS_FILE = config_dir() / "webui_users.json"
_ISSUER = "JerumedNexus Gateway"


def _load() -> dict:
    if not _USERS_FILE.exists():
        return {"users": []}
    try:
        return json.loads(_USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"users": []}


def _save(data: dict) -> None:
    import os as _os
    _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _USERS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _os.replace(tmp, _USERS_FILE)
    try:
        _USERS_FILE.chmod(0o600)
    except OSError:
        pass


def enroll(name: str) -> Optional[dict]:
    """
    Generate a TOTP secret for `name` and return provisioning info.
    Secret is stored `pending: true` until the user confirms with a code.
    """
    try:
        import pyotp
    except ImportError:
        log.error("pyotp not installed: pip install pyotp")
        return None

    data = _load()
    user = next((u for u in data.get("users", []) if u.get("name") == name), None)
    if not user:
        return None
    secret = pyotp.random_base32()
    user["totp_secret_pending"] = secret
    _save(data)
    uri = pyotp.TOTP(secret).provisioning_uri(name=name, issuer_name=_ISSUER)
    return {"secret": secret, "provisioning_uri": uri, "issuer": _ISSUER}


def confirm(name: str, code: str) -> bool:
    """Verify the first OTP code; on success promote pending secret to active."""
    try:
        import pyotp
    except ImportError:
        return False
    data = _load()
    user = next((u for u in data.get("users", []) if u.get("name") == name), None)
    if not user:
        return False
    pending = user.get("totp_secret_pending")
    if not pending:
        return False
    if pyotp.TOTP(pending).verify(code, valid_window=1):
        user["totp_secret"] = pending
        user.pop("totp_secret_pending", None)
        _save(data)
        log.info("TOTP enrolled for user %s", name)
        return True
    return False


def disable(name: str) -> bool:
    data = _load()
    user = next((u for u in data.get("users", []) if u.get("name") == name), None)
    if not user:
        return False
    user.pop("totp_secret", None)
    user.pop("totp_secret_pending", None)
    _save(data)
    return True


def has_totp(name: str) -> bool:
    data = _load()
    user = next((u for u in data.get("users", []) if u.get("name") == name), None)
    return bool(user and user.get("totp_secret"))


def verify_login(name: str, code: str) -> bool:
    """Verify the code during login."""
    try:
        import pyotp
    except ImportError:
        return False
    data = _load()
    user = next((u for u in data.get("users", []) if u.get("name") == name), None)
    if not user or not user.get("totp_secret"):
        return False
    return pyotp.TOTP(user["totp_secret"]).verify(code, valid_window=1)


def qr_data_uri(uri: str) -> Optional[str]:
    """Return a data: URI PNG of the QR code. Requires `qrcode[pil]`."""
    try:
        import base64
        import io
        import qrcode
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        return None
