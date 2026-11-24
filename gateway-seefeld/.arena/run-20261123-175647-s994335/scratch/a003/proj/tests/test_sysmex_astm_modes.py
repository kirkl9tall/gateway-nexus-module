"""
Regression tests for Sysmex ASTM TCP/IP handshake — both E1381-02 (framed)
and E1381-95 (raw) modes. Frames taken verbatim from the XQ-Series ASTM
Host Interface Specifications v1.4 (R320081) §5 and §6.4.

These test the fix for the production issue at hausarztpraxis2 / loc200-connect02
where the XQ-320 opened a TCP connection but the gateway timed out because it
was hardcoded to wait for ENQ regardless of astm_mode setting.
"""
from __future__ import annotations

import asyncio

import pytest

from src.adapters.sysmex_reader import (
    ACK, ENQ, EOT, ETX, NAK, STX,
    SysmexReader, _has_terminator_l, _parse_astm,
)


# ── E1381-95 raw-mode frames (from spec §6.4 "ASTM E1381-95 mode") ────────

RAW_INQUIRY_MESSAGE = (
    "H|\\^&|||XQ-320^00-00^11001^^^^12345678||||||||E1394-97\r"
    "Q|1|2^1^                    1234567890^B||||20011001153000\r"
    "L|1|N\r"
)

RAW_RESULT_MESSAGE = (
    "H|\\^&|||XQ-320^00-00^11001^^^^12345678||||||||E1394-97\r"
    "P|1|||100|^Muster^Anna||19850101|F\r"
    "O|1||SN0001||R\r"
    "R|1|^^^^WBC^1|7.4|10*3/uL||N||||||20260828093000\r"
    "R|2|^^^^RBC^1|4.8|10*6/uL||N||||||20260828093000\r"
    "R|3|^^^^HGB^1|14.2|g/dL||N||||||20260828093000\r"
    "L|1|N\r"
)


def test_terminator_detector_finds_L_record() -> None:
    assert _has_terminator_l(RAW_INQUIRY_MESSAGE) is True
    assert _has_terminator_l(RAW_RESULT_MESSAGE) is True
    # Partial message without L: not complete yet
    assert _has_terminator_l("H|\\^&|||XQ-320\rP|1\r") is False


def test_parser_accepts_raw_e1381_95_result_message() -> None:
    """Raw records (no framing) must parse cleanly — same _parse_astm code path."""
    result = _parse_astm(RAW_RESULT_MESSAGE, "XQ-320")
    assert result is not None
    assert result["sample_id"] == "SN0001"
    assert len(result["observations"]) == 3
    codes = [o["analyte"] for o in result["observations"]]
    assert set(codes) == {"WBC", "RBC", "HGB"}


# ── E1381-02 framed-mode helpers (spec §4.2.3) ────────────────────────────

def _build_astm_frame(text: str, frame_num: int = 1, final: bool = True) -> bytes:
    """[STX][F#][text][ETX|ETB][CHK1][CHK2][CR][LF] with correct checksum."""
    terminator = ETX if final else 0x17  # ETB
    body = bytes([frame_num + ord("0")]) + text.encode("ascii") + bytes([terminator])
    chk = sum(body) & 0xFF
    trailer = f"{chk:02X}\r\n".encode("ascii")
    return bytes([STX]) + body + trailer


def test_build_frame_checksum_matches_spec_example() -> None:
    """Example from spec §5.3.1: R|1|^^^^WBC^1|... with STX 7 F# → checksum FF-ish."""
    frame = _build_astm_frame("H|\\^&|||XQ-320\r", frame_num=1)
    # Verify: strip STX, then last-4 bytes are CHK1 CHK2 CR LF
    assert frame[0] == STX
    assert frame[-2:] == b"\r\n"
    chk_ascii = frame[-4:-2].decode("ascii")
    body = frame[1:-4]
    calc = sum(body) & 0xFF
    assert int(chk_ascii, 16) == calc


# ── End-to-end async handler test: E1381-02 mode ──────────────────────────

class _MockStreamReader:
    def __init__(self, script: bytes) -> None:
        self._script = script
        self._pos = 0
        self._closed = False

    async def read(self, n: int) -> bytes:
        if self._pos >= len(self._script):
            if self._closed:
                return b""
            self._closed = True
            return b""
        chunk = self._script[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk

    async def readexactly(self, n: int) -> bytes:
        if self._pos + n > len(self._script):
            raise asyncio.IncompleteReadError(partial=b"", expected=n)
        chunk = self._script[self._pos:self._pos + n]
        self._pos += n
        return chunk


class _MockStreamWriter:
    def __init__(self) -> None:
        self.written = bytearray()
        self._closed = False

    def write(self, data: bytes) -> None:
        self.written.extend(data)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        pass

    def get_extra_info(self, key: str):
        return ("127.0.0.1", 12345)


@pytest.mark.asyncio
async def test_e1381_02_handler_acks_enq_then_frame_then_eot() -> None:
    """Full happy-path: ENQ → ACK, framed record → ACK, EOT → done."""
    frame = _build_astm_frame("H|\\^&|||XQ-320\r", frame_num=1)
    script = bytes([ENQ]) + frame + bytes([EOT])
    r = _MockStreamReader(script)
    w = _MockStreamWriter()
    q: asyncio.Queue = asyncio.Queue()

    reader = SysmexReader(
        host="0.0.0.0", port=0, queue=q, device_name="XQ-320-test",
        astm_mode="1381-02", idle_timeout_seconds=1.0,
    )
    await reader._handle_client(r, w)
    # ACK sent for ENQ, then ACK for the frame
    assert w.written.count(bytes([ACK])) == 2


@pytest.mark.asyncio
async def test_e1381_95_handler_reads_raw_message_no_handshake() -> None:
    """Raw-mode (no ENQ/ACK): just read records until L, then dispatch."""
    script = RAW_RESULT_MESSAGE.encode("ascii")
    r = _MockStreamReader(script)
    w = _MockStreamWriter()
    q: asyncio.Queue = asyncio.Queue()

    reader = SysmexReader(
        host="0.0.0.0", port=0, queue=q, device_name="XQ-320-test",
        astm_mode="1381-95", idle_timeout_seconds=0.5,
    )
    await reader._handle_client(r, w)
    # No ACK/NAK bytes should have been written in raw mode
    assert bytes([ACK]) not in w.written
    assert bytes([NAK]) not in w.written
    # Sample enqueued
    assert q.qsize() == 1
    result = q.get_nowait()
    assert result["sample_id"] == "SN0001"
    assert len(result["observations"]) == 3


@pytest.mark.asyncio
async def test_unidirectional_device_does_not_reply_to_query() -> None:
    """XP-300 (unidirectional=True) MUST NOT try to reply to Q records."""
    script = RAW_INQUIRY_MESSAGE.encode("ascii")
    r = _MockStreamReader(script)
    w = _MockStreamWriter()
    q: asyncio.Queue = asyncio.Queue()

    reader = SysmexReader(
        host="0.0.0.0", port=0, queue=q, device_name="XP-300-test",
        astm_mode="1381-95", unidirectional=True, idle_timeout_seconds=0.5,
    )
    await reader._handle_client(r, w)
    # Query was silently ignored — no reply attempted, no result queued
    assert q.qsize() == 0
    # No handshake bytes emitted
    assert len(w.written) == 0


@pytest.mark.asyncio
async def test_e1381_02_nak_on_checksum_mismatch() -> None:
    """A frame with a wrong checksum must be NAK'd, not silently accepted."""
    good_frame = _build_astm_frame("H|\\^&|||XQ-320\r", frame_num=1)
    # Corrupt the checksum bytes (last 4 bytes before were CHK1 CHK2 CR LF)
    bad_frame = good_frame[:-4] + b"00\r\n"
    script = bytes([ENQ]) + bad_frame + bytes([EOT])

    r = _MockStreamReader(script)
    w = _MockStreamWriter()
    q: asyncio.Queue = asyncio.Queue()

    reader = SysmexReader(
        host="0.0.0.0", port=0, queue=q, device_name="XQ-320-test",
        astm_mode="1381-02", idle_timeout_seconds=1.0,
    )
    await reader._handle_client(r, w)
    # ACK for ENQ, then NAK for the bad frame
    assert bytes([ACK]) in w.written
    assert bytes([NAK]) in w.written
