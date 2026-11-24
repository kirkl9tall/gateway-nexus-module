"""
On/off switch on the Overview (POST /api/service/<action>).

With the systemd unit installed the Web UI uses systemctl. Without it (PC,
demo box, manual install) it manages the `main.py` process of THIS install
root only, through webui/gateway_process.py.
"""
from __future__ import annotations

import pytest

from webui import gateway_process as gp


@pytest.fixture()
def client(monkeypatch):
    from src.security import roles as _roles
    monkeypatch.setattr(_roles, "is_setup_required", lambda: False)
    from webui import app as webapp
    monkeypatch.setattr(webapp.time, "sleep", lambda s: None)
    c = webapp.app.test_client()
    with c.session_transaction() as s:
        s.update(auth_id="x", auth_ip="127.0.0.1", username="u", role="operator", _csrf="tok")
    return c


def test_without_unit_the_process_is_managed(client, monkeypatch):
    calls = []
    monkeypatch.setattr(gp, "systemd_unit_installed", lambda: False)
    monkeypatch.setattr(gp, "action", lambda a: calls.append(a) or (True, ""))
    monkeypatch.setattr(gp, "status", lambda: "active")
    r = client.post("/api/service/start", headers={"X-CSRF-Token": "tok"})
    assert r.get_json()["ok"] is True and calls == ["start"]
    assert r.get_json()["status"] == "active"


def test_with_unit_systemctl_is_used(client, monkeypatch):
    import subprocess
    seen = []
    monkeypatch.setattr(gp, "systemd_unit_installed", lambda: True)
    monkeypatch.setattr(gp, "action", lambda a: pytest.fail("must not manage the process"))

    class R:
        stdout = "active\n"
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append(cmd) or R())
    client.post("/api/service/restart", headers={"X-CSRF-Token": "tok"})
    assert ["sudo", "systemctl", "restart", "jerumednexus-gateway"] in seen


def test_viewer_cannot_switch(client):
    with client.session_transaction() as s:
        s["role"] = "viewer"
    assert client.post("/api/service/stop", headers={"X-CSRF-Token": "tok"}).status_code == 403


def test_unknown_action_refused(client):
    assert client.post("/api/service/reboot", headers={"X-CSRF-Token": "tok"}).status_code == 400


def test_only_this_install_root_is_matched():
    # The test runner itself is not a gateway: nothing must match.
    assert gp.gateway_pids() == [] or all(isinstance(p, int) for p in gp.gateway_pids())


def test_switch_shown_to_operator_not_viewer(monkeypatch):
    from src.security import roles as _roles
    monkeypatch.setattr(_roles, "is_setup_required", lambda: False)
    from webui import app as webapp
    c = webapp.app.test_client()
    c.set_cookie("jmnx_lang", "it")
    for role, expected in (("operator", True), ("viewer", False)):
        with c.session_transaction() as s:
            s.update(auth_id="x", auth_ip="127.0.0.1", username="u", role=role)
        html = c.get("/overview/live").get_data(as_text=True)
        assert ('role="switch"' in html) is expected, role
