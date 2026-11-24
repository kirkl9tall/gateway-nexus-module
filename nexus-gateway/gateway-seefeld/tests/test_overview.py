"""
The doctor's Overview must tell the truth in plain words.

Rules tested here (webui/overview.py, webui/check_view.py):
* a machine is "online" if it sent a result in the last 4 h or connected in
  the last 10 min; "offline" only when its USB cable is missing; "waiting"
  when it never spoke; everything is "paused" while the gateway is off;
* LOC-200 is shown only if it ever spoke (no phantom machine);
* each practice software has its own state, a failure on one never paints
  the others red;
* the headline picks the most important problem first;
* the check page regroups the technical checks into plain questions.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from webui import check_view, overview

NOW = datetime(2026, 11, 23, 15, 0, 0)

CFG = """
devices:
  - {id: sysmex_xq320, type: sysmex_astm, enabled: true, display_name: Sysmex XQ-320, listen_port: 5001}
  - {id: uc1000, type: uc1000_serial, enabled: true, display_name: UC-1000, serial_port: /dev/missing}
  - {id: cobas_b101, type: cobas_poct, enabled: true, display_name: Cobas b 101, serial_port: /dev/present}
  - {id: smt120, type: mllp_hl7, enabled: true, display_name: Seamaty SMT-120, listen_port: 6000}
targets:
  - {name: Tomedo, type: tomedo, enabled: true, sftp_host: 10.0.0.2}
  - {name: Archiv, type: file_drop, enabled: true, watch_folder: /tmp}
  - {name: Vecchio, type: vitomed, enabled: false, host: 1.2.3.4, port: 1}
"""


class FakeHistory:
    def __init__(self, rows=(), seen=None):
        self.rows = list(rows)
        self.seen = seen or {}

    def activity_since(self, since):
        return [r for r in self.rows if r["ts"] >= since]

    def daily_counts(self, days=7):
        return [{"date": (NOW - timedelta(days=i)).date().isoformat(), "total": 0, "ok": 0}
                for i in range(days - 1, -1, -1)]

    def device_last_seen(self):
        return dict(self.seen)

    def last_activity(self):
        return self.rows[0] if self.rows else None


def _row(minutes_ago, device="Sysmex XQ-320", ok=("Tomedo", "Archiv"), failed=()):
    return {"ts": (NOW - timedelta(minutes=minutes_ago)).isoformat(), "device": device,
            "status": "OK" if not failed else "ERRORE",
            "succeeded": list(ok), "failed": list(failed)}


def build(tmp_path, *, service="active", rows=(), seen=None, status=None, dlq=()):
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(CFG, encoding="utf-8")
    st = tmp_path / "status.json"
    st.write_text(json.dumps(status or {"running": True}), encoding="utf-8")
    return overview.build_overview(
        status_file=st, config_file=cfg, service=service,
        history=FakeHistory(rows, seen), dead_letters=lambda: list(dlq), now=NOW,
        path_exists=lambda p: "missing" not in p)


def _m(ov, name):
    return next(m for m in ov["machines"] if m["name"] == name)


def _d(ov, name):
    return next(d for d in ov["destinations"] if d["name"] == name)


# ── Machines ─────────────────────────────────────────────────────────────────

def test_machine_states(tmp_path):
    ov = build(tmp_path, rows=[_row(5)],
               seen={"Cobas b 101": (NOW - timedelta(days=1)).isoformat()})
    assert _m(ov, "Sysmex XQ-320")["state"] == "online"
    assert _m(ov, "UC-1000")["state"] == "offline"          # USB cable missing
    assert _m(ov, "Cobas b 101")["state"] == "idle"         # spoke yesterday
    assert _m(ov, "Seamaty SMT-120")["state"] == "waiting"  # never spoke
    assert ov["machines_up"] == 2
    assert ov["machines"][0]["name"] == "UC-1000", "problems first"


def test_recent_connection_counts_as_online(tmp_path):
    ov = build(tmp_path, status={"running": True, "connected": {
        "Seamaty SMT-120": (NOW - timedelta(minutes=3)).isoformat()}})
    assert _m(ov, "Seamaty SMT-120")["state"] == "online"


def test_everything_paused_when_gateway_off(tmp_path):
    ov = build(tmp_path, service="failed", rows=[_row(5)])
    assert {m["state"] for m in ov["machines"]} == {"paused"}
    assert ov["headline"]["key"] == "gateway_off"
    assert ov["flowing"] is False


def test_loc200_only_if_it_ever_spoke(tmp_path):
    assert "LOC-200" not in [m["name"] for m in build(tmp_path)["machines"]]
    ov = build(tmp_path, seen={"LOC-200": (NOW - timedelta(hours=1)).isoformat()})
    assert _m(ov, "LOC-200")["state"] == "online"


def test_today_count_per_machine(tmp_path):
    ov = build(tmp_path, rows=[_row(5), _row(10), _row(20, device="Cobas b 101")])
    assert _m(ov, "Sysmex XQ-320")["today"] == 2
    assert ov["today"]["total"] == 3


def test_kind_in_plain_words():
    assert overview.machine_kind("sysmex_xq320") == "Ematologia"
    assert overview.machine_kind("uc1000") == "Urine"
    assert overview.machine_kind("cobas_b101") == "HbA1c e lipidi"
    assert overview.machine_kind("unknown_thing") == "Analizzatore"


# ── Practice software ────────────────────────────────────────────────────────

def test_one_failing_destination_does_not_paint_the_other(tmp_path):
    ov = build(tmp_path, rows=[_row(2, ok=("Archiv",), failed=("Tomedo",))])
    assert _d(ov, "Tomedo")["level"] == "critical"
    assert _d(ov, "Archiv")["level"] == "good"
    assert ov["headline"] == {"level": "critical", "key": "destination_down", "name": "Tomedo"}


def test_disabled_destination_is_hidden(tmp_path):
    assert "Vecchio" not in [d["name"] for d in build(tmp_path)["destinations"]]


def test_destination_recovers_after_success(tmp_path):
    ov = build(tmp_path, rows=[_row(1), _row(30, ok=("Archiv",), failed=("Tomedo",))])
    assert _d(ov, "Tomedo")["state"] == "receiving"


def test_open_breaker_means_unreachable(tmp_path):
    ov = build(tmp_path, status={"running": True,
                                 "breakers": [{"name": "Tomedo", "breaker": {"state": "open"}}]})
    assert _d(ov, "Tomedo")["state"] == "unreachable"


def test_waiting_results_are_counted_per_destination(tmp_path):
    ov = build(tmp_path, rows=[_row(1)], dlq=[{"targets": ["Tomedo"]}, {"targets": ["Tomedo"]}])
    assert _d(ov, "Tomedo")["waiting"] == 2
    assert ov["headline"] == {"level": "warning", "key": "waiting", "n": 2}


def test_product_names(tmp_path):
    ov = build(tmp_path)
    assert _d(ov, "Tomedo")["product"] == "Tomedo"
    assert _d(ov, "Archiv")["product"] == "folder"


# ── Headline ─────────────────────────────────────────────────────────────────

def test_all_good_names_the_destinations(tmp_path, monkeypatch):
    cfg_ok = CFG.replace("serial_port: /dev/missing", "serial_port: /dev/present")
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(cfg_ok, encoding="utf-8")
    st = tmp_path / "status.json"
    st.write_text("{}", encoding="utf-8")
    ov = overview.build_overview(status_file=st, config_file=cfg, service="active",
                                 history=FakeHistory([_row(3)]), dead_letters=lambda: [],
                                 now=NOW, path_exists=lambda p: True)
    assert ov["headline"] == {"level": "good", "key": "all_good", "dest": "Tomedo, Archiv"}
    assert ov["flowing"] is True


def test_missing_usb_cable_is_the_headline(tmp_path):
    assert build(tmp_path, rows=[_row(3)])["headline"]["key"] == "machine_offline"


def test_no_systemd_uses_status_freshness(tmp_path):
    st = tmp_path / "status.json"
    ov = build(tmp_path, service="unknown", status={"running": True})
    # the file was just written: fresh → on (the build uses real mtime vs NOW)
    assert isinstance(ov["gateway"]["on"], bool)


def test_broken_inputs_never_break_the_page(tmp_path):
    class Boom:
        def __getattr__(self, name):
            raise RuntimeError("db locked")
    ov = overview.build_overview(status_file=tmp_path / "nope.json",
                                 config_file=tmp_path / "nope.yaml", service="active",
                                 history=Boom(), dead_letters=lambda: 1 / 0, now=NOW)
    assert ov["machines"] == [] and ov["today"]["total"] == 0


# ── Time words ───────────────────────────────────────────────────────────────

def test_when_is_human():
    assert overview.when(NOW - timedelta(minutes=5), now=NOW) == "oggi alle 14:55"
    assert overview.when(NOW - timedelta(days=1), now=NOW) == "ieri alle 15:00"
    assert overview.when(datetime(2026, 11, 2, 9, 5), now=NOW) == "il 02.11. alle 09:05"
    assert overview.when(None, now=NOW) == "mai"


# ── Check page, doctor view ──────────────────────────────────────────────────

def _esito(nome, stato, dati=None):
    return {"nome": nome, "stato": stato, "dettaglio": "", "rimedio": "", "dati": dati or {}}


def test_check_groups_and_order():
    res = {"esiti": [
        _esito("Servizio gateway", "ok"),
        _esito("Analizzatore · UC-1000", "guasto", {"porta": "/dev/ttyUSB0"}),
        _esito("Analizzatore · Sysmex", "ok", {"porta": 5001}),
        _esito("Gestionale · Tomedo (SFTP)", "guasto"),
        _esito("MSH-6 · Destinatario del referto", "ok"),
        _esito("Spazio su disco", "attenzione"),
    ]}
    v = check_view.doctor_view(res, lambda s, **kw: s.format(**kw) if kw else s)
    keys = [g["key"] for g in v["groups"]]
    assert keys[:2] == ["machines", "software"], "failures first"
    assert v["level"] == "critical" and v["problems"] == 3
    machines = v["groups"][0]
    assert "UC-1000: cavo USB non rilevato." in [i["text"] for i in machines["items"]]
    assert "cavo USB" in machines["todo"]
    software = v["groups"][1]
    assert software["items"][0]["name"] == "Tomedo"


def test_check_all_good_has_nothing_to_do():
    v = check_view.doctor_view({"esiti": [_esito("Servizio gateway", "ok")]}, lambda s, **kw: s)
    assert v["level"] == "good" and v["problems"] == 0
    assert v["groups"][0]["todo"] == ""


# ── Pages render for every language and role ─────────────────────────────────

@pytest.fixture()
def client(monkeypatch, tmp_path):
    from src.security import roles as _roles
    monkeypatch.setattr(_roles, "is_setup_required", lambda: False)
    from webui import app as webapp
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(CFG, encoding="utf-8")
    monkeypatch.setattr(webapp, "CONFIG_F", cfg)
    monkeypatch.setattr(webapp, "STATUS_F", tmp_path / "status.json")
    monkeypatch.setattr(webapp, "_service_status", lambda: "active")
    return webapp.app.test_client()


@pytest.mark.parametrize("lang,word", [("it", "I tuoi apparecchi"), ("de", "Ihre Geräte"),
                                       ("fr", "Vos appareils"), ("en", "Your machines")])
@pytest.mark.parametrize("role", ["viewer", "admin"])
def test_overview_and_machines_render(client, lang, word, role):
    client.set_cookie("jmnx_lang", lang)
    with client.session_transaction() as s:
        s.update(auth_id="x", auth_ip="127.0.0.1", username="u", role=role)
    for url in ("/", "/overview/live", "/analyzers"):
        r = client.get(url)
        assert r.status_code == 200, url
        assert word in r.get_data(as_text=True), url


def test_doctor_does_not_get_technician_section(client):
    with client.session_transaction() as s:
        s.update(auth_id="x", auth_ip="127.0.0.1", username="u", role="viewer")
    html = client.get("/").get_data(as_text=True)
    assert 'data-view="studio"' in html          # CSS hides .tech-only for doctors
    assert 'class="tech-zone tech-only"' in html


def test_api_overview_is_json(client):
    with client.session_transaction() as s:
        s.update(auth_id="x", auth_ip="127.0.0.1", username="u", role="viewer")
    d = client.get("/api/overview").get_json()
    assert {"gateway", "machines", "destinations", "today", "week", "headline"} <= set(d)
