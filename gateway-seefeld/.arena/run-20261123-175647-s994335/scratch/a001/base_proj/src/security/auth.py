"""
Web UI authentication with bcrypt password hashing.

Password hash stored in config/webui_password.hash (never plaintext).
Migrates legacy SHA256 / plaintext files on first verify.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets

from src.common.paths import config_dir

log = logging.getLogger("loc200.auth")

# Anchored to install_root() so save_password() works regardless of the
# process' CWD (installer, cron, tests, systemd — all correct).
_HASH_FILE = config_dir() / "webui_password.hash"
_LEGACY_PLAIN_FILE = config_dir() / "webui_password.txt"
_SECRET_KEY_FILE = config_dir() / "webui_secret.key"
MIN_PASSWORD_LEN = 12


def _bcrypt_available() -> bool:
    try:
        import bcrypt  # noqa: F401
        return True
    except ImportError:
        return False


def hash_password(password: str) -> str:
    if _bcrypt_available():
        import bcrypt
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")
    # Fallback if bcrypt not installed (dev only)
    log.warning("bcrypt not installed — using SHA256 fallback (NOT for production)")
    return "sha256:" + hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith("sha256:"):
        return hashlib.sha256(password.encode()).hexdigest() == stored_hash[7:]
    if stored_hash.startswith("$2"):
        import bcrypt
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("ascii"))
        except Exception:
            return False
    # Legacy: raw sha256 hex
    return hashlib.sha256(password.encode()).hexdigest() == stored_hash


def load_password_hash() -> str | None:
    if _HASH_FILE.exists():
        return _HASH_FILE.read_text(encoding="utf-8").strip()

    # Migrate legacy plaintext
    if _LEGACY_PLAIN_FILE.exists():
        plain = _LEGACY_PLAIN_FILE.read_text(encoding="utf-8").strip()
        if plain:
            save_password(plain)
            _LEGACY_PLAIN_FILE.unlink(missing_ok=True)
            log.info("Migrated web UI password from plaintext to bcrypt hash.")
            return load_password_hash()

    env_pw = os.environ.get("GATEWAY_WEBUI_PASSWORD")
    if env_pw:
        save_password(env_pw)
        return load_password_hash()

    return None


def save_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LEN} characters")
    _HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HASH_FILE.write_text(hash_password(password), encoding="utf-8")
    try:
        _HASH_FILE.chmod(0o600)
    except OSError:
        pass


def is_setup_required() -> bool:
    return load_password_hash() is None


def validate_login(password: str) -> bool:
    stored = load_password_hash()
    if not stored:
        return False
    return verify_password(password, stored)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def get_or_create_secret_key() -> bytes:
    """
    Return a persistent Flask secret key.

    Priority:
      1. env WEBUI_SECRET (raw string)
      2. config/webui_secret.key file
      3. auto-generated 64-byte key, saved to disk with mode 600
    """
    env_val = os.environ.get("WEBUI_SECRET")
    if env_val:
        return env_val.encode("utf-8")

    if _SECRET_KEY_FILE.exists():
        try:
            data = _SECRET_KEY_FILE.read_bytes().strip()
            if data:
                return data
        except OSError as exc:
            log.warning("Cannot read secret key file: %s", exc)

    key = secrets.token_bytes(64)
    try:
        _SECRET_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SECRET_KEY_FILE.write_bytes(key)
        try:
            _SECRET_KEY_FILE.chmod(0o600)
        except OSError:
            pass
        log.info("Generated new persistent web UI secret key.")
    except OSError as exc:
        log.warning("Could not persist secret key (%s) — using in-memory key.", exc)
    return key
