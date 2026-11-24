"""
Coverage-boost tests for src/common/{health,migrations,structured_log,idempotency}
— modules wired up in v1.3.0 that had no dedicated tests yet.
"""
from __future__ import annotations

import json
import logging
import sqlite3

import pytest


# ── structured_log ──────────────────────────────────────────────────────────

def test_json_formatter_emits_valid_json_line() -> None:
    from src.common.structured_log import JsonLineFormatter

    fmt = JsonLineFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="x", lineno=1,
        msg="hello %s", args=("world",), exc_info=None,
    )
    out = fmt.format(record)
    data = json.loads(out)
    assert data["level"] == "INFO"
    assert data["logger"] == "test"
    assert data["msg"] == "hello world"
    assert "ts" in data and data["ts"].endswith("Z")


def test_json_formatter_includes_extra_kwargs() -> None:
    from src.common.structured_log import JsonLineFormatter

    fmt = JsonLineFormatter()
    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname="x", lineno=1,
        msg="msg", args=(), exc_info=None,
    )
    record.device = "sysmex_xq320"       # type: ignore[attr-defined]
    record.sample_hash = "a6bc44b3"      # type: ignore[attr-defined]
    out = fmt.format(record)
    data = json.loads(out)
    assert data["device"] == "sysmex_xq320"
    assert data["sample_hash"] == "a6bc44b3"


def test_json_formatter_handles_non_serializable_via_repr() -> None:
    from src.common.structured_log import JsonLineFormatter

    class Weird:
        def __repr__(self) -> str:
            return "Weird<x>"
    fmt = JsonLineFormatter()
    record = logging.LogRecord("t", logging.INFO, "x", 1, "msg", (), None)
    record.thing = Weird()               # type: ignore[attr-defined]
    out = fmt.format(record)
    data = json.loads(out)
    assert data["thing"] == "Weird<x>"


def test_configure_root_is_idempotent(monkeypatch) -> None:
    from src.common.structured_log import configure_root

    root = logging.getLogger()
    root.handlers = []
    monkeypatch.setenv("LOG_FORMAT", "json")
    configure_root(level="INFO")
    configure_root(level="INFO")   # second call must not add a second handler
    marked = sum(1 for h in root.handlers if getattr(h, "_jerumednexus_configured", False))
    assert marked == 1
    root.handlers = []


# ── health ──────────────────────────────────────────────────────────────────

def test_livez_always_alive() -> None:
    from src.common.health import livez
    status, body = livez()
    assert status == 200
    assert body["status"] == "alive"


def test_readyz_ok_when_no_state(tmp_path, monkeypatch) -> None:
    from src.common import health as health_mod
    monkeypatch.chdir(tmp_path)
    # No health/breakers/dlq files present — should return ready
    status, body = health_mod.readyz()
    assert status == 200
    assert body["status"] == "ready"


def test_readyz_reports_offline_devices(tmp_path, monkeypatch) -> None:
    from src.common import health as health_mod
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "logs" / "health.json").write_text(json.dumps({
        "devices": {
            "sysmex_xq320": {"state": "ok"},
            "cobas_b101":   {"state": "offline"},
        }
    }))
    status, body = health_mod.readyz()
    assert status == 503
    assert body["status"] == "unready"
    assert any("cobas_b101" in r for r in body["reasons"])


def test_readyz_reports_dlq_backlog(tmp_path, monkeypatch) -> None:
    from src.common import health as health_mod
    monkeypatch.chdir(tmp_path)
    dlq = tmp_path / "logs" / "dead_letter"
    dlq.mkdir(parents=True)
    for i in range(501):
        (dlq / f"m{i}.meta.json").write_text("{}")
    status, body = health_mod.readyz()
    assert status == 503
    assert any("DLQ backlog" in r for r in body["reasons"])


# ── migrations ──────────────────────────────────────────────────────────────

def test_migrations_apply_creates_schema(tmp_path) -> None:
    from src.common.migrations import apply

    db = tmp_path / "history.db"
    v = apply(db)
    assert v >= 3   # our current highest known migration
    with sqlite3.connect(db) as c:
        tables = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
    assert "dispatches" in tables
    assert "audit_events" in tables
    assert "_schema" in tables


def test_migrations_are_idempotent(tmp_path) -> None:
    from src.common.migrations import apply

    db = tmp_path / "h.db"
    v1 = apply(db)
    v2 = apply(db)
    assert v1 == v2   # no double-apply, no re-execution


def test_migrations_add_error_code_column(tmp_path) -> None:
    from src.common.migrations import apply

    db = tmp_path / "h.db"
    apply(db)
    with sqlite3.connect(db) as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(dispatches)").fetchall()]
    assert "error_code" in cols


# ── idempotency ─────────────────────────────────────────────────────────────

@pytest.fixture()
def _isolated_idem(tmp_path, monkeypatch):
    from src.common import idempotency
    monkeypatch.setattr(idempotency, "_DB", tmp_path / "idem.db")
    yield idempotency


def test_idempotency_store_and_replay(_isolated_idem) -> None:
    idem = _isolated_idem
    body = b'{"hl7":"MSH|..."}'
    idem.store("key-1", body, 202, {"ok": True, "id": 42})
    got = idem.get("key-1", body)
    assert got is not None
    status, response = got
    assert status == 202
    assert response["id"] == 42


def test_idempotency_returns_none_for_missing_key(_isolated_idem) -> None:
    assert _isolated_idem.get("no-such-key", b"any") is None


def test_idempotency_refuses_same_key_different_body(_isolated_idem) -> None:
    idem = _isolated_idem
    idem.store("k1", b"body-A", 202, {"ok": True})
    result = idem.get("k1", b"body-DIFFERENT")
    assert result is not None
    status, response = result
    assert response["error"] == "E5001"


def test_idempotency_purge_expired(_isolated_idem) -> None:
    idem = _isolated_idem
    idem.store("old-key", b"x", 200, {})
    # TTL of 0 seconds → everything is expired
    n = idem.purge_expired(ttl_seconds=0)
    assert n == 1
    assert idem.get("old-key", b"x") is None
