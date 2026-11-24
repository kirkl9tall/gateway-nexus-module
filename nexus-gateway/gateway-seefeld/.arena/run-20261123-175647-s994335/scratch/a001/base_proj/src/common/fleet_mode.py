"""
Multi-tenancy fleet mode — one Pi handles N isolated clinic tenants.

Each tenant gets:
  * separate config directory     config/tenants/<tenant_id>/
  * separate history.db           logs/tenants/<tenant_id>/history.db
  * separate DLQ                  logs/tenants/<tenant_id>/dead_letter/
  * separate audit trail          logs/tenants/<tenant_id>/audit.jsonl
  * tenant-scoped Web UI URL      /t/<tenant_id>/dashboard

Enabled by setting in gateway.yaml:
    fleet_mode:
      enabled: true
      tenants:
        - {id: "clinic-zurich-01",   name: "Praxis Zurich A"}
        - {id: "clinic-luzern-02",   name: "Praxis Luzern B"}
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("loc200.fleet_mode")


@dataclass(frozen=True)
class Tenant:
    id:            str
    display_name:  str
    config_dir:    Path
    log_dir:       Path


_TENANTS: dict[str, Tenant] = {}
_ENABLED: bool = False


def is_enabled() -> bool:
    return _ENABLED


def get_tenant(tenant_id: str) -> Tenant | None:
    return _TENANTS.get(tenant_id)


def list_tenants() -> list[Tenant]:
    return list(_TENANTS.values())


def configure(cfg: dict | None) -> None:
    """Called at boot with the `fleet_mode` block of gateway.yaml."""
    global _ENABLED
    if not cfg or not cfg.get("enabled"):
        _ENABLED = False
        return
    _ENABLED = True
    for tdef in cfg.get("tenants", []):
        tid = tdef["id"]
        cfg_dir = Path("config/tenants") / tid
        log_dir = Path("logs/tenants") / tid
        cfg_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "dead_letter").mkdir(exist_ok=True)
        _TENANTS[tid] = Tenant(
            id=tid,
            display_name=tdef.get("name", tid),
            config_dir=cfg_dir,
            log_dir=log_dir,
        )
    log.info("Fleet mode: %d tenants configured — %s",
             len(_TENANTS), ", ".join(_TENANTS))


def with_tenant_context(tenant_id: str):
    """
    Context manager that redirects file paths to a tenant's subdirectory.
    Used by adapters to isolate history/audit/DLQ per clinic.
    """
    from contextlib import contextmanager
    t = get_tenant(tenant_id)

    @contextmanager
    def _ctx():
        if t is None:
            yield None
            return
        yield t

    return _ctx()
