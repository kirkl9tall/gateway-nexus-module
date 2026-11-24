"""
HL7 v2.5 compliance validator.

Runs after the HL7 message is built, before it goes out on the wire.
Catches the mistakes the receiving PIS would send back as AR/AE, so we
surface them locally and don't burn a round-trip.

Every finding has a level:
  ERROR    -- would definitely be rejected (missing required segment,
              MSH-3 too long, malformed segment terminator)
  WARN     -- probably works but not strictly conformant (placeholder
              LOINC, empty patient name, etc.)
  INFO     -- style / best-practice notes
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class Finding:
    level:    str        # ERROR | WARN | INFO
    segment:  str        # e.g. "MSH", "PID", "OBX-1"
    message:  str
    field:    str = ""


@dataclass
class Report:
    findings: List[Finding] = field(default_factory=list)

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.level == "ERROR"]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.level == "WARN"]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add(self, level: str, segment: str, message: str, field: str = "") -> None:
        self.findings.append(Finding(level, segment, message, field))

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "errors":   len(self.errors),
            "warnings": len(self.warnings),
            "findings": [
                {"level": f.level, "segment": f.segment,
                 "field": f.field, "message": f.message}
                for f in self.findings
            ],
        }


# Length caps from HL7 v2.5 table
_MAX = {
    "MSH-3":  20,   # sending_application   -- ma dipende dalla versione
    "MSH-4":  180,  # sending_facility (HD data type)
    "MSH-5":  20,   # receiving_application -- ma dipende dalla versione
    "MSH-6":  180,  # receiving_facility
    "MSH-10": 20,   # message control id
    "MSH-12": 60,   # version id
}

# In HL7 2.2 e 2.3, MSH-3 e MSH-5 sono ST con lunghezza 180. Il tipo HD, e
# con esso il limite di 20 sul primo componente, arriva con la 2.3.1.
# Applicare 20 a una 2.3 era sbagliato, e non in astratto: il nome
# "SYSMEX XQ320 Haematologie" (25 caratteri) e' quello registrato nel
# gestionale, il costruttore lo scriveva per intero -- come deve -- e questo
# validatore lo rifiutava. Cinque tentativi di consegna falliti, referto in
# coda, e un errore che parlava di una regola che per quella versione non
# esiste.
_MAX_VERSIONI_VECCHIE = {"MSH-3": 180, "MSH-5": 180}


def _limite(key: str, versione: str) -> int:
    if versione in ("2.2", "2.3") and key in _MAX_VERSIONI_VECCHIE:
        return _MAX_VERSIONI_VECCHIE[key]
    return _MAX[key]


def _split_fields(segment: str) -> List[str]:
    return segment.split("|")


def validate_hl7_message(text: str) -> Report:
    """
    Validate a full HL7 v2.5 message (segments joined by CR).
    """
    rep = Report()

    if not text or "\r" not in text:
        rep.add("ERROR", "MSG", "Empty message or missing CR segment terminator")
        return rep

    segments = [s for s in text.split("\r") if s]
    if not segments:
        rep.add("ERROR", "MSG", "No segments found")
        return rep

    # 1. MSH must be first and well-formed
    if not segments[0].startswith("MSH|^~\\&|"):
        rep.add("ERROR", "MSH",
                "First segment must be MSH with encoding chars '|^~\\&'")
        return rep

    msh = _split_fields(segments[0])
    # After 'MSH|^~\&|' the field separator becomes field 1 (empty in split)
    # Field indexing: MSH-1 is the '|' itself; MSH-2 is '^~\&'; then real fields.

    # La versione dichiarata in MSH-12 decide alcuni limiti: vedi _limite().
    versione = msh[11].strip() if len(msh) > 11 else ""

    # Length checks
    def _check_len(field_idx: int, key: str) -> None:
        if field_idx >= len(msh):
            return
        val = msh[field_idx]
        massimo = _limite(key, versione)
        if len(val) > massimo:
            rep.add("ERROR", key,
                    f"exceeds max length ({massimo} chars): {len(val)} chars",
                    field=val[:40] + "...")

    _check_len(2, "MSH-3")
    _check_len(3, "MSH-4")
    _check_len(4, "MSH-5")
    _check_len(5, "MSH-6")
    _check_len(9, "MSH-10")
    _check_len(11, "MSH-12")

    # Required fields present
    def _check_present(field_idx: int, key: str) -> None:
        if field_idx >= len(msh) or not msh[field_idx].strip():
            rep.add("ERROR", key, "required field is empty")

    _check_present(2, "MSH-3")
    _check_present(3, "MSH-4")
    _check_present(6, "MSH-7")   # message timestamp
    _check_present(8, "MSH-9")   # message type
    _check_present(9, "MSH-10")  # control ID
    _check_present(11, "MSH-12") # version

    # MSH-7 timestamp format: YYYYMMDDHHMMSS[.SSSS][+/-ZZZZ]
    if len(msh) > 6 and msh[6]:
        ts = msh[6]
        if not re.match(r"^\d{14}(\.\d{1,4})?([+-]\d{4})?$", ts):
            rep.add("WARN", "MSH-7",
                    "timestamp format should be YYYYMMDDHHMMSS[±ZZZZ]",
                    field=ts)

    # MSH-12 version check
    if len(msh) > 11 and msh[11]:
        v = msh[11].strip()
        if v not in ("2.3", "2.3.1", "2.4", "2.5", "2.5.1", "2.6", "2.7", "2.7.1", "2.8"):
            rep.add("WARN", "MSH-12",
                    f"unusual HL7 version {v!r} -- most LIS expect 2.3-2.8",
                    field=v)

    # MSH-9 must be like "ORU^R01^ORU_R01" for a lab result
    if len(msh) > 8 and msh[8]:
        mt = msh[8]
        parts = mt.split("^")
        if len(parts) < 2:
            rep.add("WARN", "MSH-9",
                    "message type should have at least type^event, "
                    "recommended type^event^structure",
                    field=mt)

    # Placeholder facility warning (both sending MSH-4 and receiving MSH-6)
    for idx, key in ((3, "MSH-4"), (5, "MSH-6")):
        if len(msh) > idx and msh[idx].strip().upper() in ("PRAXIS", "PRAXIS_NAME"):
            rep.add("WARN", key,
                    f"{key} is a placeholder; change before production",
                    field=msh[idx])

    # 2. Segment presence + basic shape
    seg_names = [s.split("|", 1)[0] for s in segments]
    if "PID" not in seg_names:
        rep.add("WARN", "PID", "PID segment missing -- many LIS require it")
    if "OBR" not in seg_names:
        rep.add("ERROR", "OBR", "OBR segment missing -- required for ORU")
    if "OBX" not in seg_names:
        rep.add("ERROR", "OBX", "no OBX segments -- an ORU without results is invalid")

    # 3. Every OBX: value type, LOINC placeholder, value present
    obx_seq_expected = 1
    for seg in segments:
        if not seg.startswith("OBX|"):
            continue
        fields = _split_fields(seg)
        seq   = fields[1] if len(fields) > 1 else ""
        vt    = fields[2] if len(fields) > 2 else ""
        obs_id = fields[3] if len(fields) > 3 else ""
        value = fields[5] if len(fields) > 5 else ""
        loc   = f"OBX-{seq or obx_seq_expected}"

        if not vt:
            rep.add("ERROR", loc, "OBX-2 (value type) required, e.g. NM or ST")
        elif vt not in ("NM", "ST", "TX", "CE", "DT", "TM", "TS", "ED", "CX", "SN"):
            rep.add("WARN", loc, f"OBX-2 value type {vt!r} is unusual")

        if not obs_id:
            rep.add("ERROR", loc, "OBX-3 (observation identifier) required")
        elif "99999-9" in obs_id:
            rep.add("WARN", loc,
                    "OBX-3 uses placeholder LOINC 99999-9 -- LIS will likely reject",
                    field=obs_id)

        if not value:
            rep.add("ERROR", loc, "OBX-5 (observation value) is empty")

        obx_seq_expected += 1

    return rep
