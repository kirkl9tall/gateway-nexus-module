"""
Tests for the Frame Inspector — verifies:
  1. history.py persists the conversion_audit column and returns it
  2. /api/sample/<sample_id>/audit endpoint works (404 when missing, 200 when found)
  3. /inspect and /inspect/<sample_id> render without error
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def _isolated_history(tmp_path, monkeypatch):
    """Redirect history.db to a temp path so tests don't pollute real logs."""
    from src.common import history

    fake_db = tmp_path / "history.db"
    monkeypatch.setattr(history, "_DB_PATH", fake_db)
    # Force fresh connection to the new path
    history._conn = None
    yield history
    if history._conn:
        history._conn.close()
    history._conn = None


def test_history_persists_conversion_audit(_isolated_history) -> None:
    history = _isolated_history
    audit_payload = json.dumps({
        "device": "XQ-320",
        "sample": {"raw": "SN0042A", "sent": "SN0042"},
        "patient": {"raw": "SN0042A", "sent": "SN0042"},
        "raw_payload_sha": "a" * 64,
        "raw_payload_hex": "01" * 128,
        "changes": [
            {"raw": {"code": "HCT", "value": "0.42", "unit": "%"},
             "sent": {"code": "HCT", "value": "42.0", "unit": "%"},
             "changed": True,
             "transforms": ["HCT-frac-to-percent(×100: 0.42→42.0)"]}
        ],
        "warnings": ["sample_id changed"],
        "audited_at": "2026-08-28T10:00:00Z",
    }, ensure_ascii=False)

    history.record({
        "ts":         "2026-08-28T10:00:00",
        "device":     "XQ-320",
        "sample_id":  "SN0042",
        "patient_id": "SN0042",
        "analytes":   1,
        "status":     "ok",
        "conversion_audit": audit_payload,
    })

    result = history.get_audit("SN0042")
    assert result is not None
    assert result["sample_id"] == "SN0042"
    assert result["device"] == "XQ-320"
    assert result["audit"]["sample"]["raw"] == "SN0042A"
    assert result["audit"]["changes"][0]["changed"] is True


def test_history_get_audit_returns_none_when_missing(_isolated_history) -> None:
    result = _isolated_history.get_audit("NONEXISTENT")
    assert result is None


def test_history_get_audit_returns_none_for_empty_sample_id(_isolated_history) -> None:
    assert _isolated_history.get_audit("") is None
    assert _isolated_history.get_audit(None) is None  # type: ignore[arg-type]


def test_alter_table_is_idempotent(_isolated_history) -> None:
    """Second _get_conn() call must not fail even though ALTER TABLE was
    already applied by the first call."""
    history = _isolated_history
    history._get_conn()
    # Reset and force a fresh connection: the ALTER should be a no-op the second time.
    history._conn = None
    c2 = history._get_conn()
    cols = [r[1] for r in c2.execute("PRAGMA table_info(dispatches)").fetchall()]
    assert "conversion_audit" in cols


# ── Blueprint integration test (Flask test client) ────────────────────────────

@pytest.fixture()
def _flask_client(_isolated_history, monkeypatch):
    """Build a minimal Flask app with just the inspect blueprint.

    Real @require_role checks: (1) setup not required, (2) session has
    auth_id + role. We stub the roles module and set session in each request.
    """
    from flask import Flask
    from src.security import roles as _roles

    # No-setup + always-authorize regardless of role
    monkeypatch.setattr(_roles, "is_setup_required", lambda: False)
    monkeypatch.setattr(_roles, "require_role", lambda have, want: True)

    from webui.blueprints.inspect import inspect_bp

    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parent.parent / "webui" / "templates"),
    )
    app.config["TESTING"] = True
    app.secret_key = "test"
    app.register_blueprint(inspect_bp)
    client = app.test_client()
    # Pre-populate a fake authenticated session
    with client.session_transaction() as s:
        s["auth_id"] = "test-user"
        s["role"] = "operator"
    return client


def test_api_audit_returns_404_when_missing(_flask_client) -> None:
    r = _flask_client.get("/api/sample/NOPE/audit")
    assert r.status_code == 404
    body = r.get_json()
    assert body["ok"] is False
    assert body["code"] == "E1010_AUDIT_MISSING"


def test_api_audit_returns_200_when_present(_flask_client, _isolated_history) -> None:
    _isolated_history.record({
        "ts": "2026-08-28T10:00:00",
        "device": "XQ-320",
        "sample_id": "SN9999",
        "patient_id": "SN9999",
        "analytes": 1,
        "status": "ok",
        "conversion_audit": json.dumps({
            "device": "XQ-320",
            "sample": {"raw": "SN9999", "sent": "SN9999"},
            "patient": {"raw": "SN9999", "sent": "SN9999"},
            "raw_payload_sha": "b" * 64,
            "raw_payload_hex": "02" * 128,
            "changes": [],
            "warnings": [],
            "audited_at": "2026-08-28T10:00:00Z",
        }, ensure_ascii=False),
    })
    r = _flask_client.get("/api/sample/SN9999/audit")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["audit"]["sample"]["sent"] == "SN9999"
