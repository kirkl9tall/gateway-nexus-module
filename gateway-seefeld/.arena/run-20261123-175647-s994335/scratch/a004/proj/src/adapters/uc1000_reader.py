"""
src/adapters/uc1000_reader.py
Reads result frames from Menarini UC-1000 urinalysis analyzer.

Protocol: RS-232C serial, HANDSHAKE mode
  UC-1000 sends: <STX> data <ETX> <CSH> <CSL>
  Gateway must reply: <ACK> (0x06)
  UC-1000 then sends: <EOT> (0x04)

Data format: 157 comma-separated fixed-width fields per sample.
Field 1:  Barcode ID (14 bytes, space-padded)
Field 8:  Analysis number
Field 10: Error codes
Field 12: Test strip name
Field 14: Date (YYYY/MM/DD)
Field 16: Time (HH:MM:SS)
Then groups of analyte fields: URO, BLD, BIL, KET, GLU, PRO, pH, NIT, LEU, S.G, CRE, ALB, P/C, A/C, S.G(ref), Color

German parameter names for HL7 output to tomedo.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

log = logging.getLogger("loc200.uc1000")

try:
    import serial_asyncio
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False

from src.common.backpressure import safe_put_sync
from src.common.framing import guard_buffer

# Control characters
STX = 0x02
ETX = 0x03
ACK = 0x06
NAK = 0x15
EOT = 0x04

# ── German parameter map ──────────────────────────────────────────────────────
UC1000_ANALYTES = [
    # (field_offset_in_group, code, german_name, loinc, unit)
    # Groups start at field index 17 (0-based after header fields)
    # Each analyte group: state(1) + mark(1) + qualitative(6) + concentration(6) + R1(5) + space + R2(5) + space + R3(5) = 30 bytes + delimiter
    {"code": "URO",  "name": "Urobilinogen",             "loinc": "20405-7", "unit": "mg/dL"},
    {"code": "BLD",  "name": "Blut",                     "loinc": "5794-3",  "unit": ""},
    {"code": "BIL",  "name": "Bilirubin",                "loinc": "1975-2",  "unit": "mg/dL"},
    {"code": "KET",  "name": "Ketone",                   "loinc": "2514-8",  "unit": "mg/dL"},
    {"code": "GLU",  "name": "Glukose",                  "loinc": "2350-7",  "unit": "mg/dL"},
    {"code": "PRO",  "name": "Protein",                  "loinc": "2888-6",  "unit": "mg/dL"},
    {"code": "PH",   "name": "pH",                       "loinc": "2756-5",  "unit": ""},
    {"code": "NIT",  "name": "Nitrit",                   "loinc": "5802-4",  "unit": ""},
    {"code": "LEU",  "name": "Leukozyten",               "loinc": "5821-4",  "unit": "cells/uL"},
    {"code": "SG",   "name": "Spezifisches Gewicht",     "loinc": "2965-2",  "unit": ""},
    {"code": "CRE",  "name": "Kreatinin",                "loinc": "2160-0",  "unit": "mg/dL"},
    {"code": "ALB",  "name": "Albumin",                  "loinc": "1751-7",  "unit": "mg/L"},
    {"code": "PC",   "name": "Protein/Kreatinin-Quotient","loinc": "13801-4", "unit": "g/gCr"},
    {"code": "AC",   "name": "Albumin/Kreatinin-Quotient","loinc": "9318-7",  "unit": "mg/gCr"},
    {"code": "SGREF","name": "Spez. Gew. (Refraktometer)","loinc": "2965-2",  "unit": ""},
]


class UC1000Reader:
    """
    Async serial reader for Menarini UC-1000 in HANDSHAKE mode.
    Receives STX...ETX frames, sends ACK, parses CSV data.
    """

    def __init__(
        self,
        port: str,
        baudrate: int,
        queue: asyncio.Queue,
        device_name: str = "UC1000 Urinstatus",
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._queue = queue
        self._device_name = device_name
        self._transport = None
        self._protocol = None
        self._stop_event = asyncio.Event()

    async def open(self) -> None:
        if not _SERIAL_AVAILABLE:
            raise RuntimeError(
                "pyserial-asyncio not installed. Run: pip install pyserial-asyncio"
            )
        loop = asyncio.get_event_loop()
        self._transport, self._protocol = await serial_asyncio.create_serial_connection(
            loop,
            lambda: _UC1000Protocol(self._on_frame, self._device_name),
            self._port,
            baudrate=self._baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            rtscts=False,
            dsrdtr=False,
        )
        log.info("[%s] Serial port %s opened at %d baud.",
                 self._device_name, self._port, self._baudrate)

    async def run(self) -> None:
        await self._stop_event.wait()

    async def close(self) -> None:
        self._stop_event.set()
        if self._transport:
            self._transport.close()
        log.info("[%s] Reader closed.", self._device_name)

    def _on_frame(self, data: bytes) -> None:
        """Called by protocol when a complete STX...ETX frame is received."""
        result = self._parse_frame(data)
        if result:
            self._attach_audit(result, data)
            safe_put_sync(self._queue, result, tag=self._device_name)

    def _attach_audit(self, result: dict, raw: bytes) -> None:
        try:
            from src.common.conversion_audit import build_audit_for
            result["conversion_audit"] = build_audit_for(
                device=self._device_name,
                sample_raw=result.get("sample_id", ""),
                sample_sent=result.get("sample_id", ""),
                patient_raw=result.get("patient_id", ""),
                patient_sent=result.get("patient_id", ""),
                raw_payload=raw,
                observations=result.get("observations") or [],
            )
        except Exception as exc:
            log.debug("[%s] audit attach failed: %s", self._device_name, exc)

    def _parse_frame(self, data: bytes) -> Optional[Dict[str, Any]]:
        """Parse UC-1000 CSV frame into result dict."""
        try:
            text = data.decode("ascii", errors="replace")
        except Exception as e:
            log.warning("[%s] Frame decode error: %s", self._device_name, e)
            return None

        # Split by comma — 157 fields expected
        fields = text.split(",")
        if len(fields) < 16:
            log.warning("[%s] Too few fields: %d", self._device_name, len(fields))
            return None

        # Field indices (0-based):
        # 0: Barcode ID (14 bytes)
        # 1: Rack No
        # 2: Tube position
        # 3: Analysis series + number (e.g. "N00000001")
        # 4: Error codes
        # 5: Test strip name
        # 6: Date (YYYY/MM/DD)
        # 7: Time (HH:MM:SS)
        # 8+: analyte groups

        barcode = fields[0].strip()
        # Campo 4 = codici d'errore dell'analizzatore. Veniva letto e buttato
        # via: se una striscia falliva, il referto partiva verso il gestionale
        # come se fosse valido. Ora viene registrato e portato nel risultato,
        # cosi' compare nel Frame Inspector e nei log. I risultati NON vengono
        # scartati -- perderli in silenzio sarebbe peggio che segnalarli.
        error_code = fields[4].strip() if len(fields) > 4 else "0000"
        strip_name = fields[5].strip() if len(fields) > 5 else ""
        date_str = fields[6].strip() if len(fields) > 6 else ""
        time_str = fields[7].strip() if len(fields) > 7 else ""

        # Parse timestamp
        timestamp = datetime.now()
        if date_str and time_str:
            try:
                timestamp = datetime.strptime(
                    f"{date_str} {time_str}", "%Y/%m/%d %H:%M:%S"
                )
            except ValueError:
                pass

        # Sample/patient ID from barcode
        sample_id = barcode if barcode else ""

        result: Dict[str, Any] = {
            "timestamp":    timestamp,
            "sample_id":    sample_id,
            "patient_id":   sample_id,
            "patient_name": "",
            "age":          None,
            "gender":       "",
            "department":   "",
            "disc_name":    strip_name or self._device_name,
            "lot_id":       "",
            "device":       self._device_name,
            "device_error_code": error_code,
            "observations": [],
        }
        if error_code and error_code.strip("0 ") != "":
            log.warning("[%s] Campione %s: l'analizzatore segnala l'errore %s "
                        "-- il referto viene comunque consegnato, verificarlo",
                        self._device_name, sample_id or "?", error_code)

        # Parse analyte groups starting at field index 8
        # Each full analyte group occupies 1 field (state+mark+qual+conc+R1+space+R2+space+R3)
        # BUT the actual field split by comma gives us one entry per analyte
        # Fields 8..22 = URO, BLD, BIL, KET, GLU, PRO, pH, NIT, LEU, S.G, CRE, ALB
        # Fields 23..24 = P/C, A/C (shorter: state+mark+qual+conc only)
        # Field 25 = S.G refractometer
        # Field 26 = urine color

        analyte_field_start = 8

        for i, analyte in enumerate(UC1000_ANALYTES):
            field_idx = analyte_field_start + i
            if field_idx >= len(fields):
                break

            field = fields[field_idx]
            if len(field) < 2:
                continue

            # Field structure: state(1) + mark(1) + qualitative(6) + concentration(6) + ...
            state = field[0] if len(field) > 0 else "1"
            if state == "1":
                # Not analyzed
                continue

            mark = field[1] if len(field) > 1 else " "
            qual = field[2:8].strip() if len(field) > 8 else ""
            conc = field[8:14].strip() if len(field) > 14 else ""

            # Determine flag from mark
            flag = ""
            if mark == "*":
                flag = "H"
            elif mark == "?":
                flag = "A"
            elif mark == "!":
                flag = "AA"

            # Use qualitative value as the reported value
            value = qual if qual else conc
            if not value:
                continue

            # Try numeric parse
            try:
                value_num: Optional[float] = float(re.sub(r"[<>= +]", "", value))
            except (ValueError, TypeError):
                value_num = None

            result["observations"].append({
                "analyte":   analyte["code"],
                "name_de":   analyte["name"],
                "loinc":     analyte["loinc"],
                "value":     value,
                "value_num": value_num,
                "flag":      flag,
                "ref_low":   None,
                "ref_high":  None,
                "unit":      analyte["unit"],
            })

        if not result["observations"]:
            log.warning("[%s] No observations parsed from frame", self._device_name)
            return None

        log.info(
            "[%s] Parsed: sample=%s analytes=%d",
            self._device_name, result["sample_id"], len(result["observations"])
        )
        return result


class _UC1000Protocol(asyncio.Protocol):
    """
    asyncio Protocol for UC-1000 HANDSHAKE mode.
    Accumulates bytes, detects STX...ETX frames, sends ACK.
    """

    def __init__(self, on_frame: callable, device_name: str) -> None:
        self._on_frame  = on_frame
        self._device    = device_name
        self._buf       = bytearray()
        self._in_frame  = False
        self._frame_buf = bytearray()
        self._transport = None

    def connection_made(self, transport) -> None:
        self._transport = transport
        log.debug("[%s] Serial connection established.", self._device)

    def data_received(self, data: bytes) -> None:
        for byte in data:
            if byte == STX:
                # Start of frame
                self._in_frame = True
                self._frame_buf = bytearray()
            elif byte == ETX:
                if self._in_frame:
                    # End of frame — send ACK and process
                    self._in_frame = False
                    frame_data = bytes(self._frame_buf)
                    log.debug("[%s] Frame received (%d bytes), sending ACK",
                              self._device, len(frame_data))
                    if self._transport:
                        self._transport.write(bytes([ACK]))
                    self._on_frame(frame_data)
                    self._frame_buf = bytearray()
            elif byte == EOT:
                log.debug("[%s] EOT received.", self._device)
                self._in_frame = False
                self._frame_buf = bytearray()
            else:
                if self._in_frame:
                    self._frame_buf.append(byte)
                    if not guard_buffer(self._frame_buf, tag=self._device):
                        self._frame_buf = bytearray()
                        self._in_frame = False

    def connection_lost(self, exc: Optional[Exception]) -> None:
        log.warning("[%s] Serial connection lost: %s", self._device, exc)
