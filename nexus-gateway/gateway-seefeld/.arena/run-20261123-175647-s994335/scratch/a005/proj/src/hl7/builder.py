r"""
src/hl7/builder.py
Builds HL7 v2.5 ORU^R01 messages from parsed result dicts.

Escape rules (HL7 v2.5 section 2.7):
  \  -> \E\   (escape)
  |  -> \F\   (field sep)
  ^  -> \S\   (component sep)
  ~  -> \R\   (repetition sep)
  &  -> \T\   (subcomponent sep)
  CR -> \X0D\ (segment sep -- MUST be escaped to preserve framing)
  LF -> \X0A\ (control char)
  FS -> \X1C\ (MLLP framing char -- MUST be escaped)
  VT -> \X0B\ (MLLP start block -- MUST be escaped)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from config.settings import HL7Config

log = logging.getLogger("loc200.hl7.builder")

_FS   = "\x1C"
_VT   = "\x0B"
_CR   = "\r"
_LF   = "\n"
_SEP  = "|"
_COMP = "^"
_REP  = "~"
_ESC  = "\\"
_SUB  = "&"
_ENCODING = f"{_COMP}{_REP}{_ESC}{_SUB}"

# Charset → Python codec name
_CHARSET_TO_CODEC = {
    "UNICODE UTF-8": "utf-8",
    "8859/1":         "iso-8859-1",
    "ASCII":          "ascii",
}


def _ts(dt: Optional[datetime] = None, include_tz: bool = True) -> str:
    d = dt or datetime.now().astimezone()
    if include_tz and d.tzinfo is None:
        d = d.astimezone()
    base = d.strftime("%Y%m%d%H%M%S")
    if include_tz and d.tzinfo is not None:
        offset = d.strftime("%z")
        return base + offset if offset else base
    return base


def _esc(s: Any) -> str:
    """
    Escape a value for safe insertion in an HL7 field.

    Handles all separator characters *and* MLLP framing bytes so
    hostile / malformed input cannot break segmentation or framing.
    """
    if s is None:
        return ""
    text = str(s)
    # Order matters: escape backslash first, then the rest.
    text = text.replace(_ESC, _ESC + "E" + _ESC)
    text = text.replace(_SEP,  _ESC + "F" + _ESC)
    text = text.replace(_COMP, _ESC + "S" + _ESC)
    text = text.replace(_REP,  _ESC + "R" + _ESC)
    text = text.replace(_SUB,  _ESC + "T" + _ESC)
    # Control / framing bytes — HL7 hex-escape notation \Xdd\
    text = text.replace(_CR, _ESC + "X0D" + _ESC)
    text = text.replace(_LF, _ESC + "X0A" + _ESC)
    text = text.replace(_FS, _ESC + "X1C" + _ESC)
    text = text.replace(_VT, _ESC + "X0B" + _ESC)
    return text


class HL7Message:
    def __init__(
        self,
        segments: List[str],
        msh_control_id: str,
        charset: str = "UNICODE UTF-8",
    ) -> None:
        self._segments = segments
        self._charset  = charset
        self._codec    = _CHARSET_TO_CODEC.get(charset, "utf-8")
        self.msh = _MSHInfo(msh_control_id)

    @property
    def control_id(self) -> str:
        return self.msh.message_control_id

    @property
    def charset(self) -> str:
        return self._charset

    def to_string(self) -> str:
        return _CR.join(self._segments) + _CR

    def to_mllp(self) -> bytes:
        """MLLP frame using the declared MSH-18 charset."""
        VT = b"\x0B"
        FS = b"\x1C"
        CR = b"\x0D"
        body = self.to_string().encode(self._codec, errors="replace")
        return VT + body + FS + CR

    def to_file(self, encoding: Optional[str] = None) -> bytes:
        codec = encoding or self._codec
        return self.to_string().replace(_CR, "\r\n").encode(codec, errors="replace")


class _MSHInfo:
    def __init__(self, control_id: str) -> None:
        self.message_control_id = control_id


class _LoincMap:
    """Maps analyte codes to LOINC codes + German display names."""

    _PLACEHOLDER_LOINC = "99999-9"

    _BUILTIN: Dict[str, Dict] = {
        # Leber / Protein
        "TP":     {"loinc": "2885-2",  "name": "Gesamtprotein",                              "unit": "g/L"},
        "ALB":    {"loinc": "1751-7",  "name": "Albumin",                                   "unit": "g/L"},
        "GLOB":   {"loinc": "10834-0", "name": "Globuline",                                  "unit": "g/L"},
        "A/G":    {"loinc": "1759-0",  "name": "Albumin/Globulin-Quotient",                  "unit": ""},
        "TBIL":   {"loinc": "1975-2",  "name": "Bilirubin gesamt",                           "unit": "umol/L"},
        "DBIL":   {"loinc": "1968-7",  "name": "Bilirubin direkt",                           "unit": "umol/L"},
        "IBIL":   {"loinc": "1971-1",  "name": "Bilirubin indirekt",                         "unit": "umol/L"},
        "TB":     {"loinc": "1975-2",  "name": "Bilirubin gesamt",                           "unit": "umol/L"},
        "DB":     {"loinc": "1968-7",  "name": "Bilirubin direkt",                           "unit": "umol/L"},
        "ALT":    {"loinc": "1742-6",  "name": "ALT (GPT) - Alanin-Aminotransferase",        "unit": "U/L"},
        "AST":    {"loinc": "1920-8",  "name": "AST (GOT) - Aspartat-Aminotransferase",      "unit": "U/L"},
        "GGT":    {"loinc": "2324-2",  "name": "Gamma-GT - Gamma-Glutamyltransferase",       "unit": "U/L"},
        "ALP":    {"loinc": "6768-6",  "name": "Alkalische Phosphatase",                     "unit": "U/L"},
        "CHE":    {"loinc": "2099-0",  "name": "Cholinesterase",                             "unit": "U/L"},
        "TBA":    {"loinc": "16124-9", "name": "Gallensaeuren gesamt",                       "unit": "umol/L"},
        "LDH":    {"loinc": "2532-0",  "name": "Laktat-Dehydrogenase",                       "unit": "U/L"},
        "AMY":    {"loinc": "1798-8",  "name": "Amylase",                                   "unit": "U/L"},
        "CK":     {"loinc": "2157-6",  "name": "Kreatinkinase gesamt",                       "unit": "U/L"},
        "CK-MB":  {"loinc": "13969-1", "name": "Kreatinkinase-MB",                           "unit": "U/L"},
        "A-HBDH": {"loinc": "12187-9", "name": "Hydroxybutyrat-Dehydrogenase",               "unit": "U/L"},
        # Niere
        "CRE":    {"loinc": "2160-0",  "name": "Kreatinin",                                  "unit": "umol/L"},
        "CREA":   {"loinc": "2160-0",  "name": "Kreatinin",                                  "unit": "umol/L"},
        "UA":     {"loinc": "3084-1",  "name": "Harnsaeure",                                 "unit": "umol/L"},
        "UREA":   {"loinc": "3094-0",  "name": "Harnstoff",                                  "unit": "mmol/L"},
        "BUN":    {"loinc": "3094-0",  "name": "Harnstoff-Stickstoff",                       "unit": "mmol/L"},
        "BUN/CREA":{"loinc":"3097-3",  "name": "BUN/Kreatinin-Quotient",                     "unit": ""},
        "eGFR":   {"loinc": "62238-1", "name": "Geschaetzte glomerulaere Filtrationsrate",   "unit": ""},
        "EGFRCR": {"loinc": "62238-1", "name": "eGFR (Kreatinin)",                           "unit": ""},
        # Stoffwechsel
        "GLU":    {"loinc": "2345-7",  "name": "Glukose",                                   "unit": "mmol/L"},
        "HBA1C":  {"loinc": "4548-4",  "name": "Glykiertes Haemoglobin (HbA1c)",             "unit": "%"},
        "FRUC":   {"loinc": "14176-0", "name": "Fructosamin",                                "unit": "umol/L"},
        # Lipide
        "CHOL":   {"loinc": "2093-3",  "name": "Cholesterin gesamt",                         "unit": "mmol/L"},
        "TC":     {"loinc": "2093-3",  "name": "Cholesterin gesamt",                         "unit": "mmol/L"},
        "TG":     {"loinc": "2571-8",  "name": "Triglyzeride",                               "unit": "mmol/L"},
        "HDL":    {"loinc": "2085-9",  "name": "HDL-Cholesterin",                            "unit": "mmol/L"},
        "HDL-C":  {"loinc": "2085-9",  "name": "HDL-Cholesterin",                            "unit": "mmol/L"},
        "LDL":    {"loinc": "2089-1",  "name": "LDL-Cholesterin",                            "unit": "mmol/L"},
        "LDL-C":  {"loinc": "2089-1",  "name": "LDL-Cholesterin",                            "unit": "mmol/L"},
        "NHDL":   {"loinc": "43396-1", "name": "Nicht-HDL-Cholesterin",                      "unit": "mmol/L"},
        "VLDL":   {"loinc": "13458-5", "name": "VLDL-Cholesterin",                           "unit": "mmol/L"},
        "TC/HDL": {"loinc": "9830-1",  "name": "Cholesterin/HDL-Quotient",                   "unit": ""},
        # Entzuendung
        "CRP":    {"loinc": "1988-5",  "name": "C-reaktives Protein",                        "unit": "mg/L"},
        # Elektrolyte
        "K+":     {"loinc": "2823-3",  "name": "Kalium",                                    "unit": "mmol/L"},
        "NA+":    {"loinc": "2951-2",  "name": "Natrium",                                   "unit": "mmol/L"},
        "CL-":    {"loinc": "2075-0",  "name": "Chlorid",                                   "unit": "mmol/L"},
        "CA":     {"loinc": "17861-6", "name": "Kalzium",                                   "unit": "mmol/L"},
        "MG2+":   {"loinc": "19123-9", "name": "Magnesium",                                 "unit": "mmol/L"},
        "P":      {"loinc": "2777-1",  "name": "Phosphor (anorganisch)",                     "unit": "mmol/L"},
        "PHOS":   {"loinc": "2777-1",  "name": "Phosphor (anorganisch)",                     "unit": "mmol/L"},
        "CO2":    {"loinc": "2028-9",  "name": "Kohlendioxid gesamt",                        "unit": "mmol/L"},
        "AG":     {"loinc": "1863-0",  "name": "Anionluecke",                                "unit": "mmol/L"},
        "HCY":    {"loinc": "13965-7", "name": "Homocystein",                                "unit": "umol/L"},
        # Haematologie Sysmex
        "WBC":    {"loinc": "6690-2",  "name": "Leukozyten",                                 "unit": "10^3/uL"},
        "RBC":    {"loinc": "789-8",   "name": "Erythrozyten",                               "unit": "10^6/uL"},
        "HGB":    {"loinc": "718-7",   "name": "Haemoglobin",                                "unit": "g/dL"},
        "HCT":    {"loinc": "20570-8", "name": "Haematokrit",                                "unit": "%"},
        "MCV":    {"loinc": "787-2",   "name": "Mittleres Erythrozyten-Volumen",             "unit": "fL"},
        "MCH":    {"loinc": "785-6",   "name": "Mittlerer Hb-Gehalt pro Erythrozyt",         "unit": "pg"},
        "MCHC":   {"loinc": "786-4",   "name": "Mittlere Hb-Konzentration",                  "unit": "g/dL"},
        "PLT":    {"loinc": "777-3",   "name": "Thrombozyten",                               "unit": "10^3/uL"},
        "NEUT%":  {"loinc": "26499-4", "name": "Neutrophile %",                              "unit": "%"},
        "LYMPH%": {"loinc": "26474-7", "name": "Lymphozyten %",                              "unit": "%"},
        "MXD%":   {"loinc": "26484-6", "name": "Mono./Eos./Baso. %",                         "unit": "%"},
        "NEUT#":  {"loinc": "751-8",   "name": "Neutrophile abs.",                           "unit": "10^3/uL"},
        "LYMPH#": {"loinc": "731-0",   "name": "Lymphozyten abs.",                           "unit": "10^3/uL"},
        "MXD#":   {"loinc": "10000-8", "name": "Mono./Eos./Baso. abs.",                      "unit": "10^3/uL"},
        "RDW-SD": {"loinc": "21000-5", "name": "Erythrozyten-Verteilungsbreite SD",          "unit": "fL"},
        "RDW-CV": {"loinc": "788-0",   "name": "Erythrozyten-Verteilungsbreite CV",          "unit": "%"},
        "PDW":    {"loinc": "32207-3", "name": "Thrombozyten-Verteilungsbreite",             "unit": "fL"},
        "MPV":    {"loinc": "32623-1", "name": "Mittleres Thrombozyten-Volumen",             "unit": "fL"},
        "P-LCR":  {"loinc": "48386-7", "name": "Grossthrombozyten-Anteil",                   "unit": "%"},
        "PCT":    {"loinc": "10501-6", "name": "Thrombokrit",                                "unit": "%"},
        # Cobas
        "CHOL_C": {"loinc": "2093-3",  "name": "Cholesterin gesamt",                         "unit": "mmol/L"},
        # UC-1000 Urinstatus
        "GLU_U":  {"loinc": "25428-4", "name": "Glukose (Urin)",                             "unit": ""},
        "PRO":    {"loinc": "20454-5", "name": "Protein (Urin)",                             "unit": ""},
        "BIL":    {"loinc": "1971-1",  "name": "Bilirubin (Urin)",                           "unit": ""},
        "KET":    {"loinc": "2514-8",  "name": "Ketone (Urin)",                              "unit": ""},
        "BLO":    {"loinc": "5794-3",  "name": "Blut (Urin)",                                "unit": ""},
        "LEU":    {"loinc": "5821-4",  "name": "Leukozyten (Urin)",                          "unit": ""},
        "NIT":    {"loinc": "5802-4",  "name": "Nitrit (Urin)",                              "unit": ""},
        "URO":    {"loinc": "13658-8", "name": "Urobilinogen (Urin)",                        "unit": "mg/dL"},
        "ASC":    {"loinc": "5804-0",  "name": "Ascorbinsaeure (Urin)",                      "unit": ""},
        "SG":     {"loinc": "2965-2",  "name": "Spezifisches Gewicht (Urin)",                "unit": ""},
        "PH":     {"loinc": "2756-5",  "name": "pH (Urin)",                                  "unit": ""},
        "AC":     {"loinc": "32294-1", "name": "Albumin/Kreatinin-Quotient",                 "unit": ""},
        "PC":     {"loinc": "2890-2",  "name": "Protein/Kreatinin-Quotient",                 "unit": ""},
    }

    def __init__(self, map_path: Optional[str] = None) -> None:
        self._map: Dict[str, Dict] = dict(self._BUILTIN)
        self._missing_warned: set[str] = set()
        if map_path:
            p = Path(map_path)
            if p.exists():
                extra = yaml.safe_load(p.read_text()) or {}
                self._map.update(extra)
                log.info("LOINC map loaded: %d extra entries from %s", len(extra), p)

    def get(self, analyte: str) -> Dict:
        key = analyte.upper().replace(" ", "")
        if key in self._map:
            return self._map[key]
        if key not in self._missing_warned:
            self._missing_warned.add(key)
            log.warning(
                "Analyte %r has no LOINC mapping — sending placeholder %s. "
                "Add it to config/loinc_map.yaml.",
                analyte, self._PLACEHOLDER_LOINC,
            )
        return {"loinc": self._PLACEHOLDER_LOINC, "name": analyte, "unit": ""}


class HL7Builder:
    """Builds HL7 v2.5 ORU^R01 messages."""

    def __init__(self, config: HL7Config) -> None:
        self._cfg = config
        self._loinc = _LoincMap(config.loinc_map_path)

    def build_oru_r01(self, result: Dict[str, Any]) -> HL7Message:
        control_id = uuid.uuid4().hex[:20].upper()
        include_tz = getattr(self._cfg, "include_timezone", True)
        charset    = getattr(self._cfg, "charset", "UNICODE UTF-8")
        now_ts     = _ts(include_tz=include_tz)
        result_ts  = _ts(result.get("timestamp"), include_tz=include_tz)

        # MSH-3 length depends on the HL7 version. The 20-char cap belongs to
        # the HD namespace-id introduced in 2.3.1; in 2.3 MSH-3 is a plain ST
        # (180). Capping at 20 turned "SYSMEX XQ320 Haematologie" into
        # "SYSMEX XQ320 Haemato" and the PIS stopped recognising the sender.
        _msh3_max = 180 if str(self._cfg.version) in ("2.2", "2.3") else 20
        sending_app_raw = str(result.get("device") or self._cfg.sending_application)
        if len(sending_app_raw) > _msh3_max:
            log.debug("Truncating sending_application %r to %d chars",
                      sending_app_raw, _msh3_max)
        sending_app = sending_app_raw[:_msh3_max]

        segments: List[str] = []

        # MSH
        segments.append(
            f"MSH|{_ENCODING}|"
            f"{_esc(sending_app)}|"
            f"{_esc(self._cfg.sending_facility)}|"
            f"{_esc(self._cfg.receiving_application)}|"
            f"{_esc(self._cfg.receiving_facility)}|"
            f"{now_ts}||ORU^R01^ORU_R01|"
            f"{control_id}|P|"
            f"{self._cfg.version}|||NE|AL|"
            f"|{charset}"
        )

        # PID
        name_parts = str(result.get("patient_name", "")).split(" ", 1)
        family = _esc(name_parts[0]) if name_parts else ""
        given  = _esc(name_parts[1]) if len(name_parts) > 1 else ""
        segments.append(
            f"PID||{_esc(result.get('patient_id',''))}|{_esc(result.get('patient_id',''))}||"
            f"{family}^{given}||"
            f"||"
            f"{_esc(result.get('gender',''))}|||"
            f"||||||"
        )

        # PV1
        dept = _esc(result.get("department", ""))
        segments.append(
            f"PV1|1|O|||||||||||||||||||"
            f"{dept}|||||||||||||||||||||||||"
        )

        # OBR
        pid = _esc(result.get('patient_id', ''))
        lot = _esc(result.get("lot_id", ""))
        segments.append(
            f"OBR|1|||"
            f"{pid}^{pid}^L||"
            f"{result_ts}|{result_ts}|||||||||"
            f"|||{lot}|||F"
        )

        # OBX (one per analyte)
        for seq, obs in enumerate(result.get("observations", []), start=1):
            analyte = obs["analyte"]
            loinc_rec = self._loinc.get(analyte)
            loinc_id  = loinc_rec["loinc"]
            loinc_nm  = _esc(analyte)

            if obs.get("value_num") is not None:
                vt    = "NM"
                value = str(obs["value_num"])
            else:
                vt    = "ST"
                value = _esc(obs.get("value", ""))

            ref_low  = obs.get("ref_low")
            ref_high = obs.get("ref_high")
            ref_str  = ""
            if ref_low is not None and ref_high is not None:
                ref_str = f"{ref_low}^{ref_high}"
            elif ref_high is not None:
                ref_str = f"^{ref_high}"
            elif ref_low is not None:
                ref_str = f"{ref_low}^"

            flag = _esc(obs.get("flag", ""))
            unit = _esc(obs.get("unit", loinc_rec.get("unit", "")))

            segments.append(
                f"OBX|{seq}|{vt}|"
                f"{loinc_id}^{loinc_nm}^LN|1|"
                f"{value}|"
                f"{unit}^{unit}^ISO+|"
                f"{ref_str}|{flag}|||F|||{result_ts}"
            )

        return HL7Message(segments, control_id, charset=charset)
