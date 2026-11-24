"""
Multi-user auth with roles.

Users live in config/webui_users.json (mode 600):

    {
      "users": [
        {"name": "admin",    "role": "admin",    "hash": "$2b$12$..."},
        {"name": "operator", "role": "operator", "hash": "$2b$12$..."},
        {"name": "nurse",    "role": "viewer",   "hash": "$2b$12$..."}
      ]
    }

Legacy single-admin (config/webui_password.hash) is auto-migrated to a
user named "admin" with role "admin" on first read.

Roles:
  * viewer   -- can read dashboard, status, logs. Cannot change anything.
  * operator -- viewer + start/stop service + acknowledge DLQ items.
  * admin    -- everything (config, users, license, updates).
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from src.common.paths import config_dir
from src.security.auth import (
    MIN_PASSWORD_LEN,
    hash_password,
    load_password_hash,
    verify_password,
)

log = logging.getLogger("loc200.roles")

_USERS_FILE = config_dir() / "webui_users.json"
_ROLES = ("viewer", "operator", "admin")

# Which role can call which endpoint kind.
_ROLE_RANK = {"viewer": 0, "operator": 1, "admin": 2}


def _load() -> dict:
    if _USERS_FILE.exists():
        try:
            data = json.loads(_USERS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("users"), list):
                return data
        except Exception as exc:
            log.warning("users file unreadable: %s", exc)
    # Legacy migration: single admin from webui_password.hash
    legacy = load_password_hash()
    if legacy:
        return {"users": [{"name": "admin", "role": "admin", "hash": legacy}]}
    return {"users": []}


def _save(data: dict) -> None:
    _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _USERS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, _USERS_FILE)
    try:
        _USERS_FILE.chmod(0o600)
    except OSError:
        pass


def list_users() -> list[dict]:
    return [{"name": u["name"], "role": u["role"]} for u in _load().get("users", [])]


def user_exists(name: str) -> bool:
    return any(u["name"] == name for u in _load().get("users", []))


def validate_login(name: str, password: str) -> Optional[str]:
    """Return the role on success, None otherwise."""
    if not name or not password:
        return None
    for u in _load().get("users", []):
        if u.get("name") == name and verify_password(password, u.get("hash", "")):
            role = u.get("role", "viewer")
            if role not in _ROLES:
                role = "viewer"
            return role
    return None


def _validate_name(name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,32}", name or ""):
        raise ValueError("Username: 2-32 chars, letters/digits/./_/-")


def create_user(name: str, password: str, role: str) -> None:
    _validate_name(name)
    if role not in _ROLES:
        raise ValueError(f"Role must be one of {_ROLES}")
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LEN} chars")
    data = _load()
    if any(u["name"] == name for u in data["users"]):
        raise ValueError(f"User {name!r} already exists")
    data["users"].append({"name": name, "role": role,
                          "hash": hash_password(password)})
    _save(data)


def update_password(name: str, new_password: str) -> None:
    if len(new_password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LEN} chars")
    data = _load()
    for u in data["users"]:
        if u["name"] == name:
            u["hash"] = hash_password(new_password)
            _save(data)
            return
    raise ValueError(f"User {name!r} not found")


def delete_user(name: str) -> None:
    data = _load()
    before = len(data["users"])
    data["users"] = [u for u in data["users"] if u["name"] != name]
    if len(data["users"]) == before:
        raise ValueError(f"User {name!r} not found")
    if not any(u["role"] == "admin" for u in data["users"]):
        raise ValueError("Cannot delete the last admin")
    _save(data)


def set_role(name: str, role: str) -> None:
    if role not in _ROLES:
        raise ValueError(f"Role must be one of {_ROLES}")
    data = _load()
    for u in data["users"]:
        if u["name"] == name:
            u["role"] = role
            _save(data)
            return
    raise ValueError(f"User {name!r} not found")


def is_setup_required() -> bool:
    return not _load().get("users")


def require_role(current_role: str, needed: str) -> bool:
    return _ROLE_RANK.get(current_role, -1) >= _ROLE_RANK.get(needed, 0)
