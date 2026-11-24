"""
FHIR R4 exporter.

Alternative to HL7 v2.5 for LIS/PIS that speak FHIR.
Produces a `transaction` Bundle with:
  * Patient      (patient demographics)
  * Specimen     (sample_id, disc_name, lot_id)
  * DiagnosticReport (one per result)
  * Observation  (one per analyte, referenced by DiagnosticReport)

Transports:
  * POST as JSON to a target `fhir_endpoint` (Bundle) -- see FHIRDispatcher
  * Also usable as file-drop (write .json to a watch folder)

We build the JSON directly (no fhirclient dep) so this stays lightweight.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.settings import HL7Config

log = logging.getLogger("loc200.fhir")

_LOINC_SYSTEM = "http://loinc.org"
_JMNX_SYSTEM  = "http://jerumed-nexus.ch/fhir/CodeSystem/analyte"


def _ts_iso(dt: Optional[datetime] = None) -> str:
    d = dt or datetime.now().astimezone()
    if d.tzinfo is None:
        d = d.astimezone()
    return d.isoformat()


def _uuid_urn() -> str:
    return f"urn:uuid:{uuid.uuid4()}"


class FHIRBundleBuilder:
    """Convert an internal result dict into a FHIR R4 transaction Bundle."""

    def __init__(self, hl7_cfg: HL7Config) -> None:
        # We reuse HL7Config for identity fields (facility, application).
        self._cfg = hl7_cfg
        # Lazy-load the LOINC map from the same source the HL7 builder uses.
        from src.hl7.builder import _LoincMap
        self._loinc = _LoincMap(hl7_cfg.loinc_map_path)

    def build(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Return a FHIR R4 Bundle (dict, JSON-serialisable)."""
        patient_id  = str(result.get("patient_id", "")) or "UNKNOWN"
        sample_id   = str(result.get("sample_id", "")) or patient_id
        device_name = str(result.get("device", "")) or "unknown-device"

        patient_urn  = _uuid_urn()
        specimen_urn = _uuid_urn()
        report_urn   = _uuid_urn()
        obs_urns: List[str] = []

        # 1. Patient
        name = result.get("patient_name", "").strip()
        parts = name.split(" ", 1) if name else []
        patient_res = {
            "resourceType": "Patient",
            "identifier": [{
                "system": f"http://jerumed-nexus.ch/patient/{self._cfg.sending_facility}",
                "value":  patient_id,
            }],
            "gender": {"M": "male", "F": "female"}.get(
                (result.get("gender") or "").upper(), "unknown"),
        }
        if parts:
            patient_res["name"] = [{
                "family": parts[0] if parts else "",
                "given":  ([parts[1]] if len(parts) > 1 else []),
            }]

        # 2. Specimen
        specimen_res = {
            "resourceType": "Specimen",
            "identifier": [{"value": sample_id}],
            "subject": {"reference": patient_urn},
            "type": {"text": result.get("disc_name") or "unspecified"},
            "accessionIdentifier": {"value": sample_id},
            "receivedTime": _ts_iso(result.get("timestamp")),
        }
        if result.get("lot_id"):
            specimen_res["container"] = [{"identifier": [{"value": result["lot_id"]}]}]

        # 3. Observations
        observations: List[Dict[str, Any]] = []
        for obs in result.get("observations", []):
            code = str(obs.get("analyte", ""))
            loinc_rec = self._loinc.get(code)
            loinc = loinc_rec.get("loinc", "99999-9")

            obs_res: Dict[str, Any] = {
                "resourceType": "Observation",
                "status": "final",
                "code": {
                    "coding": [
                        {"system": _LOINC_SYSTEM, "code": loinc,
                         "display": loinc_rec.get("name", code)},
                        {"system": _JMNX_SYSTEM,  "code": code,
                         "display": obs.get("name_de", code)},
                    ],
                    "text": obs.get("name_de", code),
                },
                "subject": {"reference": patient_urn},
                "specimen": {"reference": specimen_urn},
                "effectiveDateTime": _ts_iso(result.get("timestamp")),
                "issued":            _ts_iso(),
            }
            if obs.get("value_num") is not None:
                obs_res["valueQuantity"] = {
                    "value":  float(obs["value_num"]),
                    "unit":   obs.get("unit") or loinc_rec.get("unit", ""),
                    "system": "http://unitsofmeasure.org",
                    "code":   obs.get("unit") or loinc_rec.get("unit", ""),
                }
            else:
                obs_res["valueString"] = str(obs.get("value", ""))

            flag = obs.get("flag") or ""
            if flag in ("H", "L", "N", "HH", "LL", "A", "AA"):
                obs_res["interpretation"] = [{
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                        "code":   flag,
                    }],
                }]

            ref_low  = obs.get("ref_low")
            ref_high = obs.get("ref_high")
            if ref_low is not None or ref_high is not None:
                rr: Dict[str, Any] = {}
                if ref_low is not None:
                    rr["low"] = {"value": float(ref_low),
                                 "unit": obs.get("unit") or ""}
                if ref_high is not None:
                    rr["high"] = {"value": float(ref_high),
                                  "unit": obs.get("unit") or ""}
                obs_res["referenceRange"] = [rr]

            obs_urn = _uuid_urn()
            obs_urns.append(obs_urn)
            observations.append({"urn": obs_urn, "res": obs_res})

        # 4. DiagnosticReport
        report_res = {
            "resourceType": "DiagnosticReport",
            "status": "final",
            "code": {
                "coding": [{
                    "system": _LOINC_SYSTEM,
                    "code":   "26436-6",     # Laboratory studies (set)
                    "display": "Laboratory studies",
                }],
                "text": device_name,
            },
            "subject":  {"reference": patient_urn},
            "specimen": [{"reference": specimen_urn}],
            "effectiveDateTime": _ts_iso(result.get("timestamp")),
            "issued":            _ts_iso(),
            "result":  [{"reference": u} for u in obs_urns],
            "performer": [{"display": device_name}],
        }

        # 5. Bundle
        entries = [
            {"fullUrl": patient_urn,
             "resource": patient_res,
             "request":  {"method": "POST", "url": "Patient"}},
            {"fullUrl": specimen_urn,
             "resource": specimen_res,
             "request":  {"method": "POST", "url": "Specimen"}},
        ]
        for o in observations:
            entries.append({
                "fullUrl": o["urn"],
                "resource": o["res"],
                "request": {"method": "POST", "url": "Observation"},
            })
        entries.append({
            "fullUrl": report_urn,
            "resource": report_res,
            "request":  {"method": "POST", "url": "DiagnosticReport"},
        })

        return {
            "resourceType": "Bundle",
            "type":         "transaction",
            "timestamp":    _ts_iso(),
            "entry":        entries,
        }

    def build_json(self, result: Dict[str, Any], pretty: bool = False) -> bytes:
        b = self.build(result)
        if pretty:
            return json.dumps(b, indent=2, ensure_ascii=False).encode("utf-8")
        return json.dumps(b, ensure_ascii=False).encode("utf-8")
