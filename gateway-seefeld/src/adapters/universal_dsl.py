"""
Universal Protocol Adapter — parse any line-based / record-based device
from a YAML DSL spec, no Python code required.

DSL example (Menarini HA-8180T):

    protocol_name: menarini_ha_8180t
    transport:    rs232
    framing:
      message_start: 0x02         # STX (optional)
      message_end:   0x03         # ETX
      line_separator: "\r"
    encoding: ascii
    records:
      header:
        pattern:      "^H\\|"
        fields:
          sender:     {index: 4, split: "^", pick: 0}
      patient:
        pattern:      "^P\\|"
        fields:
          patient_id: {index: 3}
          patient_name: {index: 5, split: "^", pick: 1}
      observation:
        pattern:      "^R\\|"
        fields:
          analyte:    {index: 2, split: "^", pick: 3}
          value:      {index: 3}
          unit:       {index: 4}
          flag:       {index: 6}

Runtime interprets the spec and produces the canonical dict the router
expects. Adding a new device becomes "drop a YAML spec in
config/protocols/*.yaml" — zero code, zero deploy.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

log = logging.getLogger("loc200.universal_dsl")


@dataclass
class FieldSpec:
    index:  int
    split:  Optional[str] = None    # e.g. "^" for HL7 component split
    pick:   Optional[int] = None    # after split, which piece
    regex:  Optional[str] = None    # optional regex extract


@dataclass
class RecordSpec:
    pattern: str
    fields:  dict[str, FieldSpec] = field(default_factory=dict)


@dataclass
class ProtocolSpec:
    protocol_name: str
    transport:     str
    encoding:      str
    line_separator: str
    records:       dict[str, RecordSpec]
    field_delimiter: str = "|"


def _mk_field(f: dict[str, Any] | int) -> FieldSpec:
    if isinstance(f, int):
        return FieldSpec(index=f)
    return FieldSpec(
        index=int(f["index"]),
        split=f.get("split"),
        pick=int(f["pick"]) if "pick" in f else None,
        regex=f.get("regex"),
    )


def load_spec(path: Path) -> ProtocolSpec:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    records: dict[str, RecordSpec] = {}
    for name, r in (data.get("records") or {}).items():
        fields = {k: _mk_field(v) for k, v in (r.get("fields") or {}).items()}
        records[name] = RecordSpec(pattern=r.get("pattern", ""), fields=fields)
    return ProtocolSpec(
        protocol_name=data["protocol_name"],
        transport=data.get("transport", "rs232"),
        encoding=data.get("encoding", "ascii"),
        line_separator=data.get("framing", {}).get("line_separator", "\r"),
        field_delimiter=data.get("field_delimiter", "|"),
        records=records,
    )


def _extract(field: FieldSpec, parts: list[str]) -> str:
    if field.index >= len(parts):
        return ""
    val = parts[field.index].strip()
    if field.split:
        pieces = val.split(field.split)
        if field.pick is not None and field.pick < len(pieces):
            val = pieces[field.pick].strip()
    if field.regex:
        m = re.search(field.regex, val)
        val = m.group(1) if m and m.groups() else (m.group(0) if m else "")
    return val


def parse_message(spec: ProtocolSpec, text: str) -> Optional[dict[str, Any]]:
    """Return canonical result dict or None if nothing meaningful was found."""
    lines = [l for l in text.replace("\r\n", "\r").split(spec.line_separator) if l.strip()]
    patient_id = sample_id = patient_name = ""
    observations: list[dict[str, Any]] = []

    compiled: dict[str, tuple[re.Pattern, RecordSpec]] = {
        name: (re.compile(r.pattern), r) for name, r in spec.records.items()
    }

    for line in lines:
        parts = line.split(spec.field_delimiter)
        for name, (rx, rspec) in compiled.items():
            if rx.match(line):
                extracted = {k: _extract(f, parts) for k, f in rspec.fields.items()}
                if name == "patient":
                    patient_id = extracted.get("patient_id", patient_id)
                    patient_name = extracted.get("patient_name", patient_name)
                elif name == "order":
                    sample_id = extracted.get("sample_id", sample_id) or patient_id
                elif name == "observation":
                    analyte = extracted.get("analyte", "")
                    value = extracted.get("value", "")
                    if not analyte or not value:
                        continue
                    try:
                        value_num = float(value.replace(",", "."))
                    except (ValueError, TypeError):
                        value_num = None
                    observations.append({
                        "analyte":   analyte,
                        "value":     value,
                        "value_num": value_num,
                        "unit":      extracted.get("unit", ""),
                        "flag":      extracted.get("flag", ""),
                        "loinc":     "99999-9",
                        "name_de":   analyte,
                        "ref_low":   None, "ref_high": None,
                    })
                break

    if not observations:
        return None
    if not sample_id:
        sample_id = patient_id or "UNKNOWN"
    return {
        "sample_id":    sample_id,
        "patient_id":   patient_id or sample_id,
        "patient_name": patient_name,
        "observations": observations,
        "device":       spec.protocol_name,
    }


def load_all_specs() -> dict[str, ProtocolSpec]:
    """Scan config/protocols/ for user-supplied DSL specs."""
    root = Path("config/protocols")
    if not root.exists():
        return {}
    out: dict[str, ProtocolSpec] = {}
    for f in root.glob("*.yaml"):
        try:
            s = load_spec(f)
            out[s.protocol_name] = s
            log.info("Loaded protocol spec: %s (%d records)",
                     s.protocol_name, len(s.records))
        except Exception as exc:
            log.warning("Cannot load protocol %s: %s", f.name, exc)
    return out
