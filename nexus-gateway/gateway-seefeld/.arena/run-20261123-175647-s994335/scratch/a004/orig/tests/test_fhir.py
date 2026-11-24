"""Tests for FHIR R4 builder."""
from __future__ import annotations

import json
from datetime import datetime

from config.settings import HL7Config
from src.hl7.fhir_builder import FHIRBundleBuilder


def _sample():
    return {
        "timestamp":    datetime(2025, 1, 1, 12, 0, 0),
        "sample_id":    "S001",
        "patient_id":   "P123",
        "patient_name": "Mueller Hans",
        "gender":       "M",
        "device":       "Sysmex XN-550",
        "disc_name":    "CBC",
        "lot_id":       "L-42",
        "observations": [{
            "analyte":   "AST",
            "value":     "13",
            "value_num": 13.0,
            "flag":      "L",
            "ref_low":   15.0,
            "ref_high":  40.0,
            "unit":      "U/L",
        }, {
            "analyte":   "GLU",
            "value":     "---",
            "value_num": None,
            "flag":      "",
            "ref_low":   None,
            "ref_high":  None,
            "unit":      "mmol/L",
        }],
    }


def test_bundle_shape():
    b = FHIRBundleBuilder(HL7Config()).build(_sample())
    assert b["resourceType"] == "Bundle"
    assert b["type"] == "transaction"
    types = [e["resource"]["resourceType"] for e in b["entry"]]
    assert "Patient" in types
    assert "Specimen" in types
    assert "DiagnosticReport" in types
    assert types.count("Observation") == 2


def test_observation_loinc_codes_present():
    b = FHIRBundleBuilder(HL7Config()).build(_sample())
    obs = [e["resource"] for e in b["entry"]
           if e["resource"]["resourceType"] == "Observation"]
    ast = next(o for o in obs if o["code"]["text"] == "AST")
    codings = ast["code"]["coding"]
    assert any(c["system"] == "http://loinc.org" and c["code"] == "1920-8"
               for c in codings)


def test_flag_mapped_to_interpretation():
    b = FHIRBundleBuilder(HL7Config()).build(_sample())
    ast = next(e["resource"] for e in b["entry"]
               if e["resource"]["resourceType"] == "Observation"
               and e["resource"]["code"]["text"] == "AST")
    assert ast["interpretation"][0]["coding"][0]["code"] == "L"


def test_non_numeric_uses_valueString():
    b = FHIRBundleBuilder(HL7Config()).build(_sample())
    glu = next(e["resource"] for e in b["entry"]
               if e["resource"]["resourceType"] == "Observation"
               and e["resource"]["code"]["text"] == "GLU")
    assert "valueString" in glu
    assert "valueQuantity" not in glu


def test_reference_range():
    b = FHIRBundleBuilder(HL7Config()).build(_sample())
    ast = next(e["resource"] for e in b["entry"]
               if e["resource"]["resourceType"] == "Observation"
               and e["resource"]["code"]["text"] == "AST")
    rr = ast["referenceRange"][0]
    assert rr["low"]["value"] == 15.0
    assert rr["high"]["value"] == 40.0


def test_bundle_json_is_valid():
    b = FHIRBundleBuilder(HL7Config()).build_json(_sample())
    parsed = json.loads(b)
    assert parsed["resourceType"] == "Bundle"
