"""
src/adapters/reflotron_reader.py
Reader for Roche Reflotron Plus (dry chemistry, 17 analytes: GLU, CHOL, TG,
HDL, LDL, GGT, AST, ALT, LDH, CK, AMY, UA, UREA, CREA, HGB, BIL, ALB).

Protocol (verified — see docs/devices/RESEARCH.md § "Roche Reflotron Plus"):
  * RS-232, 9600 or 4800 baud, 8-N-1, no handshake
  * ASCII output, one record per line, semicolon-separated
  * Frame:  date;time;patient_id;test_code;value;unit;flag<CR><LF>

Example (single line):
  27.08.2026;10:35:12;PAT-42;GLU;5.6;mmol/L;N

Multi-analyte samples arrive as multiple consecutive lines sharing the same
patient_id — this adapter groups them by (date, time, patient_id) and
flushes when the tail is idle for `flush_after_idle` seconds (default 3s).
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger("loc200.reflotron")

try:
    import serial_asyncio
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False

from src.common.backpressure import safe_put_sync
from src.common.framing import guard_buffer

# ── German parameter map + LOINC ─────────────────────────────────────────────
REFLOTRON_MAP: Dict[str, Dict[str, str]] = {
    "GLU":  {"name": "Glukose",            "loinc": "2345-7",  "unit": "mg/dL"},
    "CHOL": {"name": "Cholesterin gesamt", "loinc": "2093-3",  "unit": "mg/dL"},
    "TG":   {"name": "Triglyceride",       "loinc": "2571-8",  "unit": "mg/dL"},
    "HDL":  {"name": "HDL-Cholesterin",    "loinc": "2085-9",  "unit": "mg/dL"},
    "LDL":  {"name": "LDL-Cholesterin",    "loinc": "2089-1",  "unit": "mg/dL"},
    "GGT":  {"name": "Gamma-GT",           "loinc": "2324-2",  "unit": "U/L"},
    "AST":  {"name": "AST (GOT)",          "loinc": "1920-8",  "unit": "U/L"},
    "ALT":  {"name": "ALT (GPT)",          "loinc": "1742-6",  "unit": "U/L"},
    "LDH":  {"name": "LDH",                "loinc": "2532-0",  "unit": "U/L"},
    "CK":   {"name": "Kreatinkinase",      "loinc": "2157-6",  "unit": "U/L"},
    "AMY":  {"name": "Amylase",            "loinc": "1798-8",  "unit": "U/L"},
    "UA":   {"name": "Harnsaeure",         "loinc": "3084-1",  "unit": "mg/dL"},
    "UREA": {"name": "Harnstoff",          "loinc": "3094-0",  "unit": "mg/dL"},
    "CREA": {"name": "Kreatinin",          "loinc": "2160-0",  "unit": "mg/dL"},
    "HGB":  {"name": "Haemoglobin",        "loinc": "718-7",   "unit": "g/dL"},
    "BIL":  {"name": "Bilirubin",          "loinc": "1975-2",  "unit": "mg/dL"},
    "ALB":  {"name": "Albumin",            "loinc": "1751-7",  "unit": "g/dL"},
}

_LINE_RE = re.compile(
    r"^\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*;\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*;"
    r"\s*([^;]*)\s*;\s*([A-Za-z0-9]+)\s*;\s*([-+0-9.,<>]+)\s*;\s*([^;]*)"
    r"(?:\s*;\s*([HLN*!]?))?\s*$"
)


def _parse_line(line: str, device_name: str) -> Optional[Dict[str, Any]]:
    m = _LINE_RE.match(line)
    if not m:
        return None
    date, time, patient, code, value, unit, flag = m.groups()
    code_norm = code.strip().upper()
    mapped = REFLOTRON_MAP.get(code_norm, {})
    try:
        value_num = float(value.replace(",", ".").lstrip("<>= "))
    except (ValueError, TypeError):
        value_num = None
    return {
        "date":       date.strip(),
        "time":       time.strip(),
        "patient_id": patient.strip(),
        "code":       code_norm,
        "name_de":    mapped.get("name", code_norm),
        "loinc":      mapped.get("loinc", "99999-9"),
        "value":      value.strip(),
        "value_num":  value_num,
        "unit":       (unit or "").strip() or mapped.get("unit", ""),
        "flag":       (flag or "").strip().upper() if flag else "",
    }


class _ReflotronProtocol(asyncio.Protocol):
    def __init__(self, on_line, device_name: str) -> None:
        self._on_line = on_line
        self._device  = device_name
        self._buf     = bytearray()

    def connection_made(self, transport) -> None:
        log.info("[%s] Serial connection established.", self._device)

    def data_received(self, data: bytes) -> None:
        self._buf.extend(data)
        if not guard_buffer(self._buf, tag=self._device):
            self._buf.clear()
            return
        while b"\n" in self._buf:
            raw, _, rest = self._buf.partition(b"\n")
            self._buf = bytearray(rest)
            text = raw.decode("ascii", errors="ignore").rstrip("\r").strip()
            if text:
                self._on_line(text)

    def connection_lost(self, exc) -> None:
        if exc:
            log.error("[%s] Serial connection lost: %s", self._device, exc)


class ReflotronReader:
    """Reflotron Plus serial adapter (semicolon-CSV, one record per line)."""

    def __init__(
        self,
        port: str,
        baudrate: int,
        queue: asyncio.Queue,
        device_name: str = "Roche Reflotron Plus",
        flush_after_idle: float = 3.0,
    ) -> None:
        self._port         = port
        self._baudrate     = baudrate
        self._queue        = queue
        self._device_name  = device_name
        self._flush_idle   = flush_after_idle
        self._transport    = None
        self._buffer: List[Dict[str, Any]] = []
        self._current_key: Optional[str] = None
        self._flush_task: Optional[asyncio.Task] = None
        self._stop        = asyncio.Event()

    async def open(self) -> None:
        if not _SERIAL_AVAILABLE:
            raise RuntimeError("pyserial-asyncio non installato.")
        loop = asyncio.get_event_loop()
        self._transport, _ = await serial_asyncio.create_serial_connection(
            loop,
            lambda: _ReflotronProtocol(self._handle_line, self._device_name),
            self._port,
            baudrate = self._baudrate,
            bytesize = 8,
            parity   = "N",
            stopbits = 1,
        )
        log.info("[%s] Listening on %s @ %d baud", self._device_name, self._port, self._baudrate)

    async def run(self) -> None:
        await self._stop.wait()

    async def close(self) -> None:
        self._stop.set()
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        if self._transport:
            self._transport.close()
        if self._buffer:
            self._emit()

    def _handle_line(self, text: str) -> None:
        rec = _parse_line(text, self._device_name)
        if not rec:
            log.warning("[%s] Line non-parsable, ignoring: %r", self._device_name, text[:120])
            return
        key = f"{rec['date']}|{rec['time']}|{rec['patient_id']}"
        if self._current_key and key != self._current_key and self._buffer:
            self._emit()
        self._current_key = key
        self._buffer.append(rec)
        # (re)start idle flush timer
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._flush_task = loop.create_task(self._flush_after_idle())

    async def _flush_after_idle(self) -> None:
        try:
            await asyncio.sleep(self._flush_idle)
        except asyncio.CancelledError:
            return
        if self._buffer:
            self._emit()

    def _emit(self) -> None:
        if not self._buffer:
            return
        first = self._buffer[0]
        observations = [{
            "analyte":   r["code"],
            "name_de":   r["name_de"],
            "loinc":     r["loinc"],
            "value":     r["value"],
            "value_num": r["value_num"],
            "unit":      r["unit"],
            "flag":      r["flag"],
            "ref_low":   None,
            "ref_high":  None,
        } for r in self._buffer]
        result = {
            "timestamp":    datetime.now(),
            "sample_id":    first["patient_id"],
            "patient_id":   first["patient_id"],
            "patient_name": "",
            "age":          None,
            "gender":       "",
            "department":   "",
            "disc_name":    "Reflotron",
            "lot_id":       "",
            "device":       self._device_name,
            "observations": observations,
        }
        log.info("[%s] Emit sample=%s analytes=%d",
                 self._device_name, first["patient_id"], len(observations))
        try:
            from src.common.conversion_audit import build_audit_for
            raw = "\n".join(f"{r['date']};{r['time']};{r['patient_id']};"
                            f"{r['code']};{r['value']};{r['unit']};{r['flag']}"
                            for r in self._buffer).encode("ascii", errors="replace")
            result["conversion_audit"] = build_audit_for(
                device=self._device_name,
                sample_raw=first["patient_id"],
                sample_sent=first["patient_id"],
                patient_raw=first["patient_id"],
                patient_sent=first["patient_id"],
                raw_payload=raw,
                observations=observations,
            )
        except Exception as exc:
            log.debug("[%s] audit attach failed: %s", self._device_name, exc)
        safe_put_sync(self._queue, result, tag=self._device_name)
        self._buffer = []
        self._current_key = None
