"""
Conversion audit trail — records every transformation the gateway performs
between the raw device payload and the HL7 message sent to the LIS.

Motivation (from a real question by a clinic operator):
> "Come faccio a sapere che il gateway non ha cambiato un valore o un'unità
>  in modo silenzioso? Se il medico vede un numero sbagliato, come faccio
>  a scoprirlo?"

Answer: every sample now carries an audit dict listing per-analyte the
raw value + code + unit received AND the value + code + unit emitted. It
is stored in history.db (JSON blob) and surfaced in the Web UI under
"Frame inspector". Nothing to configure — auditing is always on.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ValueChange:
    """One analyte before/after transformation."""
    raw_code:      str
    sent_code:     str
    raw_value:     str
    sent_value:    str
    raw_unit:      str
    sent_unit:     str
    transforms:    list[str] = field(default_factory=list)  # human-readable trail

    @property
    def changed(self) -> bool:
        return (self.raw_code  != self.sent_code
                or self.raw_value != self.sent_value
                or self.raw_unit  != self.sent_unit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw":        {"code": self.raw_code,  "value": self.raw_value,  "unit": self.raw_unit},
            "sent":       {"code": self.sent_code, "value": self.sent_value, "unit": self.sent_unit},
            "changed":    self.changed,
            "transforms": self.transforms,
        }


@dataclass
class ConversionAudit:
    """Complete audit for one sample: raw payload + per-analyte changes."""
    device:            str
    sample_id_raw:     str
    sample_id_sent:    str
    patient_id_raw:    str
    patient_id_sent:   str
    raw_payload_sha:   str    # sha256 of the exact bytes received (proof)
    raw_payload_hex:   str    # first 256 bytes hex, for inspection
    changes:           list[ValueChange] = field(default_factory=list)
    warnings:          list[str] = field(default_factory=list)
    audited_at:        str = ""

    def __post_init__(self) -> None:
        if not self.audited_at:
            self.audited_at = datetime.utcnow().isoformat() + "Z"

    def add_change(self, c: ValueChange) -> None:
        self.changes.append(c)

    def add_warning(self, w: str) -> None:
        self.warnings.append(w)

    def to_json(self) -> str:
        return json.dumps({
            "device":          self.device,
            "sample":          {"raw": self.sample_id_raw,  "sent": self.sample_id_sent},
            "patient":         {"raw": self.patient_id_raw, "sent": self.patient_id_sent},
            "raw_payload_sha": self.raw_payload_sha,
            "raw_payload_hex": self.raw_payload_hex,
            "changes":         [c.to_dict() for c in self.changes],
            "warnings":        self.warnings,
            "audited_at":      self.audited_at,
        }, ensure_ascii=False)


def sha_of(payload: bytes | str) -> str:
    """Deterministic SHA-256 of the raw payload — proof of what came in."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()


def hex_head(payload: bytes | str, n: int = 256) -> str:
    if isinstance(payload, str):
        payload = payload.encode("ascii", errors="replace")
    return payload[:n].hex()


def build_audit_for(
    device: str,
    sample_raw: str,
    sample_sent: str,
    patient_raw: str,
    patient_sent: str,
    raw_payload: bytes | str,
    observations: list[dict[str, Any]],
) -> str:
    """
    Shared helper — every adapter uses this so the audit format is
    identical across Sysmex, Cobas, UC-1000, LOC-200 and Reflotron.

    Each observation may carry these optional keys added by its parser:
        raw_analyte, raw_value, raw_unit, transforms (list[str])
    plus the standard analyte/value/unit/value_num fields.
    """
    from src.common.plausibility import check as plausibility_check, is_double_conversion

    audit = ConversionAudit(
        device=device,
        sample_id_raw=sample_raw or "",
        sample_id_sent=sample_sent or "",
        patient_id_raw=patient_raw or "",
        patient_id_sent=patient_sent or "",
        raw_payload_sha=sha_of(raw_payload),
        raw_payload_hex=hex_head(raw_payload),
    )
    if sample_raw and sample_sent and sample_raw != sample_sent:
        audit.add_warning(f"sample_id changed: {sample_raw!r} → {sample_sent!r}")
    if patient_raw and patient_sent and patient_raw != patient_sent:
        audit.add_warning(f"patient_id changed: {patient_raw!r} → {patient_sent!r}")

    for obs in observations:
        code_sent = str(obs.get("analyte", ""))
        vc = ValueChange(
            raw_code=str(obs.get("raw_analyte", code_sent)),
            sent_code=code_sent,
            raw_value=str(obs.get("raw_value", obs.get("value", ""))),
            sent_value=str(obs.get("value", "")),
            raw_unit=str(obs.get("raw_unit", obs.get("unit", ""))),
            sent_unit=str(obs.get("unit", "")),
            transforms=list(obs.get("transforms") or []),
        )
        audit.add_change(vc)

        # Plausibility
        value_num = obs.get("value_num")
        try:
            value_num = float(value_num) if value_num is not None else None
        except (ValueError, TypeError):
            value_num = None
        ok, reason = plausibility_check(code_sent, value_num, str(obs.get("unit", "")))
        if not ok:
            audit.add_warning(reason)
            obs["flag"] = (obs.get("flag") or "") + "TC"

        # Double-conversion sanity
        try:
            raw_num = float(vc.raw_value.replace(",", "."))
        except (ValueError, TypeError):
            raw_num = None
        if is_double_conversion(code_sent, raw_num, value_num):
            audit.add_warning(
                f"suspicious ×100 on {code_sent}: raw {raw_num} → sent {value_num}"
            )
    return audit.to_json()
