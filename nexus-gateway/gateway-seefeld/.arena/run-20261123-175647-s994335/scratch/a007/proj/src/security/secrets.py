"""
Secure credential storage.

Secrets are loaded from (highest priority first):
  1. Environment variables
  2. config/secrets.env  (chmod 600, not committed)
  3. Inline YAML values  (legacy — logs a warning once)
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

log = logging.getLogger("loc200.secrets")

_SECRETS_FILE = Path("config/secrets.env")
_LOADED = False
_FILE_SECRETS: dict[str, str] = {}


def _load_secrets_file() -> None:
    global _LOADED, _FILE_SECRETS
    if _LOADED:
        return
    _LOADED = True
    if not _SECRETS_FILE.exists():
        return
    try:
        for line in _SECRETS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            _FILE_SECRETS[key.strip()] = value.strip().strip('"').strip("'")
    except Exception as exc:
        log.warning("Could not read secrets file: %s", exc)


def get_secret(key: str, yaml_fallback: str | None = None) -> str | None:
    """Resolve a secret by key."""
    env_val = os.environ.get(key)
    if env_val:
        return env_val

    _load_secrets_file()
    if key in _FILE_SECRETS:
        return _FILE_SECRETS[key]

    if yaml_fallback:
        log.warning(
            "Secret %s loaded from gateway.yaml — move to config/secrets.env for production.",
            key,
        )
        return yaml_fallback

    return None


def resolve_target_secrets(target_name: str, fields: dict) -> dict:
    """
    Inject secrets for a PIS target from env/secrets file.

    Naming convention: ``{TARGET}_{FIELD}`` e.g. ``TOMEDO_SFTP_PASS``.
    """
    prefix = re.sub(r"[^A-Z0-9]", "_", target_name.upper())
    resolved = dict(fields)

    secret_map = {
        "sftp_pass": f"{prefix}_SFTP_PASS",
        "sftp_user": f"{prefix}_SFTP_USER",
        "sftp_host": f"{prefix}_SFTP_HOST",
    }
    for field, env_key in secret_map.items():
        if field in resolved and resolved[field]:
            override = get_secret(env_key, yaml_fallback=resolved[field])
            if override:
                resolved[field] = override

    return resolved
