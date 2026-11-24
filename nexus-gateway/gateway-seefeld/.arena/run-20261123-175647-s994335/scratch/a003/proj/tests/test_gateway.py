"""
tests/test_gateway.py
Unit tests for JerumedNexus Gateway components.

Run:  pytest tests/ -v
"""

import pytest
from datetime import datetime

# ── Parser tests ──────────────────────────────────────────────────────────────

from src.adapters.loc200_reader import Loc200Reader

SAMPLE_FRAME = b"""\
Biochemical Analyzer Test Report
Myocardial Enzyme and Lipid Lyophilized Kit 10
Sample ID: | 23
Patient ID: | 23
Department: | id1
Name: 23
Gender: Male
Age: 20 Year 1 Mon
Lot ID: 220501-53-305
AST|13|DOWN|15-40|U/L
CHOL|4.71||3.1-5.7|mmol/L
CK|35||10-200|U/L
CK-MB|8||<=24|U/L
HCY|7.1||<=15|umol/L
HDL-C|2.08|UP|1.16-1.42|mmol/L
LDH|165||120-250|U/L
TG|1.3||<=2.1|mmol/L
A-HBDH|116||90-230|U/L
LDL-C|2.04||<=3.37|mmol/L
"""


def test_parse_frame_returns_dict():
    result = Loc200Reader._parse_frame(SAMPLE_FRAME)
    assert result is not None
    assert result["sample_id"] != "" or result["patient_id"] != ""


def test_parse_frame_observations_count():
    result = Loc200Reader._parse_frame(SAMPLE_FRAME)
    assert result is not None
    obs = result["observations"]
    assert len(obs) >= 8, f"Expected ≥8 observations, got {len(obs)}"


def test_parse_frame_analyte_values():
    result = Loc200Reader._parse_frame(SAMPLE_FRAME)
    obs_map = {o["analyte"]: o for o in result["observations"]}

    assert "AST" in obs_map
    assert obs_map["AST"]["value_num"] == pytest.approx(13.0)
    assert obs_map["AST"]["flag"] == "L"   # ↓ → "L"

    assert "HDL-C" in obs_map
    assert obs_map["HDL-C"]["flag"] == "H"  # ↑ → "H"

    assert "CHOL" in obs_map
    assert obs_map["CHOL"]["value_num"] == pytest.approx(4.71)
    assert obs_map["CHOL"]["ref_low"] == pytest.approx(3.1)
    assert obs_map["CHOL"]["ref_high"] == pytest.approx(5.7)


def test_parse_frame_empty_returns_none():
    result = Loc200Reader._parse_frame(b"no observations here at all")
    assert result is None


# ── HL7 builder tests ─────────────────────────────────────────────────────────

from src.hl7.builder import HL7Builder, HL7Message
from config.settings import HL7Config


@pytest.fixture
def hl7_config():
    return HL7Config(
        sending_application="TEST_GW",
        sending_facility="TESTPRAXIS",
        receiving_application="TEST_LIS",
        receiving_facility="TESTPRAXIS",
    )


@pytest.fixture
def sample_result():
    return {
        "timestamp":    datetime(2024, 6, 1, 10, 30, 0),
        "sample_id":    "S001",
        "patient_id":   "P123",
        "patient_name": "Müller Hans",
        "age":          45,
        "gender":       "M",
        "department":   "Internal",
        "disc_name":    "General Chemistry I Kit 18",
        "lot_id":       "LOT-2024-001",
        "observations": [
            {"analyte": "AST",  "value": "13",   "value_num": 13.0,  "flag": "L",
             "ref_low": 15.0, "ref_high": 40.0, "unit": "U/L"},
            {"analyte": "CHOL", "value": "4.71", "value_num": 4.71,  "flag": "",
             "ref_low": 3.1,  "ref_high": 5.7,  "unit": "mmol/L"},
            {"analyte": "GLU",  "value": "---",  "value_num": None,  "flag": "",
             "ref_low": None, "ref_high": None,  "unit": "mmol/L"},
        ],
    }


def test_build_oru_r01_returns_hl7_message(hl7_config, sample_result):
    builder = HL7Builder(hl7_config)
    msg = builder.build_oru_r01(sample_result)
    assert isinstance(msg, HL7Message)


def test_hl7_message_contains_msh(hl7_config, sample_result):
    builder = HL7Builder(hl7_config)
    msg = builder.build_oru_r01(sample_result)
    text = msg.to_string()
    assert text.startswith("MSH|")


def test_hl7_message_contains_pid(hl7_config, sample_result):
    builder = HL7Builder(hl7_config)
    msg = builder.build_oru_r01(sample_result)
    text = msg.to_string()
    assert "\rPID|" in text
    assert "P123" in text


def test_hl7_message_contains_obx_for_each_analyte(hl7_config, sample_result):
    builder = HL7Builder(hl7_config)
    msg = builder.build_oru_r01(sample_result)
    text = msg.to_string()
    obx_count = text.count("\rOBX|")
    assert obx_count == 3


def test_hl7_mllp_framing(hl7_config, sample_result):
    builder = HL7Builder(hl7_config)
    msg = builder.build_oru_r01(sample_result)
    mllp = msg.to_mllp()
    assert mllp[0:1] == b"\x0B"    # VT
    assert mllp[-2:-1] == b"\x1C"  # FS
    assert mllp[-1:] == b"\x0D"    # CR


def test_hl7_abnormal_flag_h(hl7_config, sample_result):
    builder = HL7Builder(hl7_config)
    msg = builder.build_oru_r01(sample_result)
    text = msg.to_string()
    # AST has flag "L" → should appear in OBX-8
    assert "|L|" in text


def test_hl7_non_numeric_value_uses_st_type(hl7_config, sample_result):
    builder = HL7Builder(hl7_config)
    msg = builder.build_oru_r01(sample_result)
    text = msg.to_string()
    # GLU has value "---" → value type should be ST
    assert "|ST|" in text


# ── Dispatcher tests ──────────────────────────────────────────────────────────

from src.transport.dispatcher import Dispatcher
from config.settings import GatewayConfig, PISTarget
import tempfile


def make_config_with_target(target: PISTarget) -> GatewayConfig:
    return GatewayConfig(targets=[target])


@pytest.mark.asyncio
async def test_file_drop_creates_file(hl7_config, sample_result):
    with tempfile.TemporaryDirectory() as tmpdir:
        target = PISTarget(
            name="test_file",
            type="winmed",
            enabled=True,
            watch_folder=tmpdir,
            file_extension=".hl7",
        )
        config = make_config_with_target(target)
        dispatcher = Dispatcher(config)

        builder = HL7Builder(hl7_config)
        msg = builder.build_oru_r01(sample_result)

        await dispatcher.dispatch(msg, sample_result)

        files = list(Path(tmpdir).glob("*.hl7"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "MSH|" in content
        assert "OBX|" in content


from pathlib import Path
