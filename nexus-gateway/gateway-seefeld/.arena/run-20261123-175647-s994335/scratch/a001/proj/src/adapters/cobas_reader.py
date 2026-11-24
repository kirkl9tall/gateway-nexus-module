"""
src/adapters/cobas_reader.py
Roche Cobas b 101 — POCT1-A2 XML protocol over USB serial (/dev/ttyACM0).

Protocol flow:
  1. Cobas sends HEL.R01 (hello/connect)
  2. Gateway replies with HEL.R01 acknowledgement
  3. Cobas sends result data as OBS.R01 XML messages
  4. Cobas sends END.R01 (session end)
  5. Gateway replies with END.R01 acknowledgement

Result XML example:
  <OBS.R01>
    <PAT><PAT.patient_id V="1234"/></PAT>
    <OBS>
      <OBS.test_cd V="HBA1C"/>
      <OBS.value V="5.8"/>
      <OBS.units_cd V="%"/>
    </OBS>
  </OBS.R01>
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, Optional

from src.common.backpressure import safe_put_sync
from src.common.framing import guard_str_buffer

log = logging.getLogger("loc200.cobas")

# ── German parameter map ──────────────────────────────────────────────────────
COBAS_TEST_MAP: Dict[str, Dict] = {
    "HBA1C":   {"name": "HbA1c - Glykiertes Haemoglobin",  "unit": "%",       "loinc": "4548-4",  "ref": "4.0-5.6"},
    "TC":      {"name": "Cholesterin gesamt",               "unit": "mmol/L",  "loinc": "2093-3",  "ref": "0-5.18"},
    "CHOL":    {"name": "Cholesterin gesamt",               "unit": "mmol/L",  "loinc": "2093-3",  "ref": "0-5.18"},
    "HDL":     {"name": "HDL-Cholesterin",                  "unit": "mmol/L",  "loinc": "2085-9",  "ref": ">=1.04"},
    "HDLC":    {"name": "HDL-Cholesterin",                  "unit": "mmol/L",  "loinc": "2085-9",  "ref": ">=1.04"},
    "LDL":     {"name": "LDL-Cholesterin",                  "unit": "mmol/L",  "loinc": "2089-1",  "ref": "0-3.37"},
    "LDLC":    {"name": "LDL-Cholesterin",                  "unit": "mmol/L",  "loinc": "2089-1",  "ref": "0-3.37"},
    "TG":      {"name": "Triglyzeride",                     "unit": "mmol/L",  "loinc": "2571-8",  "ref": "0-1.7"},
    "TRIG":    {"name": "Triglyzeride",                     "unit": "mmol/L",  "loinc": "2571-8",  "ref": "0-1.7"},
    "NHDL":    {"name": "Nicht-HDL-Cholesterin",            "unit": "mmol/L",  "loinc": "43396-1", "ref": "0-4.14"},
    "CRP":     {"name": "C-reaktives Protein",              "unit": "mg/L",    "loinc": "1988-5",  "ref": "<5.0"},
}

# POCT1-A2 XML response templates
# Per il protocollo POCT1-A2 la risposta corretta a HEL, DST, OBS, END è ACK.R01
# con ACK.type_cd e ACK.ack_control_id (non ACK.ack_cd / ACK.ctl_id_responding_to)

_REQ_OBSERVATIONS = '''<?xml version="1.0" encoding="UTF-8"?>
<REQ.R01>
<HDR>
<HDR.control_id V="{ctrl_id}"/>
<HDR.version_id V="POCT1"/>
<HDR.creation_dttm V="{dttm}"/>
</HDR>
<REQ>
<REQ.request_cd V="ROBS"/>
</REQ>
</REQ.R01>\r\n'''
_ACK_RESPONSE = '''<?xml version="1.0" encoding="UTF-8"?>
<ACK.R01>
<HDR>
<HDR.control_id V="{ctrl_id}"/>
<HDR.version_id V="POCT1"/>
<HDR.creation_dttm V="{dttm}"/>
</HDR>
<ACK>
<ACK.type_cd V="AA"/>
<ACK.ack_control_id V="{responding_to}"/>
</ACK>
</ACK.R01>\r\n'''


def _now_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00")


_ctrl_counter = 1

def _ctrl_id(responding_to: str = "") -> str:
    global _ctrl_counter
    try:
        _ctrl_counter = int(responding_to) + 1
    except (ValueError, TypeError):
        _ctrl_counter += 1
    return str(_ctrl_counter)


def _get_attr(element, tag: str, attr: str = "V") -> str:
    """Find first element with tag and return attribute value."""
    el = element.find(".//" + tag)
    if el is not None:
        return el.get(attr, "")
    return ""


def _parse_obs_xml(xml_text: str, device_name: str) -> Optional[Dict[str, Any]]:
    """Parse POCT1-A2 OBS.R01 XML → result dict."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning("[%s] XML parse error: %s", device_name, e)
        return None

    tag = root.tag.upper()
    if "OBS" not in tag:
        return None

    result: Dict[str, Any] = {
        "timestamp":    datetime.now(),
        "sample_id":    "",
        "patient_id":   "",
        "patient_name": "",
        "age":          None,
        "gender":       "",
        "department":   "",
        "disc_name":    device_name,
        "lot_id":       "",
        "device":       device_name,
        "observations": [],
    }

    # Patient info
    pat_id = _get_attr(root, "PAT.patient_id")
    if pat_id:
        result["patient_id"] = pat_id
        result["sample_id"]  = pat_id

    pat_name = _get_attr(root, "PAT.patient_name")
    if pat_name:
        result["patient_name"] = pat_name.replace("^", " ").strip()

    gender = _get_attr(root, "PAT.administrative_sex_cd")
    if gender:
        result["gender"] = gender.upper()

    # Sample ID fallback from order
    ord_id = _get_attr(root, "ORD.order_id")
    if ord_id and not result["sample_id"]:
        result["sample_id"]  = ord_id
        result["patient_id"] = ord_id

    # Patient info — also check SVC/PT structure (cobas Liat style)
    pt_el = root.find(".//PT")
    if pt_el is not None:
        pid = _get_attr(pt_el, "PT.patient_id")
        if pid and not result["patient_id"]:
            result["patient_id"] = pid
            result["sample_id"]  = pid

    # Sample ID from ORD
    ord_id = _get_attr(root, "ORD.universal_service_id")
    if ord_id and not result["sample_id"]:
        result["sample_id"] = ord_id

    # Observations — find all OBS blocks (handles both flat and nested structures)
    for obs_el in root.iter("OBS"):
        test_cd = _get_attr(obs_el, "OBS.test_cd")
        value   = _get_attr(obs_el, "OBS.value")
        unit    = _get_attr(obs_el, "OBS.units_cd")
        flag    = _get_attr(obs_el, "OBS.abnormal_flag_cd")
        ref     = _get_attr(obs_el, "OBS.reference_range")
        # Also check for cobas b101 specific fields
        if not test_cd:
            test_cd = _get_attr(obs_el, "OBS.observation_id")
        if not value:
            value = _get_attr(obs_el, "OBS.qualitative_value")

        if not test_cd or not value:
            continue

        code = test_cd.upper().replace("-", "").replace("_", "")
        mapped  = COBAS_TEST_MAP.get(code, {})
        de_name = mapped.get("name", test_cd)
        de_unit = mapped.get("unit", unit) or unit
        loinc   = mapped.get("loinc", "99999-9")

        try:
            value_num: Optional[float] = float(re.sub(r"[<>= ]", "", value))
        except (ValueError, TypeError):
            value_num = None

        fl = ""
        if flag:
            fu = flag.upper()
            if "H" in fu:
                fl = "H"
            elif "L" in fu:
                fl = "L"

        ref_low = ref_high = None
        if ref and "-" in ref:
            rp = ref.split("-", 1)
            try:
                ref_low  = float(rp[0].strip())
                ref_high = float(rp[1].strip())
            except ValueError:
                pass

        result["observations"].append({
            "analyte":   code,
            "name_de":   de_name,
            "loinc":     loinc,
            "value":     value,
            "value_num": value_num,
            "flag":      fl,
            "ref_low":   ref_low,
            "ref_high":  ref_high,
            "unit":      de_unit,
        })

    if not result["observations"]:
        log.warning("[%s] OBS.R01 received but no observations found", device_name)
        return None

    log.info("[%s] Parsed: patient=%s analytes=%d",
             device_name, result["patient_id"], len(result["observations"]))
    return result


class CobasReader:
    """
    USB serial reader for Roche Cobas b 101 using POCT1-A2 XML protocol.
    Handles HEL/OBS/END handshake and parses result XML.
    """

    def __init__(
        self,
        serial_port: str,
        queue: asyncio.Queue,
        poll_interval: float = 5.0,
        device_name: str = "COBAS B101 POCT",
        baudrate: int = 9600,
    ) -> None:
        self._port        = serial_port
        self._queue       = queue
        self._device_name = device_name
        self._baudrate    = baudrate
        self._stop_event  = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def open(self) -> None:
        self._loop = asyncio.get_event_loop()
        log.info("[%s] USB serial port: %s @ %d baud",
                 self._device_name, self._port, self._baudrate)

    async def run(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._serial_loop)

    async def close(self) -> None:
        self._stop_event.set()
        log.info("[%s] Reader closed.", self._device_name)

    def _serial_loop(self) -> None:
        """Blocking serial loop — runs in executor thread."""
        import serial
        while not self._stop_event.is_set():
            try:
                ser = serial.Serial(
                    self._port,
                    baudrate=self._baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=1.0,
                )
                log.info("[%s] Serial port %s opened", self._device_name, self._port)
                self._session_loop(ser)
                ser.close()

            except Exception as exc:
                log.warning("[%s] Cannot open %s: %s — retry in 10s",
                            self._device_name, self._port, exc)
                time.sleep(10)

    def _session_loop(self, ser) -> None:
        """Handle POCT1-A2 session with Cobas."""
        buf = ""
        while not self._stop_event.is_set():
            try:
                data = ser.read(512)
                if not data:
                    continue
                buf += data.decode("utf-8", errors="replace")
                if not guard_str_buffer(buf, tag=self._device_name):
                    buf = ""  # drop and resync on next message

                # Process complete XML messages
                while True:
                    # Find complete XML message (ends with root closing tag)
                    match = re.search(r'(<\?xml[^>]*\?>.*?</\w+\.R\d+>)', buf, re.DOTALL)
                    if not match:
                        break
                    xml_text = match.group(1)
                    buf = buf[match.end():]
                    self._handle_message(ser, xml_text)

            except Exception as exc:
                log.warning("[%s] Session error: %s", self._device_name, exc)
                break

    def _handle_message(self, ser, xml_text: str) -> None:
        """Handle a single POCT1-A2 XML message."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            log.debug("[%s] Incomplete XML, skipping", self._device_name)
            return

        tag = root.tag
        ctrl_id = _get_attr(root, "HDR.control_id")
        dttm    = _now_str()
        new_id  = _ctrl_id(ctrl_id)

        log.debug("[%s] Received: %s (ctrl=%s)", self._device_name, tag, ctrl_id)

        if "HEL" in tag.upper():
            # Hello — send acknowledgement
            resp = _ACK_RESPONSE.format(
                ctrl_id=new_id, dttm=dttm, responding_to=ctrl_id
            )
            ser.write(resp.encode("utf-8"))
            ser.flush()
            log.info("[%s] Sent HEL acknowledgement (ACK.R01)", self._device_name)

        elif "DST" in tag.upper():
            # Device Status — risponde con ACK poi manda REQ per richiedere osservazioni
            obs_qty = _get_attr(root, "DST.new_observations_qty")
            log.info("[%s] Device status: %s new observations", self._device_name, obs_qty or "?")
            resp = _ACK_RESPONSE.format(
                ctrl_id=new_id, dttm=dttm, responding_to=ctrl_id
            )
            ser.write(resp.encode("utf-8"))
            ser.flush()
            # Se ci sono osservazioni disponibili, le richiediamo
            try:
                if int(obs_qty or "0") > 0:
                    # Small pause between ACK and REQ so the device has time to
                    # switch state. Blocking is fine here -- this loop runs in
                    # its own executor thread, not on the asyncio loop.
                    import time as _time
                    _time.sleep(0.2)
                    req_id = _ctrl_id(new_id)
                    req = _REQ_OBSERVATIONS.format(ctrl_id=req_id, dttm=_now_str())
                    ser.write(req.encode("utf-8"))
                    ser.flush()
                    log.info("[%s] Sent REQ.R01 for %s observations", self._device_name, obs_qty)
            except Exception as e:
                log.warning("[%s] Could not send REQ: %s", self._device_name, e)

        elif "OBS" in tag.upper():
            # Result data — parse and send ACK
            resp = _ACK_RESPONSE.format(
                ctrl_id=new_id, dttm=dttm, responding_to=ctrl_id
            )
            ser.write(resp.encode("utf-8"))
            ser.flush()

            result = _parse_obs_xml(xml_text, self._device_name)
            if result and self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._enqueue(result), self._loop
                )

        elif "END" in tag.upper():
            # Session end — acknowledge
            resp = _ACK_RESPONSE.format(
                ctrl_id=new_id, dttm=dttm, responding_to=ctrl_id
            )
            ser.write(resp.encode("utf-8"))
            ser.flush()
            log.info("[%s] Session ended (END.R01)", self._device_name)

        else:
            log.debug("[%s] Unknown message type: %s", self._device_name, tag)

    async def _enqueue(self, result: Dict[str, Any]) -> None:
        try:
            from src.common.conversion_audit import build_audit_for
            raw_hint = (result.get("_raw_payload") or "").encode("utf-8", errors="replace")
            result["conversion_audit"] = build_audit_for(
                device=self._device_name,
                sample_raw=result.get("sample_id", ""),
                sample_sent=result.get("sample_id", ""),
                patient_raw=result.get("patient_id", ""),
                patient_sent=result.get("patient_id", ""),
                raw_payload=raw_hint,
                observations=result.get("observations") or [],
            )
        except Exception as exc:
            log.debug("[%s] audit attach failed: %s", self._device_name, exc)
        safe_put_sync(self._queue, result, tag=self._device_name)
