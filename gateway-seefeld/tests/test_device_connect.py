"""
Connecting a machine picked from the catalog (/devices/new → POST
/api/devices/<id>/connect) must keep the profile's protocol details.

The older PUT /api/devices/<id> replaced the whole file: a Sysmex profile lost
`astm_mode`, `unidirectional` and its timeouts, and the analyzer then showed
"TCP/IP kann nicht hergestellt werden". This endpoint merges instead.
"""
from __future__ import annotations

import yaml
import pytest


@pytest.fixture()
def env(monkeypatch, tmp_path):
    from src.security import roles as _roles
    monkeypatch.setattr(_roles, "is_setup_required", lambda: False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config" / "devices").mkdir(parents=True)
    (tmp_path / "config" / "devices" / "sysmex_xq320.yaml").write_text(
        "id: sysmex_xq320\ntype: sysmex_astm\nenabled: false\n"
        "display_name: Sysmex XQ-320\nvendor: Sysmex\nmodel: XQ-320\n"
        "listen_host: 0.0.0.0\nlisten_port: 5006\nastm_mode: '1381-02'\n"
        "unidirectional: true\nread_timeout_seconds: 15\n", encoding="utf-8")
    (tmp_path / "config" / "devices" / "other.yaml").write_text(
        "id: other\ntype: mllp_hl7\nenabled: true\nlisten_port: 6000\n", encoding="utf-8")
    from webui import app as webapp
    monkeypatch.setattr(webapp, "CONFIG_F", tmp_path / "config" / "gateway.yaml")
    monkeypatch.setattr(webapp, "_try_reload_gateway", lambda: None)
    c = webapp.app.test_client()
    with c.session_transaction() as s:
        s.update(auth_id="x", auth_ip="127.0.0.1", username="admin", role="admin", _csrf="tok")
    return c, tmp_path


def _connect(c, dev, **body):
    return c.post(f"/api/devices/{dev}/connect", json=body, headers={"X-CSRF-Token": "tok"})


def test_connect_keeps_protocol_details(env):
    c, root = env
    r = _connect(c, "sysmex_xq320", transport="tcp", listen_port=5006, display_name="Sysmex Labor")
    assert r.get_json()["ok"] is True
    d = yaml.safe_load((root / "config/devices/sysmex_xq320.yaml").read_text())
    assert d["enabled"] is True and d["display_name"] == "Sysmex Labor"
    assert d["astm_mode"] == "1381-02" and d["unidirectional"] is True
    assert d["read_timeout_seconds"] == 15 and d["type"] == "sysmex_astm"


def test_switch_to_usb_drops_network_fields(env):
    c, root = env
    assert _connect(c, "sysmex_xq320", transport="usb", serial_port="/dev/ttyUSB0").get_json()["ok"]
    d = yaml.safe_load((root / "config/devices/sysmex_xq320.yaml").read_text())
    assert d["serial_port"].startswith("/dev/") and "listen_port" not in d
    assert d["astm_mode"] == "1381-02"


def test_port_already_used_is_refused(env):
    c, _ = env
    r = _connect(c, "sysmex_xq320", transport="tcp", listen_port=6000)
    assert r.status_code == 409 and r.get_json()["code"] == "port_in_use"


def test_bad_input_is_refused(env):
    c, _ = env
    assert _connect(c, "sysmex_xq320", transport="usb", serial_port="/etc/passwd").status_code == 400
    assert _connect(c, "../etc", transport="tcp", listen_port=7000).status_code in (400, 404)
    assert _connect(c, "missing", transport="tcp", listen_port=7000).status_code == 404


def test_add_page_lists_the_catalog_translated(env):
    c, _ = env
    c.set_cookie("jmnx_lang", "de")
    html = c.get("/devices/new").get_data(as_text=True)
    assert "Welches Gerät möchten Sie verbinden?" in html
    assert 'data-id="sysmex_xq320"' in html
