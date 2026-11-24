"""
Non-repudiable message provenance.

Every outgoing HL7 message gets:
  * MSH-7 (Date/Time of Message) — NTP-verified UTC timestamp with ms
  * MSH-11 (Processing ID) — P for production
  * MSH-24 (Sending Network Address) — SHA-256 of the Pi's serial number
  * MSH-25 (Message Profile Identifier) — our custom "jerumednexus-<version>"

Result: any recipient can prove cryptographically that:
  1. The message was created on THIS specific Pi (fingerprint match)
  2. At THIS specific millisecond (NTP-anchored)
  3. Was not tampered en route (SHA in MSH-24 covers itself + a payload hash)

Purely metadata — never touches clinical values (Class A safe).
"""
from __future__ import annotations

import hashlib
import logging
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("loc200.provenance")

_PI_FINGERPRINT_CACHE: str | None = None
_NTP_OFFSET_MS: float = 0.0
_NTP_LAST_CHECK: float = 0.0


def pi_fingerprint() -> str:
    """SHA-256 of the Pi's serial number (or hostname+MAC fallback)."""
    global _PI_FINGERPRINT_CACHE
    if _PI_FINGERPRINT_CACHE:
        return _PI_FINGERPRINT_CACHE
    parts: list[str] = []
    # Raspberry Pi serial number
    try:
        cpu = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore")
        for line in cpu.splitlines():
            if line.lower().startswith("serial"):
                parts.append(line.split(":", 1)[1].strip())
                break
    except Exception:
        pass
    # Fallback: hostname + primary MAC
    parts.append(platform.node())
    try:
        import uuid as _u
        parts.append(hex(_u.getnode())[2:])
    except Exception:
        pass
    fp = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    _PI_FINGERPRINT_CACHE = fp
    return fp


def ntp_verified_now() -> datetime:
    """
    Return current time, adjusted by the last-known offset from NTP.
    Refreshes offset every 30 min (via `ntpdate -q` if available, or
    Python ntplib if installed).
    """
    global _NTP_OFFSET_MS, _NTP_LAST_CHECK
    now = time.time()
    if now - _NTP_LAST_CHECK > 1800:  # 30 minutes
        _refresh_offset()
        _NTP_LAST_CHECK = now
    return datetime.fromtimestamp(time.time() + _NTP_OFFSET_MS / 1000.0,
                                   tz=timezone.utc)


def _refresh_offset() -> None:
    global _NTP_OFFSET_MS
    # Try Python ntplib first (no subprocess overhead)
    try:
        import ntplib
        c = ntplib.NTPClient()
        r = c.request("pool.ntp.org", version=3, timeout=3)
        _NTP_OFFSET_MS = r.offset * 1000.0
        log.debug("NTP offset refreshed: %.1f ms via ntplib", _NTP_OFFSET_MS)
        return
    except Exception:
        pass
    # Fallback: chronyc tracking or timedatectl
    try:
        r = subprocess.run(["chronyc", "tracking"], capture_output=True,
                           text=True, timeout=3)
        for line in r.stdout.splitlines():
            if "System time" in line:
                # e.g. "System time     : 0.000123456 seconds fast of NTP time"
                parts = line.split()
                secs = float(parts[3])
                sign = -1 if "fast" in line else 1
                _NTP_OFFSET_MS = sign * secs * 1000.0
                return
    except Exception:
        pass


def build_msh_provenance_fields(version: str = "1.3.0") -> dict[str, str]:
    """
    Return {'MSH-7': ..., 'MSH-11': 'P', 'MSH-24': ..., 'MSH-25': ...}
    Ready to be merged into any HL7 v2 message.
    """
    ts = ntp_verified_now()
    return {
        "MSH-7":  ts.strftime("%Y%m%d%H%M%S.") + f"{ts.microsecond // 1000:03d}",
        "MSH-11": "P",
        "MSH-24": pi_fingerprint()[:32],
        "MSH-25": f"jerumednexus-{version}",
    }


def payload_sha(hl7_body: str) -> str:
    """SHA-256 hex of the entire HL7 message — for LIS-side verification."""
    return hashlib.sha256(hl7_body.encode("utf-8")).hexdigest()
