"""
Results page: list every result, filter it, and open one to see the values
and where it was delivered (webui/results_view.py).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from webui import results_view as rv


@pytest.fixture()
def client(monkeypatch, tmp_path):
    from src.common import history
    monkeypatch.setattr(history, "_DB_PATH", tmp_path / "history.db")
    monkeypatch.setattr(history, "_conn", None)
    now = datetime.now()
    obs = [{"analyte": "GLU", "name_de": "Glukose", "value": "7.9", "value_num": 7.9, "unit": "mmol/L",
            "flag": "", "ref_low": 3.9, "ref_high": 6.1},
           {"analyte": "HGB", "name_de": "Hämoglobin", "value": "14", "unit": "g/dL", "flag": "",
            "ref_low": 12, "ref_high": 16}]
    history.record({"ts": now.isoformat(), "device": "Seamaty SMT-120", "sample_id": "S1",
                    "patient_id": "P-OK", "analytes": 2, "status": "OK", "succeeded": ["Tomedo"],
                    "failed": [], "result": {"observations": obs}, "hl7": "MSH|^~\\&|X\rPID|||P-OK"})
    history.record({"ts": now.isoformat(), "device": "Horiba", "sample_id": "S2", "patient_id": "P-BAD",
                    "analytes": 1, "status": "ERRORE", "succeeded": [], "failed": ["Tomedo"],
                    "errors": {"Tomedo": "connection refused"}, "result": {"observations": obs[:1]}})
    history.record({"ts": (now - timedelta(days=3)).isoformat(), "device": "Horiba", "sample_id": "S3",
                    "patient_id": "P-OLD", "analytes": 1, "status": "OK", "succeeded": ["Tomedo"]})
    from src.security import roles as _roles
    monkeypatch.setattr(_roles, "is_setup_required", lambda: False)
    from webui import app as webapp
    c = webapp.app.test_client()
    c.set_cookie("jmnx_lang", "it")
    with c.session_transaction() as s:
        s.update(auth_id="x", auth_ip="127.0.0.1", username="u", role="operator")
    yield c
    history._conn = None


def _ids(c, **params):
    html = c.get("/results/list", query_string=params).get_data(as_text=True)
    return [p for p in ("P-OK", "P-BAD", "P-OLD") if p in html]


def test_today_by_default(client):
    assert _ids(client) == ["P-OK", "P-BAD"] or set(_ids(client)) == {"P-OK", "P-BAD"}


def test_filters(client):
    assert set(_ids(client, period="7d")) == {"P-OK", "P-BAD", "P-OLD"}
    assert _ids(client, period="7d", status="problem") == ["P-BAD"]
    assert set(_ids(client, period="7d", status="ok")) == {"P-OK", "P-OLD"}
    assert _ids(client, period="all", q="OLD") == ["P-OLD"]
    assert _ids(client, period="all", device="Seamaty SMT-120") == ["P-OK"]


def test_rows_are_clickable(client):
    html = client.get("/results/list").get_data(as_text=True)
    assert 'onclick="openDetail(' in html


def test_detail_shows_values_flags_and_delivery(client):
    from src.common import history
    bad = next(r for r in history.list_results(limit=10) if r["patient_id"] == "P-BAD")
    html = client.get(f"/results/{bad['id']}").get_data(as_text=True)
    assert "Glukose" in html and "7.9" in html
    assert "alto" in html                                   # above 6.1
    assert "connection refused" in html                     # why Tomedo failed
    assert "Invia di nuovo" in html                         # operator may resend


def test_detail_unknown_is_404(client):
    assert client.get("/results/999999").status_code == 404


def test_viewer_cannot_resend_but_sees_values(client):
    from src.common import history
    with client.session_transaction() as s:
        s["role"] = "viewer"
    bad = next(r for r in history.list_results(limit=10) if r["patient_id"] == "P-BAD")
    html = client.get(f"/results/{bad['id']}").get_data(as_text=True)
    assert "Glukose" in html and "Invia di nuovo" not in html


@pytest.mark.parametrize("lang,word", [("de", "Ergebnisse"), ("fr", "Résultats"), ("en", "Results")])
def test_page_translated(client, lang, word):
    client.set_cookie("jmnx_lang", lang)
    assert word in client.get("/results").get_data(as_text=True)


def test_value_level():
    assert rv.value_level({"value": "7", "ref_low": 1, "ref_high": 5}) == "high"
    assert rv.value_level({"value": "0.5", "ref_low": 1, "ref_high": 5}) == "low"
    assert rv.value_level({"value": "3", "ref_low": 1, "ref_high": 5}) == ""
    assert rv.value_level({"value": "neg", "flag": "H"}) == "high"
    assert rv.value_level({"value": "neg"}) == ""


def test_period_range():
    d = date(2026, 11, 24)
    assert rv.period_range("today", d) == ("2026-11-24", "")
    assert rv.period_range("yesterday", d) == ("2026-11-23", "2026-11-24")
    assert rv.period_range("7d", d) == ("2026-11-18", "")
    assert rv.period_range("all", d) == ("", "")
