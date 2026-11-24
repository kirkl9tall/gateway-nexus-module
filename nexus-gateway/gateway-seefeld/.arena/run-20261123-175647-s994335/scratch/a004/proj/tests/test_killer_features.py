"""
Coverage tests for the 15 killer features. One test per module so
regressions on any module cause a specific CI failure.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path



# ── 1. USB auto-discovery ────────────────────────────────────────────────────

def test_usb_scan_returns_list() -> None:
    from src.discovery.usb_auto import scan
    result = scan()
    assert isinstance(result, list)   # empty on non-Linux is fine


# ── 4. WAL ───────────────────────────────────────────────────────────────────

def test_wal_lifecycle(monkeypatch, tmp_path) -> None:
    from src.common import wal
    monkeypatch.setattr(wal, "_DB", tmp_path / "wal.db")
    u = wal.enter("LIS-A", "MSG001", "MSH|test\r")
    assert wal.in_flight_count() == 1
    wal.ack(u)
    assert wal.in_flight_count() == 0


def test_wal_recovers_orphans(monkeypatch, tmp_path) -> None:
    from src.common import wal
    monkeypatch.setattr(wal, "_DB", tmp_path / "wal.db")
    wal.enter("LIS-A", "MSG001", b"MSH|test")
    calls = []
    def _replay(uuid, target, control, payload):
        calls.append((uuid[:8], target, control))
        return "ack"
    report = wal.recover_at_boot(_replay)
    assert report["total"] == 1
    assert report["acked"] == 1


# ── 6. Watchdog ─────────────────────────────────────────────────────────────

def test_watchdog_restarts_silent_reader() -> None:
    from src.common.watchdog import Watchdog
    restarts = []
    def _restart(name): restarts.append(name)
    wd = Watchdog(_restart, silence_threshold_seconds=0.01,
                   check_interval_seconds=0.05)
    wd.register("sysmex")
    time.sleep(0.1)
    wd._tick()
    assert "sysmex" in restarts


def test_watchdog_disables_after_max_restarts() -> None:
    from src.common.watchdog import Watchdog
    wd = Watchdog(lambda n: None, silence_threshold_seconds=0.01,
                   max_restarts_per_window=2, window_seconds=60,
                   check_interval_seconds=0.05)
    wd.register("dead")
    for _ in range(5):
        time.sleep(0.05)
        wd._tick()
    status = {s["name"]: s for s in wd.status()}
    assert status["dead"]["disabled"] is True


# ── 7. Priority queue ────────────────────────────────────────────────────────

def test_priority_queue_evicts_lower_priority() -> None:
    from src.common.priority_queue import SmartQueue

    async def _run():
        q = SmartQueue(maxsize=2)
        # Fill with 2 QC (P3)
        await q.put({"kind": "result", "is_qc": True, "sample_id": "QC1"})
        await q.put({"kind": "result", "is_qc": True, "sample_id": "QC2"})
        assert q.qsize() == 2
        # Add an order (P0) — should evict a QC
        added = await q.put({"kind": "order", "sample_id": "URGENT"})
        assert added is True
        assert q.qsize() == 2

    asyncio.run(_run())


# ── 8. Adaptive breaker ─────────────────────────────────────────────────────

def test_adaptive_breaker_opens_on_failures() -> None:
    from src.transport.adaptive_breaker import BreakerRegistry
    reg = BreakerRegistry()
    b = reg.get("target1")
    b.computed_max_fails = 3
    for _ in range(3):
        b.record_failure()
    assert b.state == "open"


def test_adaptive_breaker_half_opens_after_timeout() -> None:
    from src.transport.adaptive_breaker import BreakerRegistry
    reg = BreakerRegistry()
    b = reg.get("target2")
    b.computed_max_fails = 1
    b.record_failure()
    assert b.state == "open"
    b.opened_at = time.time() - 40
    b.maybe_half_open(min_open_seconds=30)
    assert b.state == "half_open"


# ── 9. Provenance ────────────────────────────────────────────────────────────

def test_provenance_fingerprint_stable() -> None:
    from src.common.provenance import pi_fingerprint
    a = pi_fingerprint()
    b = pi_fingerprint()
    assert a == b
    assert len(a) == 64


def test_provenance_msh_fields_complete() -> None:
    from src.common.provenance import build_msh_provenance_fields
    fields = build_msh_provenance_fields(version="1.3.0")
    assert "MSH-7" in fields
    assert fields["MSH-11"] == "P"
    assert fields["MSH-25"] == "jerumednexus-1.3.0"
    assert len(fields["MSH-24"]) == 32


# ── 10. Multi-target dispatcher ─────────────────────────────────────────────

def test_multi_target_mirror_success_when_one_acks() -> None:
    from src.transport.multi_target import MultiTargetDispatcher, TargetResult

    async def _sender(t, body):
        return TargetResult(target_name=t["name"], ok=(t["name"] == "primary"),
                             latency_ms=10.0)

    targets = [{"name": "primary"}, {"name": "backup"}]
    d = MultiTargetDispatcher(targets, _sender, mode="mirror")

    async def _run():
        results = await d.dispatch(b"MSH|test")
        assert any(r.ok for r in results)
        assert len(results) == 2

    asyncio.run(_run())


def test_multi_target_failover_stops_at_first_success() -> None:
    from src.transport.multi_target import MultiTargetDispatcher, TargetResult
    calls = []

    async def _sender(t, body):
        calls.append(t["name"])
        return TargetResult(target_name=t["name"], ok=(t["name"] == "backup"),
                             latency_ms=10.0)

    targets = [{"name": "primary"}, {"name": "backup"}, {"name": "tertiary"}]
    d = MultiTargetDispatcher(targets, _sender, mode="failover")

    async def _run():
        await d.dispatch(b"MSH|")
        assert calls == ["primary", "backup"]

    asyncio.run(_run())


# ── 5. Universal DSL ─────────────────────────────────────────────────────────

def test_universal_dsl_parses_ha8180t_frame() -> None:
    from src.adapters.universal_dsl import load_spec, parse_message
    spec = load_spec(Path("config/protocols/example_ha8180t.yaml"))
    text = ("H|\\^&|||MENARINI\r"
            "P|1||PAT-42||Mustermann\r"
            "O|1|SN0042\r"
            "R|1|^^^HBA1C^1|5.7|%||N\r"
            "L|1|N\r")
    r = parse_message(spec, text)
    assert r is not None
    assert r["sample_id"] == "SN0042"
    assert r["patient_id"] == "PAT-42"
    assert len(r["observations"]) == 1
    assert r["observations"][0]["value"] == "5.7"


# ── 15. Shadow mode ─────────────────────────────────────────────────────────

def test_shadow_mode_records_without_sending(tmp_path, monkeypatch) -> None:
    from src.common import shadow_mode
    monkeypatch.chdir(tmp_path)
    shadow_mode.configure({"enabled": True, "log_dir": str(tmp_path / "shadow")})
    assert shadow_mode.is_enabled()
    shadow_mode.record("SN0042", "primary_lis", "MSH|test\rOBX|value=42\r")
    files = list((tmp_path / "shadow").glob("*.json"))
    assert len(files) == 1
    shadow_mode.configure(None)


# ── 16. Config versioning ───────────────────────────────────────────────────

def test_config_versioning_snapshot_and_rollback(tmp_path, monkeypatch) -> None:
    from src.common import config_versioning as cv
    monkeypatch.setattr(cv, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cv, "_HISTORY_DB", tmp_path / "history.db")
    f = tmp_path / "test.yaml"
    f.write_text("version: 1")
    v1 = cv.snapshot("test.yaml", actor="test", reason="initial")
    assert v1
    f.write_text("version: 2")
    v2 = cv.snapshot("test.yaml", actor="test", reason="update")
    assert v2 and v2 != v1
    versions = cv.list_versions("test.yaml")
    assert len(versions) == 2
    # Rollback
    cv.rollback(versions[-1]["id"], actor="test")
    assert f.read_text() == "version: 1"


# ── 17. HL7 v2.9 / FHIR R5 ──────────────────────────────────────────────────

def test_hl7_version_normalization() -> None:
    from src.hl7.v29_r5 import normalize_hl7_version, is_v29_or_newer
    assert normalize_hl7_version("2.9") == "2.9"
    assert normalize_hl7_version("2.5") == "2.5"
    assert normalize_hl7_version("garbage") == "2.5"
    assert is_v29_or_newer("2.9")
    assert not is_v29_or_newer("2.5")


# ── 18. Rate limiter + fuzzy + bulk ─────────────────────────────────────────

def test_rate_limiter_throttles_after_capacity() -> None:
    from src.common.rate_limit import RateLimiter
    rl = RateLimiter(capacity=3, per_minute=6)
    ok = [rl.check("src") for _ in range(3)]
    fail = rl.check("src")   # 4th → refused
    assert ok == [True, True, True]
    assert fail is False


def test_fuzzy_recognize_matches_variants() -> None:
    from src.devices.fuzzy_recognize import recognize
    assert recognize("Sysmex_XQ-320") == "sysmex_xq320"
    assert recognize("SYSMEX XQ 320") == "sysmex_xq320"
    assert recognize("totally_random") is None
