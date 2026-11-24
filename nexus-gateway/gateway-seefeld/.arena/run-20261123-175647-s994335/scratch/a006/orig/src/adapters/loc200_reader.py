"""
src/adapters/loc200_reader.py
Reads raw frames from LOCMEDT LOC-200 via RS-232, wired LAN or WiFi.

Connection modes
─────────────────────────────────────────────────────────────────────
  serial   RS-232 DB9 cable → USB adapter → Raspberry Pi USB
  network  RJ45 Ethernet cable → switch/router → Raspberry Pi
  wifi     LOC-200 built-in WiFi → same WLAN as RPi
  http     LOC-200 sends HTTP POST to gateway (handled by http_server.py)
─────────────────────────────────────────────────────────────────────

Frame protocol:
  - STX (0x02) … payload … ETX (0x03)  [legacy format]
  - Plain HL7 text (MSH...OBX lines)   [modern LOC-200 firmware]
  - Plain-text lines terminated by sentinel "---END---"
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from config.settings import Loc200Config

try:
    import serial_asyncio
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False

from src.common.backpressure import safe_put_sync
from src.common import trace as _trace

log = logging.getLogger("loc200.reader")

STX = b"\x02"
ETX = b"\x03"
_SENTINEL = b"---END---"
_MAX_FRAME_BYTES = 256 * 1024  # 256 KiB — larger than any realistic result frame

# ── Regex per formato proprietario LOC-200 ────────────────────────────────────
# Reference range accepts either:
#   "15-40"     -> low=15, high=40
#   "<=24"      -> high=24 (no low)
#   "<24"       -> high=24
#   ">=1.0"     -> low=1.0
#   ">1.0"      -> low=1.0
#   ""          -> neither
_RE_KIT_LINE = re.compile(
    r"^(?P<analyte>[A-Za-z0-9_\-/+]+)\s*\|"
    r"\s*(?P<value>[<>=\s\d.]+|-{3})\s*\|"
    r"\s*(?P<arrow>UP|DOWN|HIGH|LOW|[HLhl]?)\s*\|"
    r"\s*(?P<ref>[^|]*?)\s*\|"
    r"\s*(?P<unit>[^\|]+)"
)


def _parse_ref_range(ref: str) -> tuple[Optional[float], Optional[float]]:
    """Parse a LOC-200 reference range into (low, high)."""
    ref = ref.strip()
    if not ref:
        return None, None
    # Upper-only: "<=24", "<24"
    m = re.match(r"^<=?\s*([\d.]+)$", ref)
    if m:
        try:
            return None, float(m.group(1))
        except ValueError:
            return None, None
    # Lower-only: ">=1.0", ">1.0"
    m = re.match(r"^>=?\s*([\d.]+)$", ref)
    if m:
        try:
            return float(m.group(1)), None
        except ValueError:
            return None, None
    # Range: "15-40"
    if "-" in ref:
        parts = ref.split("-", 1)
        try:
            low  = float(parts[0].strip()) if parts[0].strip() else None
            high = float(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else None
            return low, high
        except ValueError:
            return None, None
    return None, None
_RE_SAMPLE_ID  = re.compile(r"Sample\s*ID\s*[:\|]\s*\|?\s*(\S+)", re.I)
_RE_PATIENT_ID = re.compile(r"Patient\s*ID\s*[:\|]\s*\|?\s*(\S+)", re.I)
_RE_NAME       = re.compile(r"^Name\s*[:\|]\s*(.+)", re.I)
_RE_AGE        = re.compile(r"Age\s*[:\|]\s*(\d+)", re.I)
_RE_GENDER     = re.compile(r"Gender\s*[:\|]\s*(Male|Female|M|F)", re.I)
_RE_DISC       = re.compile(r"^(?:Disc\s*(?:Name)?|Kit)\s*[:\|]\s*(.+)", re.I)
_RE_LOT        = re.compile(r"Lot\s*ID\s*[:\|]\s*(\S+)", re.I)
_RE_DEPT       = re.compile(r"Department\s*[:\|]\s*(.+)", re.I)


def _parse_hl7(text: str) -> Optional[Dict[str, Any]]:
    """
    Parsa messaggi HL7 ORU^R01 mandati dal LOC-200 via seriale o rete.
    Formato: MSH|...\rPID|...\rOBR|...\rOBX|...
    """
    lines = [l.strip() for l in text.replace("\r\n", "\r").replace("\n", "\r").split("\r") if l.strip()]

    result: Dict[str, Any] = {
        "timestamp":    datetime.now(),
        "sample_id":    "",
        "patient_id":   "",
        "patient_name": "",
        "age":          None,
        "gender":       "",
        "department":   "",
        "disc_name":    "",
        "lot_id":       "",
        "device":       "",
        "observations": [],
    }

    for line in lines:
        fields = line.split("|")
        seg = fields[0].upper() if fields else ""

        if seg == "PID":
            for idx in [3, 4, 2]:
                if len(fields) > idx and fields[idx].strip():
                    val = fields[idx].strip().split("^")[0].strip()
                    if val:
                        result["patient_id"] = val
                        result["sample_id"]  = val
                        break
            if len(fields) > 5 and fields[5].strip():
                result["patient_name"] = fields[5].strip().replace("^", " ").strip()
            if len(fields) > 8 and fields[8].strip():
                g = fields[8].strip().upper()
                result["gender"] = "M" if g == "M" else ("F" if g == "F" else "")

        elif seg == "OBR":
            if len(fields) > 4 and fields[4].strip():
                sid = fields[4].strip().split("^")[0].strip()
                if sid:
                    result["disc_name"] = sid
            if len(fields) > 3 and fields[3].strip():
                result["sample_id"] = result["sample_id"] or fields[3].strip().split("^")[0]

        elif seg == "OBX":
            if len(fields) < 6:
                continue
            code_field  = fields[3].strip() if len(fields) > 3 else ""
            analyte     = code_field.split("^")[0].strip().upper()
            if not analyte:
                continue
            value_str   = fields[5].strip() if len(fields) > 5 else ""
            unit_raw    = fields[6].strip().split("^")[0] if len(fields) > 6 else ""
            ref_raw     = fields[7].strip() if len(fields) > 7 else ""
            flag_raw    = fields[8].strip() if len(fields) > 8 else ""

            flag = ""
            if flag_raw:
                if "H" in flag_raw.upper():
                    flag = "H"
                elif "L" in flag_raw.upper():
                    flag = "L"

            try:
                value_num: Optional[float] = float(re.sub(r"[<>= ]", "", value_str))
            except (ValueError, TypeError):
                value_num = None

            ref_low = ref_high = None
            if "-" in ref_raw:
                rp = ref_raw.split("-", 1)
                try:
                    ref_low  = float(rp[0].strip())
                    ref_high = float(rp[1].strip())
                except ValueError:
                    pass

            result["observations"].append({
                "analyte":   analyte,
                "name_de":   analyte,
                "loinc":     "99999-9",
                "value":     value_str,
                "value_num": value_num,
                "flag":      flag,
                "ref_low":   ref_low,
                "ref_high":  ref_high,
                "unit":      unit_raw,
            })

    if not result["observations"]:
        return None

    # Imposta device = disc_name se presente
    result["device"] = ""
    return result


class Loc200Reader:
    """
    Async reader. Supports serial (RS-232), wired LAN, WiFi and HTTP.
    """

    def __init__(self, config: Loc200Config, queue: asyncio.Queue,
                 device_name: str = "LOC-200") -> None:
        self._config     = config
        self._queue      = queue
        self._device_name = device_name or "LOC-200"
        self._transport  = None
        self._stop_event = asyncio.Event()
        self._reconnect_task: Optional[asyncio.Task] = None

    async def open(self) -> None:
        ct = self._config.connection_type
        log.info("Opening LOC-200 connection [mode=%s] …", ct)
        if ct == "serial":
            await self._connect_serial()
        elif ct == "network":
            await self._connect_tcp(
                self._config.network.host,
                self._config.network.port,
                self._config.network.timeout,
                self._config.network.reconnect_delay,
            )
        elif ct == "wifi":
            await self._connect_tcp(
                self._config.wifi.host,
                self._config.wifi.port,
                self._config.wifi.timeout,
                self._config.wifi.reconnect_delay,
            )
        else:
            pass  # http mode handled by gateway

    async def run(self) -> None:
        await self._stop_event.wait()

    async def close(self) -> None:
        self._stop_event.set()
        if self._reconnect_task:
            self._reconnect_task.cancel()
        if self._transport:
            self._transport.close()
        log.info("LOC-200 reader closed.")

    async def _connect_serial(self) -> None:
        """
        Non-blocking: try once, then retry in background if the port isn't
        there yet. Keeps the gateway alive so the WebUI, discovery and HTTP
        ingest stay usable even before an analyzer is physically plugged in.
        The reconnect loop stops as soon as it succeeds or on shutdown.
        """
        if not _SERIAL_AVAILABLE:
            log.warning("pyserial-asyncio not installed -- LOC-200 serial disabled. "
                        "Run: pip install pyserial-asyncio")
            return
        cfg = self._config.serial

        async def _try_open() -> bool:
            log.info("RS-232: %s  %d %d%s%s",
                     cfg.port, cfg.baudrate, cfg.bytesize, cfg.parity, int(cfg.stopbits))
            loop = asyncio.get_event_loop()
            try:
                self._transport, _ = await serial_asyncio.create_serial_connection(
                    loop,
                    lambda: _FrameProtocol(self._on_frame, self._on_connection_lost),
                    cfg.port,
                    baudrate  = cfg.baudrate,
                    bytesize  = cfg.bytesize,
                    parity    = cfg.parity,
                    stopbits  = cfg.stopbits,
                    timeout   = cfg.timeout,
                )
                log.info("RS-232 port open: %s", cfg.port)
                return True
            except (FileNotFoundError, OSError, Exception) as exc:
                log.warning("LOC-200 serial %s not available: %s -- will retry every 10s.",
                            cfg.port, exc)
                return False

        if await _try_open():
            return

        async def _reconnect_loop() -> None:
            while not self._stop_event.is_set():
                await asyncio.sleep(10.0)
                if self._stop_event.is_set():
                    return
                if await _try_open():
                    return

        self._reconnect_task = asyncio.create_task(
            _reconnect_loop(), name="loc200-serial-reconnect"
        )

    async def _connect_tcp(self, host, port, timeout, reconnect_delay):
        """
        Start a reconnect loop for TCP mode.  Does not block startup: the loop
        keeps trying in the background so a device that comes online later
        is picked up automatically.  On boot we log clearly whether the first
        attempt succeeded (INFO) or is still pending (WARNING).
        """
        async def _do_connect() -> None:
            while not self._stop_event.is_set():
                try:
                    log.info("TCP -> %s:%d ...", host, port)
                    loop = asyncio.get_event_loop()
                    transport, _ = await asyncio.wait_for(
                        loop.create_connection(
                            lambda: _FrameProtocol(
                                self._on_frame,
                                lambda exc: asyncio.ensure_future(_do_connect()),
                            ),
                            host, port,
                        ),
                        timeout=timeout,
                    )
                    self._transport = transport
                    log.info("TCP connected to %s:%d", host, port)
                    return
                except Exception as exc:
                    log.warning(
                        "TCP connection to %s:%d failed: %s -- retrying in %.0fs",
                        host, port, exc, reconnect_delay,
                    )
                    await asyncio.sleep(reconnect_delay)

        self._reconnect_task = asyncio.ensure_future(_do_connect())
        # Give the first connect attempt up to `timeout` seconds so the
        # startup log accurately reports success/pending -- but never fail
        # startup if the device is offline; the loop keeps trying.
        deadline = int(max(1, timeout) * 2)
        for _ in range(deadline):
            if self._transport is not None:
                return
            await asyncio.sleep(0.5)
        log.warning(
            "TCP %s:%d not connected after %.0fs -- reconnect loop still active.",
            host, port, float(deadline) / 2,
        )

    def _on_frame(self, raw_frame: bytes) -> None:
        _trace.record("LOC-200", "in", raw_frame)
        if self._config.debug_raw_frames:
            log.debug("RAW FRAME (%d bytes):\n%s", len(raw_frame),
                      raw_frame.decode("utf-8", errors="replace"))
        try:
            result = self._parse_frame(raw_frame)
            if result and result.get("observations"):
                # Name that appears in the gestionale (MSH-3). The parser leaves
                # "device" empty, which made HL7 fall back to the generic
                # "LOC200_GW"; use the configured device name instead.
                result["device"] = self._device_name
                log.info("LOC-200 parsed: sample=%s patient=%s analytes=%d",
                         result.get("sample_id", "?"),
                         result.get("patient_id", "?"),
                         len(result["observations"]))
                try:
                    from src.common.conversion_audit import build_audit_for
                    result["conversion_audit"] = build_audit_for(
                        device="LOC-200",
                        sample_raw=result.get("sample_id", ""),
                        sample_sent=result.get("sample_id", ""),
                        patient_raw=result.get("patient_id", ""),
                        patient_sent=result.get("patient_id", ""),
                        raw_payload=raw_frame,
                        observations=result["observations"],
                    )
                except Exception as exc:
                    log.debug("audit attach failed: %s", exc)
                safe_put_sync(self._queue, result, tag="loc200")
            else:
                log.warning("Frame had no parsable observations – skipped.")
        except Exception as exc:
            log.error("Frame parse error: %s", exc, exc_info=True)

    def _on_connection_lost(self, exc: Optional[Exception]) -> None:
        if exc:
            log.error("Connection lost: %s", exc)
        else:
            log.warning("Connection closed by remote device.")

    @staticmethod
    def _parse_frame(raw: bytes) -> Optional[Dict[str, Any]]:
        text  = raw.decode("utf-8", errors="replace")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        # ── Prova prima il formato HL7 ────────────────────────────────────────
        if any(l.startswith("MSH") for l in lines) or any(l.startswith("OBX") for l in lines):
            return _parse_hl7(text)

        # ── Formato proprietario LOC-200 ──────────────────────────────────────
        result: Dict[str, Any] = {
            "timestamp":    datetime.now(),
            "sample_id":    "",
            "patient_id":   "",
            "patient_name": "",
            "age":          None,
            "gender":       "",
            "department":   "",
            "disc_name":    "",
            "lot_id":       "",
            "device":       "LOC-200",
            "observations": [],
        }
        for line in lines:
            if m := _RE_SAMPLE_ID.search(line):
                result["sample_id"] = m.group(1)
            elif m := _RE_PATIENT_ID.search(line):
                result["patient_id"] = m.group(1)
            elif m := _RE_NAME.search(line):
                result["patient_name"] = m.group(1).strip()
            elif m := _RE_AGE.search(line):
                result["age"] = int(m.group(1))
            elif m := _RE_GENDER.search(line):
                g = m.group(1).upper()
                result["gender"] = "M" if g.startswith("M") else "F"
            elif m := _RE_DISC.search(line):
                result["disc_name"] = m.group(1).strip()
                result["device"]    = result["disc_name"]
            elif m := _RE_LOT.search(line):
                result["lot_id"] = m.group(1)
            elif m := _RE_DEPT.search(line):
                result["department"] = m.group(1).strip()
            elif m := _RE_KIT_LINE.match(line):
                value_str = m.group("value").strip()
                arrow     = m.group("arrow").strip().upper()
                flag      = "H" if arrow in ("UP", "H", "HIGH") else (
                            "L" if arrow in ("DOWN", "L", "LOW") else "")
                try:
                    value_num: Optional[float] = float(re.sub(r"[<>=\s]", "", value_str))
                except ValueError:
                    value_num = None
                ref_low, ref_high = _parse_ref_range(m.group("ref"))
                result["observations"].append({
                    "analyte":   m.group("analyte").strip().upper(),
                    "name_de":   m.group("analyte").strip().upper(),
                    "loinc":     "99999-9",
                    "value":     value_str,
                    "value_num": value_num,
                    "flag":      flag,
                    "ref_low":   ref_low,
                    "ref_high":  ref_high,
                    "unit":      m.group("unit").strip(),
                })

        if not result["observations"]:
            log.warning("Frame had no parsable observations – skipped.")
            return None
        return result


class _FrameProtocol(asyncio.Protocol):
    """
    asyncio Protocol: accumula bytes e emette frame completi.
    Supporta:
    - STX/ETX framing (formato legacy)
    - HL7 plain text (MSH...OBX, termina con timeout o fine stream)
    - Plain-text con sentinel ---END---
    """

    def __init__(
        self,
        on_frame: Callable[[bytes], None],
        on_lost:  Callable[[Optional[Exception]], None],
    ) -> None:
        self._on_frame = on_frame
        self._on_lost  = on_lost
        self._buf      = bytearray()
        self._in_frame = False
        self._hl7_mode = False
        self._hl7_timer: Optional[asyncio.TimerHandle] = None

    def _guard_buffer(self) -> bool:
        """Drop buffer with a warning if it exceeds the hard cap."""
        if len(self._buf) > _MAX_FRAME_BYTES:
            log.warning(
                "Frame buffer exceeded %d bytes (%d) — dropping to avoid OOM.",
                _MAX_FRAME_BYTES, len(self._buf),
            )
            self._buf.clear()
            self._in_frame = False
            self._hl7_mode = False
            if self._hl7_timer:
                self._hl7_timer.cancel()
                self._hl7_timer = None
            return False
        return True

    def data_received(self, data: bytes) -> None:
        for byte in data:
            b = bytes([byte])
            if b == STX:
                self._buf.clear()
                self._in_frame = True
                self._hl7_mode = False
            elif b == ETX and self._in_frame:
                self._in_frame = False
                if self._buf:
                    self._on_frame(bytes(self._buf))
                self._buf.clear()
            elif self._in_frame:
                self._buf.extend(b)
                if not self._guard_buffer():
                    continue
            else:
                # Plain text mode — accumula
                self._buf.extend(b)
                if not self._guard_buffer():
                    continue

                # Rileva inizio messaggio HL7
                text_so_far = self._buf.decode("utf-8", errors="replace")
                if not self._hl7_mode and ("MSH|" in text_so_far or "OBX|" in text_so_far):
                    self._hl7_mode = True

                if self._hl7_mode:
                    # Resetta timer ad ogni byte ricevuto
                    if self._hl7_timer:
                        self._hl7_timer.cancel()
                    try:
                        loop = asyncio.get_event_loop()
                        self._hl7_timer = loop.call_later(0.5, self._flush_hl7)
                    except Exception:
                        pass
                elif _SENTINEL in self._buf:
                    idx   = self._buf.index(_SENTINEL)
                    frame = bytes(self._buf[:idx])
                    if frame.strip():
                        self._on_frame(frame)
                    self._buf = self._buf[idx + len(_SENTINEL):]

    def _flush_hl7(self) -> None:
        """Invia il buffer HL7 accumulato dopo 500ms di silenzio."""
        if self._buf and self._hl7_mode:
            frame = bytes(self._buf)
            self._buf.clear()
            self._hl7_mode = False
            self._hl7_timer = None
            if frame.strip():
                self._on_frame(frame)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        # Flush eventuale buffer HL7 rimasto
        if self._buf and self._hl7_mode:
            self._on_frame(bytes(self._buf))
            self._buf.clear()
        self._on_lost(exc)
