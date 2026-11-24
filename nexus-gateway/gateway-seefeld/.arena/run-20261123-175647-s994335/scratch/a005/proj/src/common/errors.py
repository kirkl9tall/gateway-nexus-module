"""
Typed error taxonomy — every error the gateway can surface has a stable
code (E1xxx = adapter, E2xxx = router/DLQ, E3xxx = target, E4xxx = auth,
E5xxx = config, E9xxx = internal). Codes are stable across MAJOR releases
per the versioning policy — they are documented in docs/API.md and land
verbatim in HL7 error responses, in the Web UI, and in support bundles.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    # ── Adapter / device (E1xxx) ────────────────────────────────────────────
    E1001_DEVICE_TIMEOUT       = "E1001"
    E1002_DEVICE_UNREACHABLE   = "E1002"
    E1003_MALFORMED_FRAME      = "E1003"
    E1004_UNKNOWN_PROTOCOL     = "E1004"
    E1005_SERIAL_PORT_MISSING  = "E1005"
    E1006_CHECKSUM_MISMATCH    = "E1006"
    E1007_ASTM_HANDSHAKE_FAIL  = "E1007"
    E1008_HL7_PARSE_ERROR      = "E1008"
    E1009_UNSUPPORTED_DEVICE   = "E1009"

    # ── Router / DLQ (E2xxx) ────────────────────────────────────────────────
    E2001_BACKPRESSURE_DROP    = "E2001"
    E2002_DLQ_WRITE_FAIL       = "E2002"
    E2003_DLQ_ENCRYPTION_FAIL  = "E2003"
    E2004_DEDUP_HIT            = "E2004"
    E2005_BREAKER_OPEN         = "E2005"

    # ── Target / LIS (E3xxx) ────────────────────────────────────────────────
    E3001_LIS_UNREACHABLE      = "E3001"
    E3002_LIS_REJECTED         = "E3002"
    E3003_LIS_TIMEOUT          = "E3003"
    E3004_MSA_NACK             = "E3004"
    E3005_FHIR_BUNDLE_ERROR    = "E3005"

    # ── Auth (E4xxx) ────────────────────────────────────────────────────────
    E4001_LOGIN_INVALID        = "E4001"
    E4002_TOTP_INVALID         = "E4002"
    E4003_TOKEN_EXPIRED        = "E4003"
    E4004_RBAC_DENIED          = "E4004"
    E4005_OIDC_FAIL            = "E4005"
    E4006_LDAP_UNREACHABLE     = "E4006"

    # ── Config (E5xxx) ──────────────────────────────────────────────────────
    E5001_CONFIG_INVALID       = "E5001"
    E5002_LICENSE_INVALID      = "E5002"
    E5003_LICENSE_EXPIRED      = "E5003"
    E5004_DEVICE_PROFILE_BAD   = "E5004"
    E5005_RETENTION_BAD_VALUE  = "E5005"

    # ── Internal (E9xxx) ────────────────────────────────────────────────────
    E9001_UNEXPECTED           = "E9001"
    E9002_DB_MIGRATION_FAIL    = "E9002"
    E9003_LEADER_LOST          = "E9003"


@dataclass
class GatewayError(Exception):
    """Base exception. Raise this instead of bare Exception."""
    code:    ErrorCode
    message: str
    detail:  dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "error":   self.code.value,
            "message": self.message,
            "detail":  self.detail or {},
        }


# Convenience factories (make raise-sites terse)
def device_timeout(device: str, seconds: float, **extra: Any) -> GatewayError:
    return GatewayError(ErrorCode.E1001_DEVICE_TIMEOUT,
                        f"device {device!r} timed out after {seconds}s",
                        {"device": device, "seconds": seconds, **extra})


def lis_unreachable(target: str, cause: str) -> GatewayError:
    return GatewayError(ErrorCode.E3001_LIS_UNREACHABLE,
                        f"cannot reach LIS {target!r}: {cause}",
                        {"target": target, "cause": cause})


def rbac_denied(user: str, role: str, path: str) -> GatewayError:
    return GatewayError(ErrorCode.E4004_RBAC_DENIED,
                        f"user {user!r} (role={role}) not allowed on {path!r}",
                        {"user": user, "role": role, "path": path})
