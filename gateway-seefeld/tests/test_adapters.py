"""
Adapter-level parser tests: real sample frames + fuzz.

We test the pure parser functions (no I/O) with representative frames from
each analyzer, plus a Hypothesis fuzz that throws random bytes at each
parser and asserts it never crashes -- worst case it returns None.
"""
from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings, strategies as st

_random_bytes = st.binary(min_size=0, max_size=4096)


# ── Sysmex ASTM ──────────────────────────────────────────────────────────────

_SYSMEX_ASTM_FRAME = (
    "1H|\\^&|||^Sysmex XP-300|||||||P|E1394-97|20250101120000\r"
    "P|1|||PAT001||^Mueller^Hans|||M\r"
    "O|1|SAMPLE001||^^^CBC|R||20250101120000\r"
    "R|1|^^^WBC|7.2|10^3/uL|4.0-10.0||F\r"
    "R|2|^^^HGB|14.5|g/dL|12.0-16.0||F\r"
    "R|3|^^^HCT|43.2|%|36.0-46.0||F\r"
    "R|4|^^^PLT|250|10^3/uL|150-400||F\r"
    "L|1|N\r"
)


def test_sysmex_astm_parses_full_frame():
    from src.adapters.sysmex_reader import _parse_astm
    result = _parse_astm(_SYSMEX_ASTM_FRAME, "TEST_SYSMEX")
    assert result is not None
    assert result["sample_id"] == "SAMPLE001"
    assert result["device"] == "TEST_SYSMEX"
    obs = {o["analyte"]: o for o in result["observations"]}
    assert "WBC" in obs
    assert obs["WBC"]["value_num"] == pytest.approx(7.2)
    assert obs["WBC"]["ref_low"] == pytest.approx(4.0)
    assert obs["WBC"]["ref_high"] == pytest.approx(10.0)
    assert "HGB" in obs and obs["HGB"]["unit"] == "g/dL"


def test_sysmex_astm_strips_id_suffix_when_asked():
    from src.adapters.sysmex_reader import _strip_suffix
    assert _strip_suffix("SAMPLE001A") == "SAMPLE001"
    assert _strip_suffix("SAMPLE001") == "SAMPLE001"


def test_sysmex_normalize_code_variants():
    from src.adapters.sysmex_reader import _normalize_code
    assert _normalize_code("LYM#") == "LYMPH#"
    assert _normalize_code("LYM%") == "LYMPH%"
    assert _normalize_code("NEUTPCT") == "NEUT%"


def test_sysmex_hct_scale_normalization():
    """When HCT < 1.0 the device sent a fraction — multiply by 100."""
    from src.adapters.sysmex_reader import _normalize_value
    # _normalize_value now returns (value, transforms_list) so the conversion
    # audit can record every silent change. Only the value must match here.
    assert _normalize_value("HCT", "0.43")[0] == "43.0"
    assert _normalize_value("HCT", "43.2")[0] == "43.2"


@settings(max_examples=200, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(_random_bytes)
def test_sysmex_fuzz_never_crashes(raw):
    from src.adapters.sysmex_reader import _parse_astm
    try:
        text = raw.decode("ascii", errors="ignore")
    except Exception:
        text = ""
    # Must not raise -- may return None
    _parse_astm(text, "FUZZ")


# ── Cobas POCT1-A2 ───────────────────────────────────────────────────────────

_COBAS_OBS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OBS.R01>
  <HDR><HDR.control_id V="42"/><HDR.version_id V="POCT1"/></HDR>
  <PAT><PAT.patient_id V="PAT-42"/><PAT.patient_name V="Meier^Anna"/></PAT>
  <OBS><OBS.test_cd V="HBA1C"/><OBS.value V="5.8"/><OBS.units_cd V="%"/></OBS>
  <OBS><OBS.test_cd V="CRP"/><OBS.value V="3.2"/><OBS.units_cd V="mg/L"/></OBS>
</OBS.R01>"""


def test_cobas_xml_parses():
    from src.adapters.cobas_reader import _parse_obs_xml
    result = _parse_obs_xml(_COBAS_OBS_XML, "COBAS TEST")
    assert result is not None
    assert result["patient_id"] == "PAT-42"
    obs = {o["analyte"]: o for o in result["observations"]}
    assert "HBA1C" in obs
    assert obs["HBA1C"]["value_num"] == pytest.approx(5.8)
    assert obs["HBA1C"]["unit"] == "%"
    assert obs["HBA1C"]["loinc"] == "4548-4"
    assert "CRP" in obs


def test_cobas_xml_missing_value_skipped():
    from src.adapters.cobas_reader import _parse_obs_xml
    xml = ("""<?xml version="1.0" encoding="UTF-8"?>
<OBS.R01>
  <HDR><HDR.control_id V="1"/></HDR>
  <PAT><PAT.patient_id V="P1"/></PAT>
  <OBS><OBS.test_cd V="HBA1C"/></OBS>
</OBS.R01>""")
    assert _parse_obs_xml(xml, "TEST") is None


@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(_random_bytes)
def test_cobas_fuzz_never_crashes(raw):
    from src.adapters.cobas_reader import _parse_obs_xml
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    _parse_obs_xml(text, "FUZZ")


# ── UC-1000 CSV ──────────────────────────────────────────────────────────────

def _uc1000_frame() -> bytes:
    """Build a minimal-but-valid UC-1000 CSV frame."""
    fields = [
        "BC000001      ",   # 0: barcode
        "R1",               # 1: rack
        "01",               # 2: tube
        "N00000001",        # 3: analysis id
        "0000",             # 4: error
        "10PC10        ",   # 5: strip name
        "2025/01/01",       # 6: date
        "12:00:00",         # 7: time
        # 8+ analyte groups (state 2, mark space, qual+conc)
        "2 NEG   30    ", "2 POS   +     ", "2 NEG         ",
        "2 NEG         ", "2 NEG         ", "2 NEG         ",
        "2 6.0         ", "2 NEG         ", "2 NEG         ",
        "2 1.015       ", "2 88          ", "2 15          ",
        "2 40          ", "2 15          ", "2 1.015       ",
    ]
    return ",".join(fields).encode("ascii")


def test_uc1000_csv_parses():
    from src.adapters.uc1000_reader import UC1000Reader
    import asyncio
    reader = UC1000Reader(port="", baudrate=9600,
                          queue=asyncio.Queue(), device_name="UC-TEST")
    result = reader._parse_frame(_uc1000_frame())
    assert result is not None
    assert result["sample_id"] == "BC000001"
    codes = {o["analyte"] for o in result["observations"]}
    # At least the ones we filled with "state=2" should show up
    assert "URO" in codes or "GLU" in codes


@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(_random_bytes)
def test_uc1000_fuzz_never_crashes(raw):
    from src.adapters.uc1000_reader import UC1000Reader
    import asyncio
    reader = UC1000Reader(port="", baudrate=9600,
                          queue=asyncio.Queue(), device_name="FUZZ")
    reader._parse_frame(raw)


# ── MLLP HL7 ─────────────────────────────────────────────────────────────────

_MLLP_HL7 = (
    "MSH|^~\\&|SMT120|LAB|LIS|PRAXIS|20250101120000||ORU^R01|MSG001|P|2.5\r"
    "PID||PAT-99||PAT-99||Weber^Klaus||||M\r"
    "OBR|1||SAMPLE-99|panel|||20250101120000\r"
    "OBX|1|NM|GLU^Glukose^L|1|5.4|mmol/L|3.9-6.1|N|||F\r"
    "OBX|2|NM|CHOL^Cholesterin^L|1|6.2|mmol/L|0-5.17|H|||F\r"
)


def test_mllp_reader_parses_hl7():
    from src.adapters.mllp_reader import MLLPReader
    import asyncio
    reader = MLLPReader(host="127.0.0.1", port=0,
                        queue=asyncio.Queue(), device_name="Seamaty",
                        device_type="seamaty_smt120")
    result = reader._parse_hl7(_MLLP_HL7)
    assert result is not None
    assert result["patient_id"] == "PAT-99"
    obs = {o["analyte"]: o for o in result["observations"]}
    assert obs["CHOL"]["flag"] == "H"
    assert obs["GLU"]["value_num"] == pytest.approx(5.4)


@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(_random_bytes)
def test_mllp_fuzz_never_crashes(raw):
    from src.adapters.mllp_reader import MLLPReader
    import asyncio
    reader = MLLPReader(host="127.0.0.1", port=0,
                        queue=asyncio.Queue(), device_name="FUZZ",
                        device_type="seamaty")
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    reader._parse_hl7(text)


# ── LOC-200 native ───────────────────────────────────────────────────────────

@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(_random_bytes)
def test_loc200_fuzz_never_crashes(raw):
    from src.adapters.loc200_reader import Loc200Reader
    Loc200Reader._parse_frame(raw)
