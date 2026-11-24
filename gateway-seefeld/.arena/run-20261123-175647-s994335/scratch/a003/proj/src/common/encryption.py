"""
At-rest encryption for sensitive files (DLQ HL7 bodies).

Uses Fernet (AES-128-CBC + HMAC-SHA-256) from the `cryptography` package.
Key stored at config/dlq_key (32 bytes urlsafe-b64, mode 600, owned by
gateway user).

If cryptography is not installed OR encryption disabled in config,
falls back to plaintext (with a log warning).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("loc200.encryption")

_KEY_FILE = Path("config/dlq_key")


def _load_or_create_key() -> Optional[bytes]:
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        log.warning("cryptography not installed -- DLQ stored in plaintext")
        return None

    if _KEY_FILE.exists():
        try:
            data = _KEY_FILE.read_bytes().strip()
            if len(data) >= 44:
                return data
        except OSError as exc:
            log.warning("cannot read %s: %s", _KEY_FILE, exc)

    # Generate fresh key
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    try:
        _KEY_FILE.chmod(0o600)
    except OSError:
        pass
    log.info("Generated new DLQ encryption key at %s", _KEY_FILE)
    return key


_key: Optional[bytes] = None


def _get_fernet() -> Optional["Fernet"]:  # type: ignore[name-defined]  # noqa: F821
    global _key
    if _key is None:
        _key = _load_or_create_key()
    if _key is None:
        return None
    from cryptography.fernet import Fernet
    return Fernet(_key)


def encrypt_bytes(plaintext: bytes) -> bytes:
    """Encrypt bytes. Returns ciphertext prefixed with b'FRNT1' magic."""
    f = _get_fernet()
    if f is None:
        return plaintext
    return b"FRNT1" + bytes(f.encrypt(plaintext))


def decrypt_bytes(data: bytes) -> bytes:
    """Decrypt bytes if they start with FRNT1 magic. Otherwise return as-is."""
    if not data.startswith(b"FRNT1"):
        return data
    f = _get_fernet()
    if f is None:
        raise RuntimeError("Encrypted data present but cryptography not installed")
    return bytes(f.decrypt(data[5:]))


def is_available() -> bool:
    return _get_fernet() is not None


def rotate_key() -> None:
    """
    Generate a new key. WARNING: all previously-encrypted files become
    unreadable unless re-encrypted with the new key.

    Usage: run only after archiving/re-encrypting all existing DLQ.
    """
    global _key
    if _KEY_FILE.exists():
        backup = _KEY_FILE.with_suffix(".key.old")
        _KEY_FILE.rename(backup)
        log.warning("Old key archived to %s", backup)
    _key = None
    _load_or_create_key()
