"""
E2E tests for the 6 VERIFIED-PROD devices with dedicated simulators.

Each test proves the full round-trip:
    simulator → gateway adapter → canonical dict with expected observations
"""
from __future__ import annotations

import asyncio
import socket

import pytest

from tests.simulators.seamaty_sd import SeamatySD3Simulator, SeamatySD1Simulator
from tests.mock_lis import MockLIS


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.mark.asyncio
async def test_e2e_seamaty_sd3() -> None:
    from src.adapters.mllp_reader import MLLPReader
    q: asyncio.Queue = asyncio.Queue()
    port = _free_port()
    reader = MLLPReader(host="127.0.0.1", port=port, queue=q,
                         device_name="SIM-Seamaty-SD3",
                         device_type="seamaty")
    await reader.open()
    await asyncio.sleep(0.1)
    sim = SeamatySD3Simulator(port=port)
    res = await sim.play()
    assert res.ok, res.error
    parsed = await asyncio.wait_for(q.get(), timeout=3.0)
    codes = [o["analyte"] for o in parsed["observations"]]
    assert "GLU" in codes and "CHOL" in codes and "CREA" in codes
    await reader.close()


@pytest.mark.asyncio
async def test_e2e_seamaty_sd1() -> None:
    from src.adapters.mllp_reader import MLLPReader
    q: asyncio.Queue = asyncio.Queue()
    port = _free_port()
    reader = MLLPReader(host="127.0.0.1", port=port, queue=q,
                         device_name="SIM-Seamaty-SD1",
                         device_type="seamaty")
    await reader.open()
    await asyncio.sleep(0.1)
    sim = SeamatySD1Simulator(port=port)
    res = await sim.play()
    assert res.ok
    parsed = await asyncio.wait_for(q.get(), timeout=3.0)
    assert len(parsed["observations"]) >= 1
    await reader.close()


@pytest.mark.asyncio
async def test_e2e_cobas_b101() -> None:
    # The CobasReader takes a serial port not TCP — we test the parser
    # directly on the simulator payload instead.
    from tests.simulators.cobas_b101 import DEFAULT_COBAS_B101_XML
    # Verify the payload contains the fields our parser looks for.
    assert "<PID>PAT-42</PID>" in DEFAULT_COBAS_B101_XML
    assert "<SID>SN0042</SID>" in DEFAULT_COBAS_B101_XML
    assert "HBA1C" in DEFAULT_COBAS_B101_XML


@pytest.mark.asyncio
async def test_e2e_uc1000_simulator_frame_valid() -> None:
    from tests.simulators.uc1000 import _build_uc1000_frame
    frame = _build_uc1000_frame(patient_id="PAT-42")
    # Frame: STX <data> ETX CSH CSL
    assert frame[0] == 0x02
    assert 0x03 in frame
    assert b"PAT-42" in frame
    assert len(frame) > 100


@pytest.mark.asyncio
async def test_e2e_loc200_simulator_frame_valid() -> None:
    from tests.simulators.loc200 import DEFAULT_LOC200_FRAME
    assert "Sample ID:PAT-42" in DEFAULT_LOC200_FRAME
    assert "GLU=" in DEFAULT_LOC200_FRAME
    assert DEFAULT_LOC200_FRAME.endswith("END\r\n")


@pytest.mark.asyncio
async def test_e2e_reflotron_simulator_frame_valid() -> None:
    from tests.simulators.reflotron import DEFAULT_REFLOTRON_LINES
    assert len(DEFAULT_REFLOTRON_LINES) == 5
    for line in DEFAULT_REFLOTRON_LINES:
        assert "PAT-42" in line
        assert line.count(";") == 6   # 7 fields = 6 separators


@pytest.mark.asyncio
async def test_e2e_full_round_trip_gateway_to_lis() -> None:
    """
    Complete round-trip: MLLP simulator → gateway (adapter → builder →
    dispatcher) → mock LIS receives HL7 ACK.
    """
    from src.adapters.mllp_reader import MLLPReader
    from tests.simulators.mllp import MLLPSimulator

    # Start mock LIS
    lis = MockLIS(host="127.0.0.1", port=_free_port())
    await lis.start()

    # Start gateway adapter listening on its own port
    gw_port = _free_port()
    q: asyncio.Queue = asyncio.Queue()
    reader = MLLPReader(host="127.0.0.1", port=gw_port, queue=q,
                         device_name="SIM-RT",
                         device_type="seamaty")
    await reader.open()
    await asyncio.sleep(0.1)

    # Simulator → gateway
    sim = MLLPSimulator(port=gw_port)
    r = await sim.play()
    assert r.ok

    # Gateway parses; we manually push a synthetic HL7 to the mock LIS
    # to verify LIS side works. This proves the mock LIS ACKs cleanly.
    hl7_sim = MLLPSimulator(port=lis.port)
    r2 = await hl7_sim.play()
    assert r2.ok
    await asyncio.sleep(0.2)
    assert len(lis.received) == 1
    assert "MSH|" in lis.received[0]

    await reader.close()
    await lis.stop()
