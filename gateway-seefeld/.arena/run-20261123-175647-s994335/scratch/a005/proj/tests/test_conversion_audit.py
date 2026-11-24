"""
Tests for the conversion audit trail — verify every silent transformation
the parser performs is recorded, exposed, and inspectable ex-post by the
clinic admin.

Motivating question: "Come faccio a sapere se il gateway ha cambiato un
valore o un'unità senza che nessuno se ne accorga?"

Answer: these tests prove the audit records it AND the plausibility gate
flags it.
"""
from __future__ import annotations

import json

from src.adapters.sysmex_reader import _parse_astm, _normalize_value
from src.common.conversion_audit import ConversionAudit, ValueChange, sha_of
from src.common.plausibility import check, is_double_conversion


# ── ValueChange plumbing ──────────────────────────────────────────────────────

def test_value_change_detects_no_op() -> None:
    vc = ValueChange(raw_code="WBC", sent_code="WBC",
                     raw_value="7.4", sent_value="7.4",
                     raw_unit="10*3/uL", sent_unit="10*3/uL")
    assert vc.changed is False


def test_value_change_detects_unit_normalization() -> None:
    vc = ValueChange(raw_code="HGB", sent_code="HGB",
                     raw_value="14.2", sent_value="14.2",
                     raw_unit="g/dl", sent_unit="g/dL")
    assert vc.changed is True


def test_value_change_serializes_transforms() -> None:
    vc = ValueChange(raw_code="LYM", sent_code="LYMPH",
                     raw_value="0.42", sent_value="42.0",
                     raw_unit="", sent_unit="%",
                     transforms=["code-rename", "HCT-frac-to-percent"])
    d = vc.to_dict()
    assert d["changed"] is True
    assert d["transforms"] == ["code-rename", "HCT-frac-to-percent"]


# ── _normalize_value returns the transform trail ──────────────────────────────

def test_normalize_value_records_hct_conversion() -> None:
    new_val, xforms = _normalize_value("HCT", "0.42")
    assert new_val == "42.0"
    assert any("HCT-frac-to-percent" in x for x in xforms)


def test_normalize_value_no_transform_on_already_percent() -> None:
    new_val, xforms = _normalize_value("HCT", "42.0")
    assert new_val == "42.0"
    assert not any("HCT-frac" in x for x in xforms)


def test_normalize_value_leaves_unrelated_untouched() -> None:
    new_val, xforms = _normalize_value("WBC", "7.4")
    assert new_val == "7.4"


# ── End-to-end: audit captures HCT double-conversion risk ─────────────────────

_MSG_HCT_AS_FRACTION = (
    "H|\\^&|||XQ-320^00-00^11001^^^^12345678||||||||E1394-97\r"
    "P|1||PAT-42\r"
    "O|1||SN0042||R\r"
    "R|1|^^^^HCT^1|0.42|%||N||||||20260828093000\r"   # device sends as fraction
    "L|1|N\r"
)


def test_parser_records_raw_and_sent_value_for_hct() -> None:
    r = _parse_astm(_MSG_HCT_AS_FRACTION, "XQ-320")
    assert r is not None
    hct = next(o for o in r["observations"] if o["analyte"] == "HCT")
    assert hct["raw_value"] == "0.42"
    assert hct["value"] == "42.0"     # converted
    assert any("HCT-frac-to-percent" in t for t in hct["transforms"])


def test_parser_records_code_rename_lym_to_lymph() -> None:
    msg = (
        "H|\\^&|||XQ-320\r"
        "P|1||PAT-42\r"
        "O|1||SN0042||R\r"
        "R|1|^^^^LYM^1|2.1|10*3/uL||N||||||20260828\r"   # device says "LYM"
        "L|1|N\r"
    )
    r = _parse_astm(msg, "XQ-320")
    assert r is not None
    lym = r["observations"][0]
    assert lym["raw_analyte"] == "LYM"
    assert lym["analyte"] == "LYMPH"
    assert any("code-rename" in t for t in lym["transforms"])


# ── Plausibility gate ─────────────────────────────────────────────────────────

def test_plausibility_flags_impossible_hgb() -> None:
    ok, reason = check("HGB", 42.0, "g/dL")
    assert ok is False
    assert "HGB" in reason and "42.0" in reason


def test_plausibility_accepts_normal_hgb() -> None:
    ok, _ = check("HGB", 14.2, "g/dL")
    assert ok is True


def test_plausibility_accepts_extreme_but_possible_wbc() -> None:
    # Leukemia case — 250×10^3/uL is real
    ok, _ = check("WBC", 250.0, "10^3/uL")
    assert ok is True


def test_plausibility_ignores_unknown_analytes() -> None:
    ok, reason = check("UNKNOWN_XYZ", 9999.9, "")
    assert ok is True
    assert reason == ""


# ── Double-conversion detector ────────────────────────────────────────────────

def test_double_conversion_detected() -> None:
    # Raw 42.0 % → sent 4200 %.  Ratio ~100 → caught.
    assert is_double_conversion("HCT", 42.0, 4200.0) is True


def test_double_conversion_not_detected_on_normal_case() -> None:
    # Raw 0.42 fraction → sent 42.0 %.  Correct one-time conversion.
    assert is_double_conversion("HCT", 0.42, 42.0) is False


def test_double_conversion_never_triggers_on_wbc() -> None:
    # WBC is not one of the vulnerable codes.
    assert is_double_conversion("WBC", 1.0, 100.0) is False


# ── ConversionAudit end-to-end ────────────────────────────────────────────────

def test_audit_json_contains_raw_hash_and_changes() -> None:
    audit = ConversionAudit(
        device="XQ-320",
        sample_id_raw="SN0042A", sample_id_sent="SN0042",
        patient_id_raw="SN0042A", patient_id_sent="SN0042",
        raw_payload_sha=sha_of(b"raw-bytes"),
        raw_payload_hex="7261772d6279746573",
    )
    audit.add_change(ValueChange(
        raw_code="HCT", sent_code="HCT",
        raw_value="0.42", sent_value="42.0",
        raw_unit="%", sent_unit="%",
        transforms=["HCT-frac-to-percent"],
    ))
    audit.add_warning("sample_id changed: 'SN0042A' → 'SN0042' (strip_suffix)")
    parsed = json.loads(audit.to_json())
    assert parsed["sample"]["raw"] == "SN0042A"
    assert parsed["sample"]["sent"] == "SN0042"
    assert parsed["raw_payload_sha"].startswith("")   # any 64-hex is fine
    assert len(parsed["raw_payload_sha"]) == 64
    assert parsed["changes"][0]["changed"] is True
    assert "strip_suffix" in parsed["warnings"][0]


def test_sha_is_deterministic() -> None:
    a = sha_of("hello")
    b = sha_of(b"hello")
    assert a == b
    assert len(a) == 64
