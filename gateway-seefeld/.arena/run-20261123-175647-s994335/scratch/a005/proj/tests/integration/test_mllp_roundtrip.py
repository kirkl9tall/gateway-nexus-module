"""End-to-end: builder -> dispatcher -> real socket -> fake MLLP receiver."""
from __future__ import annotations

from datetime import datetime

import pytest

from config.settings import GatewayConfig, HL7Config, PISTarget
from src.hl7.builder import HL7Builder
from src.transport.dispatcher import Dispatcher


def _make_result():
    return {
        "timestamp":    datetime(2025, 1, 1, 12, 0, 0),
        "sample_id":    "S123",
        "patient_id":   "P123",
        "patient_name": "Mueller Hans",
        "gender":       "M",
        "disc_name":    "K1",
        "lot_id":       "L1",
        "observations": [{
            "analyte":   "AST",
            "value":     "13",
            "value_num": 13.0,
            "flag":      "",
            "ref_low":   15,
            "ref_high":  40,
            "unit":      "U/L",
        }],
    }


@pytest.mark.asyncio
async def test_mllp_roundtrip_ack_accepted(fake_mllp):
    cfg = GatewayConfig(
        targets=[PISTarget(
            name="fake",
            type="generic_hl7_mllp",
            enabled=True,
            host="127.0.0.1",
            port=fake_mllp.port,
            mllp_timeout=3.0,
        )],
        retry_max_attempts=1,
    )
    disp = Dispatcher(cfg)
    builder = HL7Builder(HL7Config(sending_facility="TEST"))
    msg = builder.build_oru_r01(_make_result())

    summary = await disp.dispatch(msg, _make_result())

    assert summary.succeeded == ["fake"]
    assert summary.failed == []
    assert len(fake_mllp.received) == 1
    body = fake_mllp.received[0].decode("utf-8", errors="replace")
    assert "MSH|" in body
    assert "OBX|" in body
    assert msg.control_id in body


@pytest.mark.asyncio
async def test_mllp_roundtrip_ack_reject_marks_failed(fake_mllp_reject):
    cfg = GatewayConfig(
        targets=[PISTarget(
            name="rejector",
            type="generic_hl7_mllp",
            enabled=True,
            host="127.0.0.1",
            port=fake_mllp_reject.port,
            mllp_timeout=3.0,
        )],
        retry_max_attempts=1,
        retry_delay_seconds=0.1,
    )
    disp = Dispatcher(cfg)
    builder = HL7Builder(HL7Config(sending_facility="TEST"))
    msg = builder.build_oru_r01(_make_result())

    summary = await disp.dispatch(msg, _make_result())

    assert summary.succeeded == []
    assert summary.failed == ["rejector"]
    assert "AR" in summary.errors["rejector"]


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold(fake_mllp_reject):
    cfg = GatewayConfig(
        targets=[PISTarget(
            name="unstable",
            type="generic_hl7_mllp",
            enabled=True,
            host="127.0.0.1",
            port=fake_mllp_reject.port,
            mllp_timeout=1.0,
        )],
        retry_max_attempts=1,
        retry_delay_seconds=0.05,
        breaker_threshold=2,
        breaker_recovery_seconds=60.0,
    )
    disp = Dispatcher(cfg)
    builder = HL7Builder(HL7Config(sending_facility="TEST"))
    msg = builder.build_oru_r01(_make_result())

    # First failure
    await disp.dispatch(msg, _make_result())
    # Second failure -- trips breaker
    await disp.dispatch(msg, _make_result())
    # Third call: breaker should be OPEN -> skipped_open, no network hit
    summary = await disp.dispatch(msg, _make_result())
    assert summary.skipped_open == ["unstable"]


@pytest.mark.asyncio
async def test_mllp_unreachable_host_marks_failed():
    cfg = GatewayConfig(
        targets=[PISTarget(
            name="dead",
            type="generic_hl7_mllp",
            enabled=True,
            host="127.0.0.1",
            port=1,   # nothing listens on port 1
            mllp_timeout=1.0,
        )],
        retry_max_attempts=1,
        retry_delay_seconds=0.05,
    )
    disp = Dispatcher(cfg)
    builder = HL7Builder(HL7Config(sending_facility="TEST"))
    msg = builder.build_oru_r01(_make_result())

    summary = await disp.dispatch(msg, _make_result())
    assert summary.succeeded == []
    assert summary.failed == ["dead"]
    assert summary.all_failed
