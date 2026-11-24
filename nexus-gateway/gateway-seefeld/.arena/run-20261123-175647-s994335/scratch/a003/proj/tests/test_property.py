"""
Property-based tests: fuzz the HL7 builder with arbitrary strings and
assert invariants no matter what the input looks like.
"""
from __future__ import annotations

from datetime import datetime

import pytest

hypothesis = pytest.importorskip("hypothesis")

from hypothesis import given, settings, strategies as st

from config.settings import HL7Config
from src.hl7.builder import HL7Builder, _esc


# Any printable + control chars, incl. HL7 separators
_TEXT = st.text(
    alphabet=st.characters(min_codepoint=0, max_codepoint=0xFFFF,
                           blacklist_categories=("Cs",)),  # skip surrogates
    max_size=200,
)


@given(_TEXT)
def test_esc_never_introduces_bare_separator(raw):
    """After escaping, no raw |, ^, ~, & or CR/LF/FS may remain."""
    out = _esc(raw)
    for forbidden in ("|", "^", "~", "&", "\r", "\n", "\x1C", "\x0B"):
        assert forbidden not in out, (
            f"Escaped output still contains {forbidden!r}: {out!r}"
        )


@given(_TEXT, _TEXT)
def test_single_msh_regardless_of_hostile_input(patient_name, disc_name):
    """
    Whatever the operator (or attacker) puts in patient name or disc name,
    the generated HL7 message must contain exactly one MSH segment.
    """
    cfg = HL7Config(sending_facility="X")
    builder = HL7Builder(cfg)
    result = {
        "timestamp":    datetime(2025, 1, 1, 12, 0, 0),
        "sample_id":    "S",
        "patient_id":   "P",
        "patient_name": patient_name,
        "gender":       "M",
        "disc_name":    disc_name,
        "lot_id":       "L",
        "observations": [{
            "analyte": "AST", "value": "10", "value_num": 10.0, "flag": "",
            "ref_low": 5, "ref_high": 30, "unit": "U/L",
        }],
    }
    msg = builder.build_oru_r01(result)
    text = msg.to_string()
    assert text.count("MSH|") == 1


@settings(max_examples=200)
@given(st.integers(min_value=0, max_value=50))
def test_obx_count_matches_observations(n):
    """The number of OBX segments must equal the number of observations."""
    cfg = HL7Config(sending_facility="X")
    builder = HL7Builder(cfg)
    obs = [{
        "analyte": f"CODE{i}", "value": str(i), "value_num": float(i),
        "flag": "", "ref_low": None, "ref_high": None, "unit": "U/L",
    } for i in range(n)]
    result = {
        "timestamp":    datetime(2025, 1, 1, 12, 0, 0),
        "sample_id":    "S", "patient_id": "P", "patient_name": "X",
        "gender":       "M", "disc_name": "D", "lot_id": "L",
        "observations": obs,
    }
    msg = builder.build_oru_r01(result)
    assert msg.to_string().count("\rOBX|") == n


@given(_TEXT)
def test_mllp_frame_starts_with_vt_ends_with_fs_cr(patient_name):
    """MLLP framing bytes must be present regardless of payload contents."""
    cfg = HL7Config(sending_facility="X")
    builder = HL7Builder(cfg)
    result = {
        "timestamp":    datetime(2025, 1, 1, 12, 0, 0),
        "sample_id":    "S", "patient_id": "P",
        "patient_name": patient_name,
        "gender":       "M", "disc_name": "D", "lot_id": "L",
        "observations": [{
            "analyte": "AST", "value": "10", "value_num": 10.0, "flag": "",
            "ref_low": 5, "ref_high": 30, "unit": "U/L",
        }],
    }
    frame = builder.build_oru_r01(result).to_mllp()
    assert frame[0:1] == b"\x0B"
    assert frame[-2:] == b"\x1C\x0D"
    # No stray VT / FS in the body (they would break framing)
    body = frame[1:-2]
    assert b"\x0B" not in body
    assert b"\x1C" not in body
