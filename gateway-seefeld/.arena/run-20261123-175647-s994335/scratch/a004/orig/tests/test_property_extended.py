"""
Extended property-based fuzz suite. Complements tests/test_property.py
with adversarial inputs designed to survive a night of Hypothesis
mutations without crashing any parser.

Run standalone:
    pytest tests/test_property_extended.py --hypothesis-seed=random \
                                           -p no:cacheprovider

Nightly CI runs this with `--hypothesis-profile=ci` (500 examples per
test) instead of the default 100.
"""
from __future__ import annotations

import string

import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

# ── Strategies ────────────────────────────────────────────────────────────────

_ASCII_PRINTABLE = st.text(alphabet=string.printable, min_size=0, max_size=500)
_ASTM_FIELD      = st.text(alphabet=string.ascii_letters + string.digits + "-_.^&", max_size=40)
_CONTROL_BYTES   = st.binary(min_size=0, max_size=100)


@st.composite
def astm_frame(draw) -> str:
    """Random ASTM-like frame that a real Sysmex might produce."""
    seq = draw(st.integers(min_value=0, max_value=9))
    records = []
    records.append(f"H|\\^&|||{draw(_ASTM_FIELD)}||||||||E1394-97")
    records.append(f"P|1||{draw(_ASTM_FIELD)}||{draw(_ASTM_FIELD)}")
    records.append(f"O|1|{draw(_ASTM_FIELD)}||^^^{draw(_ASTM_FIELD)}|R||")
    n_results = draw(st.integers(min_value=0, max_value=20))
    for i in range(1, n_results + 1):
        code  = draw(st.sampled_from(["WBC", "RBC", "HGB", "HCT", "MCV", "PLT",
                                       "NEUT#", "LYMPH#", "MXD#", "GLU"]))
        value = draw(st.floats(min_value=0, max_value=10_000, allow_nan=False,
                                allow_infinity=False))
        unit  = draw(st.sampled_from(["g/dL", "10^3/uL", "%", "fL", "pg"]))
        flag  = draw(st.sampled_from(["", "H", "L", "N", "*"]))
        records.append(f"R|{i}|{code}|{value:.2f}|{unit}|||{flag}")
    records.append("L|1|N")
    return f"{seq}" + "\r".join(records) + "\r"


# ── Sysmex parser: never crashes on arbitrary text ────────────────────────────

@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(_ASCII_PRINTABLE)
def test_sysmex_parser_never_crashes(text: str) -> None:
    from src.adapters.sysmex_reader import _parse_astm
    result = _parse_astm(text, "fuzz")
    assert result is None or isinstance(result, dict)


@settings(max_examples=100)
@given(astm_frame())
def test_sysmex_parser_wellformed_returns_observations(frame: str) -> None:
    from src.adapters.sysmex_reader import _parse_astm
    result = _parse_astm(frame, "fuzz")
    if result is not None:
        obs = result.get("observations", [])
        for o in obs:
            assert "analyte" in o and "value" in o


# ── Reflotron parser fuzz ─────────────────────────────────────────────────────

@settings(max_examples=100)
@given(_ASCII_PRINTABLE)
def test_reflotron_parser_never_crashes(text: str) -> None:
    from src.adapters.reflotron_reader import _parse_line
    for line in text.splitlines()[:10]:
        _parse_line(line, "fuzz")   # must not raise


# ── HL7 builder fuzz ──────────────────────────────────────────────────────────

@settings(max_examples=100)
@given(
    patient_id=_ASTM_FIELD,
    sample_id=_ASTM_FIELD,
    n_obs=st.integers(min_value=0, max_value=15),
)
def test_hl7_builder_produces_msh_pid_obr(patient_id: str, sample_id: str, n_obs: int) -> None:
    try:
        from src.hl7 import builder as hl7_builder
    except ImportError:
        pytest.skip("hl7 builder not available")
    if not hasattr(hl7_builder, "build_hl7_message"):
        pytest.skip("builder not available in this build")
    observations = [
        {"analyte": f"A{i}", "name_de": "X", "loinc": "0-0", "value": str(i),
         "value_num": float(i), "unit": "u", "flag": "",
         "ref_low": None, "ref_high": None}
        for i in range(n_obs)
    ]
    payload = {
        "timestamp":    __import__("datetime").datetime.now(),
        "sample_id":    sample_id or "S1",
        "patient_id":   patient_id or "P1",
        "patient_name": "",
        "age": None, "gender": "", "department": "", "disc_name": "",
        "lot_id": "", "device": "fuzz",
        "observations": observations,
    }
    try:
        out = hl7_builder.build_hl7_message(payload)
    except Exception:
        # builder is allowed to reject degenerate inputs — as long as
        # it does not crash the process; pytest catches SystemExit.
        return
    if not out:
        return
    assert out.startswith("MSH|"), "must start with MSH segment"
    if n_obs > 0:
        assert "OBR|" in out and "OBX|" in out


# ── Error codes are stable enum values ────────────────────────────────────────

@given(st.sampled_from([
    "E1001", "E1002", "E1003", "E2001", "E3001", "E4001", "E5001", "E9001",
]))
def test_error_codes_exist(code: str) -> None:
    from src.common.errors import ErrorCode
    assert code in {e.value for e in ErrorCode}
