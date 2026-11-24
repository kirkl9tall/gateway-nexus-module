"""
tests/test_security.py
Tests for hardened paths: HL7 escape, ACK correlation, encoding, auth.
"""
from __future__ import annotations

import pytest
from datetime import datetime

from config.settings import HL7Config
from src.hl7.builder import HL7Builder, _esc


# ── HL7 escape ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected_substr", [
    ("Müller",           "Müller"),          # unicode passes through
    ("Foo|Bar",          r"Foo\F\Bar"),
    ("Foo^Bar",          r"Foo\S\Bar"),
    ("Foo~Bar",          r"Foo\R\Bar"),
    ("Foo&Bar",          r"Foo\T\Bar"),
    ("Foo\\Bar",         r"Foo\E\Bar"),
    ("Foo\rBar",         r"Foo\X0D\Bar"),
    ("Foo\nBar",         r"Foo\X0A\Bar"),
    ("Foo\x1CBar",       r"Foo\X1C\Bar"),
    ("Foo\x0BBar",       r"Foo\X0B\Bar"),
])
def test_esc_escapes_all_special_chars(raw, expected_substr):
    out = _esc(raw)
    assert expected_substr in out, f"Expected {expected_substr!r} in {out!r}"


def test_esc_none_returns_empty():
    assert _esc(None) == ""


def test_hostile_patient_name_cannot_break_framing():
    """A CR in patient name must NOT create a new segment."""
    cfg = HL7Config(sending_facility="TEST")
    builder = HL7Builder(cfg)
    result = {
        "timestamp": datetime(2025, 1, 1, 12, 0, 0),
        "sample_id": "S1", "patient_id": "P1",
        "patient_name": "Evil\rMSH|^~\\&|HACKED|",
        "gender": "M", "disc_name": "K1", "lot_id": "L1",
        "observations": [{"analyte": "AST", "value": "10", "value_num": 10.0,
                          "flag": "", "ref_low": 5, "ref_high": 30, "unit": "U/L"}],
    }
    msg = builder.build_oru_r01(result)
    text = msg.to_string()
    # Exactly one MSH — the injected one must be escaped
    assert text.count("\rMSH|") == 0
    assert text.count("MSH|") == 1
    assert "\\X0D\\" in text  # escaped CR


# ── Encoding coherence ───────────────────────────────────────────────────────

def test_utf8_charset_matches_wire_encoding():
    cfg = HL7Config(charset="UNICODE UTF-8", sending_facility="P")
    b = HL7Builder(cfg)
    r = {"timestamp": datetime(2025, 1, 1), "sample_id": "S",
         "patient_id": "P", "patient_name": "Müller",
         "gender": "M", "disc_name": "D", "lot_id": "L",
         "observations": [{"analyte": "AST", "value": "1", "value_num": 1.0,
                           "flag": "", "ref_low": None, "ref_high": None,
                           "unit": "U/L"}]}
    msg = b.build_oru_r01(r)
    assert "UNICODE UTF-8" in msg.to_string()
    # Round-trip must preserve umlaut in the declared codec.
    payload = msg.to_mllp()
    body = payload[1:-2]  # strip VT / FS+CR
    assert "Müller" in body.decode("utf-8")


def test_iso8859_charset_uses_latin1_encoding():
    cfg = HL7Config(charset="8859/1", sending_facility="P")
    b = HL7Builder(cfg)
    r = {"timestamp": datetime(2025, 1, 1), "sample_id": "S",
         "patient_id": "P", "patient_name": "Müller",
         "gender": "M", "disc_name": "D", "lot_id": "L",
         "observations": [{"analyte": "AST", "value": "1", "value_num": 1.0,
                           "flag": "", "ref_low": None, "ref_high": None,
                           "unit": "U/L"}]}
    msg = b.build_oru_r01(r)
    assert "8859/1" in msg.to_string()
    payload = msg.to_mllp()
    body = payload[1:-2]
    assert "Müller" in body.decode("iso-8859-1")


# ── Timezone ──────────────────────────────────────────────────────────────────

def test_timestamp_includes_tz_by_default():
    cfg = HL7Config(sending_facility="P")
    b = HL7Builder(cfg)
    r = {"timestamp": None, "sample_id": "", "patient_id": "",
         "patient_name": "", "gender": "", "disc_name": "", "lot_id": "",
         "observations": [{"analyte": "X", "value": "1", "value_num": 1.0,
                           "flag": "", "ref_low": None, "ref_high": None, "unit": ""}]}
    msg = b.build_oru_r01(r)
    # Look for MSH-7 timestamp — should have +HHMM or -HHMM at the end of the base
    import re
    m = re.search(r"MSH\|[^|]+\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|(\d{14}[+-]\d{4})", msg.to_string())
    assert m, f"Expected TZ-aware timestamp, got: {msg.to_string()[:200]}"


def test_timestamp_no_tz_when_disabled():
    cfg = HL7Config(sending_facility="P", include_timezone=False)
    b = HL7Builder(cfg)
    r = {"timestamp": datetime(2025, 1, 1, 12, 0, 0), "sample_id": "", "patient_id": "",
         "patient_name": "", "gender": "", "disc_name": "", "lot_id": "",
         "observations": [{"analyte": "X", "value": "1", "value_num": 1.0,
                           "flag": "", "ref_low": None, "ref_high": None, "unit": ""}]}
    msg = b.build_oru_r01(r)
    assert "20250101120000" in msg.to_string()


# ── ACK correlation ──────────────────────────────────────────────────────────

from src.transport.dispatcher import Dispatcher


def test_ack_correlation_pass():
    Dispatcher._check_ack(
        "MSH|^~\\&|...\rMSA|AA|ABC123|\r",
        target_name="test",
        expected_control_id="ABC123",
    )  # should not raise


def test_ack_correlation_mismatch_raises():
    with pytest.raises(RuntimeError, match="control-id mismatch"):
        Dispatcher._check_ack(
            "MSH|^~\\&|...\rMSA|AA|DIFFERENT|\r",
            target_name="test",
            expected_control_id="ABC123",
        )


def test_ack_ae_raises():
    with pytest.raises(RuntimeError, match="AE"):
        Dispatcher._check_ack(
            "MSH|^~\\&|...\rMSA|AE|ABC123|error\r",
            target_name="test",
            expected_control_id="ABC123",
        )


def test_ack_ar_raises():
    with pytest.raises(RuntimeError, match="AR"):
        Dispatcher._check_ack(
            "MSH|^~\\&|...\rMSA|AR|ABC123|rejected\r",
            target_name="test",
            expected_control_id="ABC123",
        )


def test_ack_accepts_crlf_and_lf_terminators():
    """Some peers emit CRLF or LF instead of CR."""
    Dispatcher._check_ack(
        "MSH|^~\\&|...\r\nMSA|AA|X1|\r\n",
        target_name="test",
        expected_control_id="X1",
    )
    Dispatcher._check_ack(
        "MSH|^~\\&|...\nMSA|AA|X1|\n",
        target_name="test",
        expected_control_id="X1",
    )


# ── Auth: bcrypt ─────────────────────────────────────────────────────────────

def test_bcrypt_password_roundtrip(tmp_path, monkeypatch):
    from src.security import auth as auth_mod
    hash_file = tmp_path / "webui_password.hash"
    monkeypatch.setattr(auth_mod, "_HASH_FILE", hash_file)
    auth_mod.save_password("test-password-1234")
    assert auth_mod.validate_login("test-password-1234")
    assert not auth_mod.validate_login("wrong-password-1234")


def test_password_length_enforced(tmp_path, monkeypatch):
    from src.security import auth as auth_mod
    monkeypatch.setattr(auth_mod, "_HASH_FILE", tmp_path / "h.hash")
    with pytest.raises(ValueError):
        auth_mod.save_password("short")


def test_setup_required_when_no_hash(tmp_path, monkeypatch):
    from src.security import auth as auth_mod
    monkeypatch.setattr(auth_mod, "_HASH_FILE", tmp_path / "nope.hash")
    monkeypatch.setattr(auth_mod, "_LEGACY_PLAIN_FILE", tmp_path / "nope.txt")
    monkeypatch.setattr(auth_mod.os.environ, "get", lambda *_: None)
    assert auth_mod.is_setup_required()


# ── LOINC map ────────────────────────────────────────────────────────────────

def test_loinc_fallback_warns_once(caplog):
    from src.hl7.builder import _LoincMap
    m = _LoincMap()
    with caplog.at_level("WARNING"):
        m.get("UNKNOWNCODE")
        m.get("UNKNOWNCODE")
    warns = [r for r in caplog.records if "UNKNOWNCODE" in r.getMessage()]
    assert len(warns) == 1  # deduped


# ── LOC-200 reference-range parser ───────────────────────────────────────────

from src.adapters.loc200_reader import _parse_ref_range


@pytest.mark.parametrize("raw,expected", [
    ("15-40",   (15.0, 40.0)),
    ("3.1-5.7", (3.1, 5.7)),
    ("<=24",    (None, 24.0)),
    ("<24",     (None, 24.0)),
    ("<=3.37",  (None, 3.37)),
    (">=1.0",   (1.0, None)),
    (">1.0",    (1.0, None)),
    ("",        (None, None)),
    ("gibberish", (None, None)),
])
def test_ref_range_parser(raw, expected):
    assert _parse_ref_range(raw) == expected


def test_loc200_parses_upper_only_reference():
    """Regression: LOC-200 emits CK-MB|8||<=24|U/L for one-sided ranges."""
    from src.adapters.loc200_reader import Loc200Reader
    frame = b"Sample ID: | S1\nCK-MB|8||<=24|U/L\nHCY|7.1||<=15|umol/L\n"
    result = Loc200Reader._parse_frame(frame)
    assert result is not None
    obs = {o["analyte"]: o for o in result["observations"]}
    assert "CK-MB" in obs
    assert obs["CK-MB"]["ref_low"] is None
    assert obs["CK-MB"]["ref_high"] == 24.0
    assert obs["HCY"]["ref_high"] == 15.0
