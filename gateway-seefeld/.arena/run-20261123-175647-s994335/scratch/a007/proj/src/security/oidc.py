"""
OpenID Connect (OIDC) login for enterprise SSO.

Config in gateway.yaml:
  oidc:
    enabled: true
    provider_url: "https://login.microsoftonline.com/<tenant>/v2.0"
    client_id:    "<app-id>"
    client_secret: <resolved from OIDC_CLIENT_SECRET env>
    redirect_uri: "https://gateway.example.ch/auth/oidc/callback"
    default_role: "viewer"
    role_claim:   "roles"    # groups claim to map to viewer/operator/admin

Requires: authlib. Optional -- gateway works without OIDC configured.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

log = logging.getLogger("loc200.oidc")


class OIDCConfig:
    def __init__(self, cfg: dict) -> None:
        self.enabled       = bool(cfg.get("enabled", False))
        self.provider_url  = cfg.get("provider_url", "").rstrip("/")
        self.client_id     = cfg.get("client_id", "")
        self.client_secret = cfg.get("client_secret") or os.environ.get("OIDC_CLIENT_SECRET", "")
        self.redirect_uri  = cfg.get("redirect_uri", "")
        self.default_role  = cfg.get("default_role", "viewer")
        self.role_claim    = cfg.get("role_claim", "roles")
        self.role_map      = cfg.get("role_map", {})   # {"admin-group": "admin", ...}

    def is_valid(self) -> bool:
        return (self.enabled and self.provider_url and self.client_id
                and self.client_secret and self.redirect_uri)


def build_client(cfg: OIDCConfig):
    """Return an authlib OAuth2Session or None if authlib is missing."""
    try:
        from authlib.integrations.requests_client import OAuth2Session
    except ImportError:
        log.error("authlib not installed: pip install authlib requests")
        return None
    return OAuth2Session(
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        scope="openid email profile",
        redirect_uri=cfg.redirect_uri,
    )


def _oidc_metadata(provider_url: str) -> Optional[Dict[str, Any]]:
    """Fetch .well-known/openid-configuration."""
    try:
        import requests
        r = requests.get(f"{provider_url}/.well-known/openid-configuration", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        log.warning("OIDC metadata fetch failed: %s", exc)
        return None


def authorize_url(cfg: OIDCConfig, state: str) -> Optional[str]:
    md = _oidc_metadata(cfg.provider_url)
    if not md:
        return None
    client = build_client(cfg)
    if not client:
        return None
    uri, _state = client.create_authorization_url(
        md["authorization_endpoint"], state=state,
    )
    return uri


def exchange_code_for_userinfo(cfg: OIDCConfig, code: str) -> Optional[Dict[str, Any]]:
    md = _oidc_metadata(cfg.provider_url)
    if not md:
        return None
    client = build_client(cfg)
    if not client:
        return None
    try:
        client.fetch_token(md["token_endpoint"], code=code, grant_type="authorization_code")
        import requests
        r = requests.get(md["userinfo_endpoint"],
                         headers={"Authorization": f"Bearer {client.token['access_token']}"},
                         timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        log.error("OIDC token exchange failed: %s", exc)
        return None


def map_role(userinfo: Dict[str, Any], cfg: OIDCConfig) -> str:
    """Map OIDC roles/groups claim to internal role name."""
    claims = userinfo.get(cfg.role_claim, [])
    if isinstance(claims, str):
        claims = [claims]
    for c in claims:
        if c in cfg.role_map:
            return cfg.role_map[c]
    return cfg.default_role
