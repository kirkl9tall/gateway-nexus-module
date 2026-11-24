"""
LDAP / Active Directory authentication.

Config in gateway.yaml:
  ldap:
    enabled: true
    server:   "ldaps://ad.hospital.local:636"
    base_dn:  "OU=Users,DC=hospital,DC=local"
    bind_dn:  "CN=jerumednexus,OU=Service Accounts,DC=hospital,DC=local"
    bind_pw:  # from LDAP_BIND_PW env
    user_filter: "(sAMAccountName={username})"
    group_role_map:
      "CN=JMNX-Admins,...":    admin
      "CN=JMNX-Operators,...": operator
      "CN=JMNX-Viewers,...":   viewer

Requires: python-ldap. Optional.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger("loc200.ldap")


class LDAPConfig:
    def __init__(self, cfg: dict) -> None:
        self.enabled     = bool(cfg.get("enabled", False))
        self.server      = cfg.get("server", "")
        self.base_dn     = cfg.get("base_dn", "")
        self.bind_dn     = cfg.get("bind_dn", "")
        self.bind_pw     = cfg.get("bind_pw") or os.environ.get("LDAP_BIND_PW", "")
        self.user_filter = cfg.get("user_filter", "(sAMAccountName={username})")
        self.group_role_map = cfg.get("group_role_map", {})
        self.default_role = cfg.get("default_role", "viewer")

    def is_valid(self) -> bool:
        return bool(self.enabled and self.server and self.base_dn)


def authenticate(cfg: LDAPConfig, username: str, password: str) -> Optional[str]:
    """
    Bind as service account, look up user DN, then bind as user to verify pwd.
    Returns role (viewer/operator/admin) on success, None on failure.
    """
    try:
        import ldap
    except ImportError:
        log.error("python-ldap not installed: pip install python-ldap")
        return None

    try:
        conn = ldap.initialize(cfg.server)
        conn.set_option(ldap.OPT_REFERRALS, 0)
        conn.simple_bind_s(cfg.bind_dn, cfg.bind_pw)

        user_filter = cfg.user_filter.replace("{username}", ldap.dn.escape_dn_chars(username))
        results = conn.search_s(cfg.base_dn, ldap.SCOPE_SUBTREE,
                                 user_filter, ["memberOf", "cn"])
        if not results:
            return None
        user_dn, attrs = results[0]

        # Verify user password
        conn.simple_bind_s(user_dn, password)

        # Determine role from group membership
        groups = [g.decode() if isinstance(g, bytes) else g
                  for g in attrs.get("memberOf", [])]
        for group_dn, role in cfg.group_role_map.items():
            if group_dn in groups:
                return role
        return cfg.default_role
    except Exception as exc:
        log.debug("LDAP auth failed for %s: %s", username, exc)
        return None
