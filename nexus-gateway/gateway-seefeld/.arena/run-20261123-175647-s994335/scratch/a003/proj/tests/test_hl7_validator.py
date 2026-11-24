"""Tests for HL7 validator + rewrites."""
from __future__ import annotations


from src.hl7.validator import validate_hl7_message
from src.hl7.rewrites import apply_rewrites


_MSH  = "MSH|^~\\&|APP|FAC|LIS|PRAXIS|20250101120000+0200||ORU^R01^ORU_R01|CTL001|P|2.5|||NE|AL||UNICODE UTF-8"
_PID  = "PID||P123|P123||Mueller^Hans||||M"
_PV1  = "PV1|1|O"
_OBR  = "OBR|1|||P123^P123^L||20250101120000|20250101120000|||||||||||||F"
_OBX  = "OBX|1|NM|1920-8^AST^LN|1|10|U/L^U/L^ISO+|15^40|||||F|||20250101120000"


def _msg(*extra_obx):
    parts = [_MSH, _PID, _PV1, _OBR, _OBX] + list(extra_obx)
    return "\r".join(parts) + "\r"


def test_valid_message_passes():
    rep = validate_hl7_message(_msg())
    assert rep.is_valid, [f.message for f in rep.errors]


def test_msh_3_too_long_is_error():
    text = _msg().replace("|APP|", "|" + "X" * 25 + "|")
    rep = validate_hl7_message(text)
    assert not rep.is_valid
    assert any("MSH-3" in e.segment for e in rep.errors)


def test_missing_obr_is_error():
    text = "\r".join([_MSH, _PID, _PV1, _OBX]) + "\r"
    rep = validate_hl7_message(text)
    assert not rep.is_valid
    assert any("OBR" in e.segment for e in rep.errors)


def test_missing_obx_is_error():
    text = "\r".join([_MSH, _PID, _PV1, _OBR]) + "\r"
    rep = validate_hl7_message(text)
    assert not rep.is_valid


def test_placeholder_loinc_is_warning():
    weird_obx = "OBX|2|NM|99999-9^UNKNOWN^LN|1|10|U/L|||||F"
    rep = validate_hl7_message(_msg(weird_obx))
    assert rep.is_valid
    assert any("99999-9" in f.message for f in rep.warnings)


def test_placeholder_facility_is_warning():
    text = _msg().replace("|PRAXIS|", "|PRAXIS_NAME|", 1)
    rep = validate_hl7_message(text)
    assert any(f.segment in ("MSH-4", "MSH-6") for f in rep.warnings)


def test_empty_obx_value_is_error():
    weird_obx = "OBX|2|NM|1743-4^ALT^LN|1||U/L|||||F"  # missing value
    rep = validate_hl7_message(_msg(weird_obx))
    assert not rep.is_valid


# ── rewrites (uses tmp_path for the rules dir) ────────────────────────────────

def test_rewrites_noop_when_no_file(tmp_path, monkeypatch):
    from src.hl7 import rewrites as _r
    monkeypatch.setattr(_r, "_RULES_DIR", tmp_path)
    text = _msg()
    assert apply_rewrites(text, "no_rules_target") == text


def test_rewrites_regex_replace(tmp_path, monkeypatch):
    from src.hl7 import rewrites as _r
    monkeypatch.setattr(_r, "_RULES_DIR", tmp_path)
    (tmp_path / "vitomed.yaml").write_text(
        "- name: strip Dr\n  apply_to: [PID]\n  field: 5\n"
        "  match: '^Dr\\.\\s*'\n  replace: ''\n"
    )
    text = _msg().replace("Mueller^Hans", "Dr. Mueller^Hans")
    out = apply_rewrites(text, "vitomed")
    assert "Dr. Mueller" not in out
    assert "Mueller^Hans" in out


def test_rewrites_set_value(tmp_path, monkeypatch):
    from src.hl7 import rewrites as _r
    monkeypatch.setattr(_r, "_RULES_DIR", tmp_path)
    (tmp_path / "curamed.yaml").write_text(
        "- name: force fac\n  apply_to: [MSH]\n  field: 4\n  set: NEW_FAC\n"
    )
    out = apply_rewrites(_msg(), "curamed")
    assert "|NEW_FAC|" in out


def test_rewrites_component(tmp_path, monkeypatch):
    from src.hl7 import rewrites as _r
    monkeypatch.setattr(_r, "_RULES_DIR", tmp_path)
    (tmp_path / "aeskulap.yaml").write_text(
        "- name: strip unit qualifier\n  apply_to: [OBX]\n  field: 6\n"
        "  component: 1\n  match: '^(.*?)/.*$'\n  replace: '\\1'\n"
    )
    text = _msg("OBX|2|NM|CHOL^Chol^LN|1|5|mg/dL^mg/dL^ISO+|0-200|||||F")
    out = apply_rewrites(text, "aeskulap")
    assert "|mg^mg/dL^ISO+|" in out
