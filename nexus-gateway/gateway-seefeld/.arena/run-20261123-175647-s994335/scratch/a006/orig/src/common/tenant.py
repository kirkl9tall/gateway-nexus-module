"""
Multi-tenancy scaffolding.

Single-tenant (default) = 1 gateway serves 1 clinic. Tenant id = "default".
Multi-tenant             = 1 gateway serves N clinics, isolated by tenant id.

Design (opt-in, backward compat):
  * config/tenants/<tenant_id>.yaml declares a tenant (name, contacts, quota)
  * URL prefix `/t/<tenant_id>/...` selects the tenant on the Web UI
  * `X-Tenant-Id` header on API calls
  * Audit + history + DLQ paths get scoped to `logs/<tenant_id>/...`
  * Users have optional `tenant_id` -- global admins keep no scope

For the v1.2 release we ship the plumbing; enabling requires an intentional
config change. Existing single-tenant deployments are unaffected.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

log = logging.getLogger("loc200.tenant")

_TENANTS_DIR = Path("config/tenants")
DEFAULT_TENANT = "default"


def is_multitenant() -> bool:
    return os.environ.get("MULTITENANT", "").lower() in ("1", "true", "yes") \
        or _TENANTS_DIR.exists() and any(_TENANTS_DIR.glob("*.yaml"))


def list_tenants() -> List[Dict[str, Any]]:
    if not _TENANTS_DIR.exists():
        return [{"id": DEFAULT_TENANT, "name": "Default (single-tenant)"}]
    out = []
    for f in sorted(_TENANTS_DIR.glob("*.yaml")):
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            d.setdefault("id", f.stem)
            out.append(d)
        except Exception as exc:
            log.warning("skipping tenant %s: %s", f.name, exc)
    return out or [{"id": DEFAULT_TENANT, "name": "Default"}]


def get_tenant(tenant_id: str) -> Optional[Dict[str, Any]]:
    if not re.fullmatch(r"[a-z0-9_-]{2,40}", tenant_id or ""):
        return None
    if tenant_id == DEFAULT_TENANT:
        return {"id": DEFAULT_TENANT, "name": "Default"}
    f = _TENANTS_DIR / f"{tenant_id}.yaml"
    if not f.exists():
        return None
    try:
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        d.setdefault("id", tenant_id)
        return d
    except Exception:
        return None


def scoped_path(tenant_id: str, *parts: str) -> Path:
    """Return a per-tenant path under logs/<tenant_id>/..."""
    base = Path("logs") if tenant_id == DEFAULT_TENANT else Path("logs") / tenant_id
    p = base.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def request_tenant_id(request) -> str:
    """Determine tenant id from the current Flask request."""
    # 1. Explicit path prefix /t/<id>/...
    m = re.match(r"^/t/([a-z0-9_-]{2,40})/", request.path)
    if m:
        return m.group(1)
    # 2. Header
    hdr = request.headers.get("X-Tenant-Id", "").strip().lower()
    if hdr and re.fullmatch(r"[a-z0-9_-]{2,40}", hdr):
        return hdr
    # 3. Session (user was bound to a tenant at login)
    try:
        from flask import session
        s = session.get("tenant_id", "")
        if s:
            return s
    except Exception:
        pass
    return DEFAULT_TENANT
