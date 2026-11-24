"""
src/adapters/mllp_reader.py
Generic MLLP/HL7 TCP listener for analyzers that send HL7 natively.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.common.backpressure import safe_put_sync
from src.common.framing import guard_buffer
from src.common import trace as _trace

log = logging.getLogger("loc200.mllp")

VT = b"\x0B"
FS = b"\x1C"
CR = b"\x0D"

SEAMATY_TEST_MAP: Dict[str, Dict] = {
    "ALT":   {"name": "ALT (GPT) - Alanin-Aminotransferase",      "unit": "U/L",    "loinc": "1742-6",  "ref": "7-40"},
    "AST":   {"name": "AST (GOT) - Aspartat-Aminotransferase",     "unit": "U/L",    "loinc": "1920-8",  "ref": "13-35"},
    "GGT":   {"name": "Gamma-GT - Gamma-Glutamyltransferase",      "unit": "U/L",    "loinc": "2324-2",  "ref": "7-45"},
    "ALP":   {"name": "Alkalische Phosphatase",                    "unit": "U/L",    "loinc": "6768-6",  "ref": "50-135"},
    "TBIL":  {"name": "Bilirubin gesamt",                          "unit": "umol/L", "loinc": "1975-2",  "ref": "0-20.5"},
    "DBIL":  {"name": "Bilirubin direkt",                          "unit": "umol/L", "loinc": "1968-7",  "ref": "0-6.8"},
    "ALB":   {"name": "Albumin",                                   "unit": "g/L",    "loinc": "1751-7",  "ref": "40-55"},
    "TP":    {"name": "Gesamtprotein",                             "unit": "g/L",    "loinc": "2885-2",  "ref": "65-85"},
    "CHE":   {"name": "Cholinesterase",                            "unit": "U/L",    "loinc": "2099-0",  "ref": "5320-12920"},
    "TBA":   {"name": "Gallensaeuren gesamt",                      "unit": "umol/L", "loinc": "16124-9", "ref": "0-10"},
    "UREA":  {"name": "Harnstoff",                                 "unit": "mmol/L", "loinc": "3094-0",  "ref": "3.1-8.8"},
    "CRE":   {"name": "Kreatinin",                                 "unit": "umol/L", "loinc": "2160-0",  "ref": "41-81"},
    "UA":    {"name": "Harnsaeure",                                "unit": "umol/L", "loinc": "3084-1",  "ref": "155-357"},
    "eGFR":  {"name": "Geschaetzte glomerulaere Filtrationsrate",  "unit": "",       "loinc": "62238-1", "ref": ""},
    "GLU":   {"name": "Glukose",                                   "unit": "mmol/L", "loinc": "2345-7",  "ref": "4.41-6.11"},
    "HBA1C": {"name": "Glykiertes Haemoglobin (HbA1c)",            "unit": "%",      "loinc": "4548-4",  "ref": "4.0-5.6"},
    "CHOL":  {"name": "Cholesterin gesamt",                        "unit": "mmol/L", "loinc": "2093-3",  "ref": "0-5.17"},
    "TG":    {"name": "Triglyzeride",                              "unit": "mmol/L", "loinc": "2571-8",  "ref": "0-1.7"},
    "HDL":   {"name": "HDL-Cholesterin",                           "unit": "mmol/L", "loinc": "2085-9",  "ref": "1.04-1.55"},
    "LDL":   {"name": "LDL-Cholesterin",                           "unit": "mmol/L", "loinc": "2089-1",  "ref": "0.5-3.14"},
    "NHDL":  {"name": "Nicht-HDL-Cholesterin",                     "unit": "mmol/L", "loinc": "43396-1", "ref": "0-4.14"},
    "CRP":   {"name": "C-reaktives Protein",                       "unit": "mg/L",   "loinc": "1988-5",  "ref": ""},
    "AMY":   {"name": "Amylase",                                   "unit": "U/L",    "loinc": "1798-8",  "ref": "20-110"},
    "LDH":   {"name": "Laktat-Dehydrogenase",                      "unit": "U/L",    "loinc": "2532-0",  "ref": "135-225"},
    "CK":    {"name": "Kreatinkinase gesamt",                      "unit": "U/L",    "loinc": "2157-6",  "ref": "24-170"},
    "CA":    {"name": "Kalzium",                                   "unit": "mmol/L", "loinc": "17861-6", "ref": "2.1-2.6"},
    "PHOS":  {"name": "Phosphor (anorganisch)",                    "unit": "mmol/L", "loinc": "2777-1",  "ref": "0.87-1.45"},
    "GLOB":  {"name": "Globuline",                                 "unit": "g/L",    "loinc": "10834-0", "ref": "20-40"},
    "IBIL":  {"name": "Bilirubin indirekt",                        "unit": "umol/L", "loinc": "1971-1",  "ref": "0-17"},
    "TC":    {"name": "Cholesterin gesamt",                        "unit": "mmol/L", "loinc": "2093-3",  "ref": "0-5.17"},
    "EGFRCR":{"name": "eGFR (Kreatinin)",                          "unit": "",       "loinc": "62238-1", "ref": ""},
    "BUN":   {"name": "Harnstoff-Stickstoff",                      "unit": "mmol/L", "loinc": "3094-0",  "ref": "2.5-8.2"},
    "CREA":  {"name": "Kreatinin",                                 "unit": "umol/L", "loinc": "2160-0",  "ref": "35-80"},
    "TB":    {"name": "Bilirubin gesamt",                          "unit": "umol/L", "loinc": "1975-2",  "ref": "3.4-21.0"},
    "DB":    {"name": "Bilirubin direkt",                          "unit": "umol/L", "loinc": "1968-7",  "ref": "0-6.8"},
    "A/G":   {"name": "Albumin/Globulin-Quotient",                 "unit": "",       "loinc": "1759-0",  "ref": "1.2-2.4"},
    "BUN/CREA": {"name": "BUN/Kreatinin-Quotient",                 "unit": "",       "loinc": "99999-9", "ref": "24-155"},
    "VLDL":  {"name": "VLDL-Cholesterin",                          "unit": "mmol/L", "loinc": "99999-9", "ref": ""},
    "TC/HDL":{"name": "Cholesterin/HDL-Quotient",                  "unit": "",       "loinc": "99999-9", "ref": ""},
}

# Mappa LOINC → chiave breve per lookup inverso.
# NB: rebuilt at reader-init time so custom entries from config/loinc_map.yaml
# are honoured (see MLLPReader.__init__).
_LOINC_TO_KEY: Dict[str, str] = {v["loinc"]: k for k, v in SEAMATY_TEST_MAP.items() if v.get("loinc") != "99999-9"}


def _build_loinc_index(*maps: Dict[str, Dict]) -> Dict[str, str]:
    idx: Dict[str, str] = {}
    for m in maps:
        for k, v in m.items():
            loinc = v.get("loinc")
            if loinc and loinc != "99999-9" and loinc not in idx:
                idx[loinc] = k
    return idx

HORIBA_TEST_MAP: Dict[str, Dict] = {
    "WBC":   {"name": "Leukozyten",                                "unit": "10^3/uL", "loinc": "6690-2",  "ref": "4.0-10.0"},
    "GRA#":  {"name": "Granulozyten abs.",                         "unit": "10^3/uL", "loinc": "26499-4", "ref": "2.0-7.5"},
    "LYM#":  {"name": "Lymphozyten abs.",                          "unit": "10^3/uL", "loinc": "26474-7", "ref": "1.0-4.0"},
    "MID#":  {"name": "Mittelzellen abs. (Mono/Eos/Baso)",         "unit": "10^3/uL", "loinc": "26484-6", "ref": "0.1-1.0"},
    "GRA%":  {"name": "Granulozyten %",                            "unit": "%",       "loinc": "26499-4", "ref": "43-76"},
    "LYM%":  {"name": "Lymphozyten %",                             "unit": "%",       "loinc": "26474-7", "ref": "20-45"},
    "MID%":  {"name": "Mittelzellen %",                            "unit": "%",       "loinc": "26484-6", "ref": "2-12"},
    "GLR":   {"name": "Granulozyten/Lymphozyten-Ratio",            "unit": "",        "loinc": "99999-9", "ref": ""},
    "RBC":   {"name": "Erythrozyten",                              "unit": "10^6/uL", "loinc": "789-8",   "ref": "4.2-5.4"},
    "HGB":   {"name": "Haemoglobin",                               "unit": "g/dL",    "loinc": "718-7",   "ref": "12.0-16.0"},
    "HCT":   {"name": "Haematokrit",                               "unit": "%",       "loinc": "20570-8", "ref": "36.0-46.0"},
    "MCV":   {"name": "Mittleres Erythrozyten-Volumen",            "unit": "fL",      "loinc": "787-2",   "ref": "85-95"},
    "MCH":   {"name": "Mittlerer Hb-Gehalt pro Erythrozyt",        "unit": "pg",      "loinc": "785-6",   "ref": "27-33"},
    "MCHC":  {"name": "Mittlere Hb-Konzentration",                 "unit": "g/dL",    "loinc": "786-4",   "ref": "32-36"},
    "RDW":   {"name": "Erythrozyten-Verteilungsbreite",            "unit": "%",       "loinc": "788-0",   "ref": "11.5-14.5"},
    "PLT":   {"name": "Thrombozyten",                              "unit": "10^3/uL", "loinc": "777-3",   "ref": "150-400"},
    "MPV":   {"name": "Mittleres Thrombozyten-Volumen",            "unit": "fL",      "loinc": "32623-1", "ref": "7-13"},
    "PCT":   {"name": "Thrombokrit",                               "unit": "%",       "loinc": "32623-1", "ref": "0.10-0.30"},
    "PDW":   {"name": "Thrombozyten-Verteilungsbreite",            "unit": "fL",      "loinc": "32623-1", "ref": "9-17"},
    "CRP":   {"name": "C-reaktives Protein",                       "unit": "mg/L",    "loinc": "1988-5",  "ref": ""},
}

_DEVICE_MAPS: Dict[str, Dict] = {
    "seamaty":          SEAMATY_TEST_MAP,
    "seamaty_smt120":   SEAMATY_TEST_MAP,
    "seamaty_sd1":      SEAMATY_TEST_MAP,
    "seamaty_sd3":      SEAMATY_TEST_MAP,
    "horiba":           HORIBA_TEST_MAP,
    "horiba_microsemi": HORIBA_TEST_MAP,
}


def _lookup_test(test_map: Dict, analyte: str, code_parts: List[str]) -> Dict:
    """Cerca nella mappa per codice breve, poi per LOINC."""
    # 1. Cerca direttamente per codice breve
    mapped = test_map.get(analyte, {})
    if mapped:
        return mapped
    # 2. Cerca per LOINC (primo campo es. "1751-7")
    loinc_key = _LOINC_TO_KEY.get(analyte)
    if loinc_key:
        return test_map.get(loinc_key, {})
    # 3. Cerca tra i campi del codice OBX-3
    for part in code_parts:
        p = part.strip().upper()
        if p in test_map:
            return test_map[p]
        loinc_key2 = _LOINC_TO_KEY.get(p)
        if loinc_key2:
            return test_map.get(loinc_key2, {})
    return {}


def _parse_ref(ref_raw: str):
    """Parsa il campo ref: supporta ^ e - come separatori."""
    ref_low = ref_high = None
    if "^" in ref_raw:
        rp = ref_raw.split("^", 1)
        try:
            ref_low  = float(rp[0].strip())
            ref_high = float(rp[1].strip())
        except ValueError:
            pass
    elif "-" in ref_raw:
        rp = ref_raw.split("-", 1)
        try:
            ref_low  = float(rp[0].strip())
            ref_high = float(rp[1].strip())
        except ValueError:
            pass
    return ref_low, ref_high


class MLLPReader:

    def __init__(
        self,
        host: str,
        port: int,
        queue: asyncio.Queue,
        device_name: str,
        device_type: str = "seamaty",
        on_connect: Optional[Callable] = None,
    ) -> None:
        self._host        = host
        self._port        = port
        self._queue       = queue
        self._device_name = device_name
        self._device_type = device_type
        self._test_map    = _DEVICE_MAPS.get(device_type, SEAMATY_TEST_MAP)
        self._on_connect  = on_connect
        self._server: Optional[asyncio.AbstractServer] = None
        self._stop_event  = asyncio.Event()

    async def open(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self._host, self._port
        )
        log.info("[%s] MLLP listening on %s:%d", self._device_name, self._host, self._port)

    async def run(self) -> None:
        await self._stop_event.wait()

    async def close(self) -> None:
        self._stop_event.set()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        log.info("[%s] MLLP reader closed.", self._device_name)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        addr = writer.get_extra_info("peername")
        log.info("[%s] MLLP connection from %s", self._device_name, addr)

        if self._on_connect:
            self._on_connect()

        buf = bytearray()
        in_msg = False

        try:
            while True:
                data = await asyncio.wait_for(reader.read(4096), timeout=30.0)
                if not data:
                    break

                for byte in data:
                    b = bytes([byte])
                    if b == VT:
                        buf.clear()
                        in_msg = True
                    elif b == FS and in_msg:
                        in_msg = False
                        raw_frame = bytes(buf)
                        msg_text = raw_frame.decode("utf-8", errors="replace")
                        buf.clear()
                        _trace.record(self._device_name, "in", raw_frame)
                        result = self._parse_hl7(msg_text)
                        if result:
                            safe_put_sync(self._queue, result, tag=self._device_name)
                        ack = self._build_ack(msg_text)
                        writer.write(ack)
                        await writer.drain()
                    elif in_msg:
                        buf.extend(b)
                        if not guard_buffer(buf, tag=self._device_name):
                            buf.clear()
                            in_msg = False

        except asyncio.TimeoutError:
            log.debug("[%s] Client %s timeout.", self._device_name, addr)
        except Exception as exc:
            log.warning("[%s] Client error %s: %s", self._device_name, addr, exc)
        finally:
            writer.close()

    def _parse_hl7(self, msg: str) -> Optional[Dict[str, Any]]:
        lines = [l.strip() for l in msg.replace("\r\n", "\r").split("\r") if l.strip()]

        result: Dict[str, Any] = {
            "timestamp":    datetime.now(),
            "sample_id":    "",
            "patient_id":   "",
            "patient_name": "",
            "age":          None,
            "gender":       "",
            "department":   "",
            "disc_name":    self._device_name,
            "lot_id":       "",
            "device":       self._device_name,
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
                if len(fields) > 5:
                    result["patient_name"] = fields[5].strip().replace("^", " ").strip()
                if len(fields) > 8:
                    g = fields[8].strip().upper()
                    result["gender"] = "M" if g == "M" else ("F" if g == "F" else "")

            elif seg == "OBR":
                if len(fields) > 2:
                    result["sample_id"] = result["sample_id"] or fields[2].strip()
                if len(fields) > 3:
                    result["disc_name"] = fields[3].strip().split("^")[0] or self._device_name

            elif seg == "OBX":
                if len(fields) < 6:
                    continue

                code_field  = fields[3].strip() if len(fields) > 3 else ""
                code_parts  = [p.strip() for p in code_field.split("^")]
                # Usa il primo campo come analyte (es. LOINC o codice breve)
                analyte     = code_parts[0].upper() if code_parts else ""
                if not analyte:
                    continue

                value_str = fields[5].strip() if len(fields) > 5 else ""
                unit_raw  = fields[6].strip().split("^")[0] if len(fields) > 6 else ""
                ref_raw   = fields[7].strip() if len(fields) > 7 else ""
                flag_raw  = fields[8].strip() if len(fields) > 8 else ""

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

                # Parsa ref dal messaggio (supporta ^ e -)
                ref_low, ref_high = _parse_ref(ref_raw)

                # Cerca nella mappa per codice breve o LOINC
                mapped  = _lookup_test(self._test_map, analyte, code_parts)
                de_name = mapped.get("name", analyte)
                de_unit = mapped.get("unit", unit_raw) or unit_raw
                loinc   = mapped.get("loinc", analyte if re.match(r"^\d+-\d+$", analyte) else "99999-9")

                # Fallback ref dalla mappa se il device non li manda
                if ref_low is None and ref_high is None and mapped.get("ref", ""):
                    ref_low, ref_high = _parse_ref(mapped["ref"])

                result["observations"].append({
                    "analyte":   analyte,
                    "name_de":   de_name,
                    "loinc":     loinc,
                    "value":     value_str,
                    "value_num": value_num,
                    "flag":      flag,
                    "ref_low":   ref_low,
                    "ref_high":  ref_high,
                    "unit":      de_unit,
                })

        if not result["observations"]:
            log.warning("[%s] No OBX segments found in HL7 message.", self._device_name)
            return None

        log.info(
            "[%s] Parsed: sample=%s patient=%s analytes=%d",
            self._device_name,
            result["sample_id"],
            result["patient_id"],
            len(result["observations"]),
        )
        return result

    @staticmethod
    def _build_ack(original: str) -> bytes:
        ctrl_id = "ACK_" + datetime.now().strftime("%H%M%S%f")[:16]
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        msh_line = next((l for l in original.split("\r") if l.startswith("MSH")), "")
        fields = msh_line.split("|")
        sending_app = fields[2] if len(fields) > 2 else "DEVICE"
        orig_ctrl   = fields[9] if len(fields) > 9 else ctrl_id
        ack = (
            f"MSH|^~\\&|LOC200_GW|PRAXIS|{sending_app}|DEVICE|{ts}||ACK^R01|{ctrl_id}|P|2.3\r"
            f"MSA|AA|{orig_ctrl}|Message accepted\r"
        )
        return VT + ack.encode("utf-8") + FS + CR
