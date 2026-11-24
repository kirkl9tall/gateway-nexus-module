"""
Regression tests for the three follow-up fixes plus the CWD/install-root fix:

1. TOTP 2FA login flow — user with an active secret must supply an OTP.
2. Admin password reset via /api/users/<name>/password.
3. Gateway boot invokes wal.recover_at_boot and quarantines orphans to DLQ.
4. save_password() / roles.create_user() work regardless of process CWD
   (regression for the installer PermissionError seen at Altstetten).
"""
from __future__ import annotations


import pyotp
import pytest


# ── Shared fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """
    Redirect every module that persists to disk into a temp directory.
    Keeps tests hermetic and lets us run assertions on the on-disk state.
    """
    (tmp_path / "config").mkdir()
    (tmp_path / "logs").mkdir()
    monkeypatch.chdir(tmp_path)

    # Anchor the module-level Path constants that were resolved at import
    # time via config_dir(). Without these overrides the tests write to
    # the REAL install tree's config/ and cross-pollute each other.
    from src.security import roles as _roles
    from src.security import totp as _totp
    from src.security import auth as _auth
    monkeypatch.setattr(_auth, "_HASH_FILE", tmp_path / "config" / "webui_password.hash")
    monkeypatch.setattr(_auth, "_LEGACY_PLAIN_FILE",
                        tmp_path / "config" / "webui_password.txt")
    monkeypatch.setattr(_auth, "_SECRET_KEY_FILE",
                        tmp_path / "config" / "webui_secret.key")
    monkeypatch.setattr(_roles, "_USERS_FILE", tmp_path / "config" / "webui_users.json")
    monkeypatch.setattr(_totp, "_USERS_FILE", tmp_path / "config" / "webui_users.json")

    # WebUI reads/writes gateway.yaml via CONFIG_F — override it too so the
    # save-form tests don't touch the real project checkout.
    from webui import app as _webapp
    monkeypatch.setattr(_webapp, "CONFIG_F", tmp_path / "config" / "gateway.yaml")
    monkeypatch.setattr(_webapp, "LICENSE_F", tmp_path / "config" / "license.json")
    monkeypatch.setattr(_webapp, "STATUS_F", tmp_path / "logs" / "status.json")
    return tmp_path


@pytest.fixture
def client(sandbox):
    """A Flask test client with a seeded admin user."""
    from src.security import roles as _roles
    _roles.create_user("admin", "InitialPassword12!", "admin")
    _roles.create_user("nurse", "NursePassword12!", "viewer")

    # Import webui.app AFTER the users file has been seeded so first-run
    # setup doesn't kick in and redirect us.
    from webui.app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _login(c, username: str, password: str, otp: str = "") -> int:
    return c.post("/login", data={
        "username": username, "password": password, "otp": otp,
    }, follow_redirects=False).status_code


# ── 1. TOTP end-to-end ──────────────────────────────────────────────────────

def test_totp_status_defaults_to_disabled(client):
    # Log in as admin first — status endpoint requires session.
    assert _login(client, "admin", "InitialPassword12!") in (302, 200)
    r = client.get("/api/users/admin/totp/status")
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "enabled": False}


def test_totp_enroll_confirm_then_login_requires_otp(client):
    assert _login(client, "admin", "InitialPassword12!") == 302
    # Enroll
    r = client.post("/api/users/admin/totp/enroll",
                    json={},
                    headers={"X-CSRF-Token": client.get("/settings")  # get session cookies
                             and _csrf(client)})
    body = r.get_json()
    assert r.status_code == 200 and body["ok"]
    secret = body["secret"]

    # Confirm with a valid OTP
    code = pyotp.TOTP(secret).now()
    r = client.post("/api/users/admin/totp/verify",
                    json={"code": code},
                    headers={"X-CSRF-Token": _csrf(client)})
    assert r.status_code == 200 and r.get_json()["ok"]

    # A fresh session must now be rejected without an OTP code
    client.get("/logout")
    assert _login(client, "admin", "InitialPassword12!") == 200  # returns login page

    # And accepted with a valid one
    fresh_code = pyotp.TOTP(secret).now()
    assert _login(client, "admin", "InitialPassword12!", fresh_code) == 302


def test_totp_wrong_code_rejected(client):
    assert _login(client, "admin", "InitialPassword12!") == 302
    body = client.post("/api/users/admin/totp/enroll", json={},
                       headers={"X-CSRF-Token": _csrf(client)}).get_json()
    pyotp.TOTP(body["secret"]).now()
    client.post("/api/users/admin/totp/verify",
                json={"code": pyotp.TOTP(body["secret"]).now()},
                headers={"X-CSRF-Token": _csrf(client)})

    client.get("/logout")
    # Login with password ok, OTP wrong → still on login page (200), not redirect (302)
    assert _login(client, "admin", "InitialPassword12!", "000000") == 200


# ── 2. Admin password reset ─────────────────────────────────────────────────

def test_admin_can_reset_another_users_password(client):
    assert _login(client, "admin", "InitialPassword12!") == 302
    r = client.post("/api/users/nurse/password",
                    json={"password": "BrandNewNursePw99!"},
                    headers={"X-CSRF-Token": _csrf(client)})
    assert r.status_code == 200 and r.get_json()["ok"]

    # Old password fails, new password works
    client.get("/logout")
    assert _login(client, "nurse", "NursePassword12!") == 200      # login form re-shown
    assert _login(client, "nurse", "BrandNewNursePw99!") == 302    # accepted → redirect


def test_admin_cannot_reset_own_password_via_users_endpoint(client):
    assert _login(client, "admin", "InitialPassword12!") == 302
    r = client.post("/api/users/admin/password",
                    json={"password": "SomethingElse123!"},
                    headers={"X-CSRF-Token": _csrf(client)})
    assert r.status_code == 400
    assert "settings" in r.get_json()["error"].lower()


def test_non_admin_cannot_reset_others(client):
    assert _login(client, "nurse", "NursePassword12!") == 302
    r = client.post("/api/users/admin/password",
                    json={"password": "PwnedByViewer12!"},
                    headers={"X-CSRF-Token": _csrf(client)})
    # require_role("admin") returns 403 for API paths
    assert r.status_code in (302, 403)


# ── 3. WAL boot recovery ────────────────────────────────────────────────────

def test_gateway_boot_quarantines_wal_orphans(sandbox, monkeypatch):
    from src.common import wal
    monkeypatch.setattr(wal, "_DB", sandbox / "logs" / "wal.db")

    # Seed one in-flight entry to simulate a pre-crash state.
    wal.enter("lis-a", "MSG-ABC-42",
              b"MSH|^~\\&|GW|X|LIS|X|20260914||ORU^R01|MSG-ABC-42|P|2.5\r"
              b"PID|1||SAMPLE-9876||Doe^John\r")

    # Import the boot hook and run it directly. No event loop needed.
    from src.gateway import _wal_replay_to_dlq
    report = wal.recover_at_boot(_wal_replay_to_dlq)
    assert report["total"] == 1
    assert report["skipped"] == 1     # quarantined-then-cleared
    assert wal.in_flight_count() == 0

    # A .meta.json now exists in the DLQ tree
    metas = list((sandbox / "logs" / "dead_letter").rglob("*.meta.json"))
    assert metas, "boot recovery should have written a DLQ entry"
    import json
    meta = json.loads(metas[0].read_text(encoding="utf-8"))
    assert meta.get("reason") == "wal_recovered_at_boot"
    assert "lis-a" in (meta.get("targets") or [])


# ── 4. Install-root anchor / CWD independence ───────────────────────────────

def test_save_password_works_with_wrong_cwd(tmp_path, monkeypatch):
    """
    Regression for the installer crash at Altstetten:

        PermissionError: [Errno 13] Permission denied: 'config'

    The installer ran `sudo -u loc200 python -c "save_password(...)"` with
    CWD=/home/alt (or /root). Before the fix, save_password() resolved
    'config/webui_password.hash' as a relative path against that CWD and
    the loc200 user got EACCES.

    Contract now: as long as JMNX_INSTALL_ROOT is set (or the module can
    walk up to a project root), save_password() writes to the anchored
    path — even from CWD='/'.
    """
    install = tmp_path / "install-tree"
    install.mkdir()
    (install / "config").mkdir()
    monkeypatch.setenv("JMNX_INSTALL_ROOT", str(install))

    # Blow away the cached install_root() answer so it re-reads the env var
    from src.common import paths as _paths
    _paths.install_root.cache_clear()

    # Reload auth so _HASH_FILE re-binds using the new install_root
    import importlib
    from src.security import auth as _auth
    importlib.reload(_auth)

    # Simulate the installer: CWD is somewhere the loc200 user can't write.
    monkeypatch.chdir(tmp_path)   # not install/, not tmp_path/config/
    _auth.save_password("HotFixPassword12!")

    # File landed under install/, not CWD
    written = install / "config" / "webui_password.hash"
    assert written.is_file(), "save_password must anchor to install_root, not CWD"
    assert (install / "config" / "webui_password.hash").read_text().startswith(("$2", "sha256:"))


def test_roles_create_user_survives_wrong_cwd(tmp_path, monkeypatch):
    """Same regression, one layer up: create_user() → _save() → webui_users.json."""
    install = tmp_path / "install-tree-2"
    install.mkdir()
    (install / "config").mkdir()
    monkeypatch.setenv("JMNX_INSTALL_ROOT", str(install))

    from src.common import paths as _paths
    _paths.install_root.cache_clear()
    import importlib
    from src.security import auth as _auth
    from src.security import roles as _roles
    importlib.reload(_auth)
    importlib.reload(_roles)

    monkeypatch.chdir(tmp_path)
    _roles.create_user("admin", "HotFixPassword12!", "admin")

    users_file = install / "config" / "webui_users.json"
    assert users_file.is_file()
    import json
    data = json.loads(users_file.read_text())
    assert any(u["name"] == "admin" and u["role"] == "admin" for u in data["users"])


# ── 5. Structured config save (no client-side YAML edits) ───────────────────

def test_config_save_form_writes_valid_yaml(client, sandbox):
    """
    Regression for the config-page 400 storm at Altstetten:

    The old flow had the browser build YAML via string replace, which broke
    the moment the current file didn't match the expected shape. The new
    endpoint accepts JSON, merges, validates, writes.
    """
    # Seed a minimal current config so the merge has something to overlay.
    (sandbox / "config" / "gateway.yaml").write_text(
        "log_level: INFO\nloc200:\n  connection_type: http\n  http_port: 5003\n"
        "hl7:\n  sending_facility: OLD\n  receiving_facility: OLD\n"
        "targets: []\ndevices: []\n",
        encoding="utf-8",
    )
    assert _login(client, "admin", "InitialPassword12!") == 302

    payload = {
        "hl7": {"sending_facility": "Praxis Test", "sending_application": "GW"},
        "loc200": {"connection_type": "http", "http_port": 5003},
        "targets": [
            {"name": "vitomed", "type": "vitomed", "enabled": True,
             "host": "10.0.0.50", "port": 6661},
            {"name": "tomedo", "type": "tomedo", "enabled": True,
             "sftp_host": "10.0.0.60", "sftp_port": 22,
             "sftp_user": "labimport", "sftp_pass": "s3cret",
             "sftp_remote_path": "/import"},
        ],
    }
    r = client.post("/api/config/save-form",
                    json=payload,
                    headers={"X-CSRF-Token": _csrf(client)})
    body = r.get_json()
    assert r.status_code == 200, body
    assert body["ok"] is True

    # File on disk must parse and contain both targets under the correct schema keys.
    import yaml as _y
    written = _y.safe_load((sandbox / "config" / "gateway.yaml").read_text(encoding="utf-8"))
    assert written["hl7"]["sending_facility"] == "Praxis Test"
    names = [t["name"] for t in written["targets"]]
    assert "vitomed" in names and "tomedo" in names
    vito = next(t for t in written["targets"] if t["name"] == "vitomed")
    assert vito["type"] == "vitomed" and vito["port"] == 6661
    tomedo = next(t for t in written["targets"] if t["name"] == "tomedo")
    assert tomedo["type"] == "tomedo"
    assert tomedo["sftp_pass"] == "s3cret"


def test_config_save_form_preserves_secret_when_placeholder(client, sandbox):
    """If the operator leaves sftp_pass as '********', keep the stored value."""
    (sandbox / "config" / "gateway.yaml").write_text(
        "hl7:\n  sending_facility: X\ntargets:\n"
        "- name: tomedo\n  type: tomedo\n  enabled: true\n"
        "  sftp_host: h\n  sftp_user: u\n  sftp_pass: ORIGINAL_SECRET\n"
        "  sftp_remote_path: /import\n",
        encoding="utf-8",
    )
    assert _login(client, "admin", "InitialPassword12!") == 302

    r = client.post("/api/config/save-form", json={
        "hl7": {"sending_facility": "X"},
        "targets": [{
            "name": "tomedo", "type": "tomedo", "enabled": True,
            "sftp_host": "h", "sftp_user": "u", "sftp_pass": "********",
            "sftp_remote_path": "/import",
        }],
    }, headers={"X-CSRF-Token": _csrf(client)})
    assert r.status_code == 200
    import yaml as _y
    written = _y.safe_load((sandbox / "config" / "gateway.yaml").read_text(encoding="utf-8"))
    tomedo = next(t for t in written["targets"] if t["name"] == "tomedo")
    assert tomedo["sftp_pass"] == "ORIGINAL_SECRET"  # not the placeholder


def test_config_save_form_rejects_invalid_schema(client, sandbox):
    """Pydantic rejection must surface as 400 with a readable message."""
    (sandbox / "config" / "gateway.yaml").write_text(
        "hl7:\n  sending_facility: X\ntargets: []\n", encoding="utf-8"
    )
    assert _login(client, "admin", "InitialPassword12!") == 302

    r = client.post("/api/config/save-form", json={
        "targets": [{"name": "x", "type": "not_a_real_type", "enabled": True}],
    }, headers={"X-CSRF-Token": _csrf(client)})
    assert r.status_code == 400
    # Either our field-level validator or Pydantic catches it — both are OK,
    # what matters is the operator gets a readable message, not a stack.
    err = (r.get_json().get("error") or "").lower()
    assert err  # non-empty


def test_config_save_form_rejects_tomedo_without_host(client, sandbox):
    """
    Regression for Altstetten: operator enables Tomedo but leaves
    sftp_host empty (thought the placeholder was the value). Before this
    fix the config saved with '' and every dispatch failed silently.
    Now the server rejects with a targeted error mentioning the field.
    """
    (sandbox / "config" / "gateway.yaml").write_text(
        "hl7:\n  sending_facility: X\ntargets: []\n", encoding="utf-8"
    )
    assert _login(client, "admin", "InitialPassword12!") == 302

    r = client.post("/api/config/save-form", json={
        "targets": [{
            "name": "tomedo", "type": "tomedo", "enabled": True,
            "sftp_host": "",             # empty — this is the bug we're catching
            "sftp_user": "jerumed",
            "sftp_pass": "s3cret",
            "sftp_remote_path": "/import",
        }],
    }, headers={"X-CSRF-Token": _csrf(client)})
    assert r.status_code == 400
    body = r.get_json()
    err = (body.get("error") or "").lower()
    assert "sftp" in err and ("host" in err or "ip server" in err), body


def test_config_save_form_rejects_mllp_without_port(client, sandbox):
    """Same guard for MLLP-style gestionali (Vitomed / curaMED / etc.)."""
    (sandbox / "config" / "gateway.yaml").write_text(
        "hl7:\n  sending_facility: X\ntargets: []\n", encoding="utf-8"
    )
    assert _login(client, "admin", "InitialPassword12!") == 302

    r = client.post("/api/config/save-form", json={
        "targets": [{
            "name": "vitomed", "type": "vitomed", "enabled": True,
            "host": "192.168.2.50",
            # port intentionally omitted
        }],
    }, headers={"X-CSRF-Token": _csrf(client)})
    assert r.status_code == 400
    assert "porta" in (r.get_json().get("error") or "").lower()


def test_config_save_form_allows_disabled_incomplete_targets(client, sandbox):
    """
    Sanity: only enabled targets are validated. Otherwise the operator
    couldn't ever turn a broken target OFF via the WebUI.
    """
    (sandbox / "config" / "gateway.yaml").write_text(
        "hl7:\n  sending_facility: X\ntargets: []\n", encoding="utf-8"
    )
    assert _login(client, "admin", "InitialPassword12!") == 302

    r = client.post("/api/config/save-form", json={
        "targets": [{
            "name": "tomedo", "type": "tomedo", "enabled": False,
            "sftp_host": "", "sftp_user": "", "sftp_pass": "", "sftp_remote_path": "",
        }],
    }, headers={"X-CSRF-Token": _csrf(client)})
    # Disabled → not incoming_targets (form filter), no validation triggers
    # → the payload merges with the target simply absent.
    assert r.status_code == 200, r.get_json()


def test_service_action_returns_readable_error_on_failure(monkeypatch):
    """
    Regression for the "Errore: sconosciuto" toast that hid the real
    reason (permission denied, unit not found, timeout).
    Now _service_action returns (bool, str) and api_service surfaces the
    string via the `error` field.
    """
    from webui import app as _webapp
    from unittest.mock import patch
    import subprocess

    # Case 1: exit code != 0 → stderr surfaces
    def _fake_run_fail(*a, **kw):
        raise subprocess.CalledProcessError(
            returncode=5, cmd=a[0], stderr="Unit not found",
        )
    with patch("subprocess.run", _fake_run_fail):
        ok, err = _webapp._service_action("start")
        assert ok is False
        assert "unit not found" in err.lower()

    # Case 2: timeout → readable message, not just "sconosciuto"
    def _fake_run_timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=15)
    with patch("subprocess.run", _fake_run_timeout):
        ok, err = _webapp._service_action("restart")
        assert ok is False
        assert "timeout" in err.lower()

    # Case 3: happy path
    class _R:
        stdout = ""
        stderr = ""
    def _fake_run_ok(*a, **kw):
        return _R()
    with patch("subprocess.run", _fake_run_ok):
        ok, err = _webapp._service_action("start")
        assert ok is True and err == ""


# ── Helpers ────────────────────────────────────────────────────────────────

def _csrf(c) -> str:
    """Extract the CSRF token from the /settings page HTML."""
    html = c.get("/settings").get_data(as_text=True)
    import re
    m = re.search(r'name="_csrf"[^>]*value="([^"]+)"', html)
    if m:
        return m.group(1)
    # Fallback: header from a meta tag on base.html
    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else ""
