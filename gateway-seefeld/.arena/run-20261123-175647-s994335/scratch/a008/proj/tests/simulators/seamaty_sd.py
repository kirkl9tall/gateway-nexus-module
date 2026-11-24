"""Seamaty SD1 / SD3 dry-chemistry simulator — HL7 v2 ORU over serial/TCP.

Verified frame layout from Seamaty LIS Connection Manual:
  MSH → MSA (ACK) → PID → OBR → OBX × N
"""
from __future__ import annotations

from tests.simulators.mllp import MLLPSimulator

SEAMATY_SD3_ORU = (
    "MSH|^~\\&|Seamaty SD3|LAB|LIS|CLINIC|20260828093000||ORU^R01|MSG00042|P|2.5\r"
    "PID|1||PAT-42||Muster^Anna||19850101|F\r"
    "OBR|1|SN0042|SN0042|CHEM^Clinical Chemistry^LN|||20260828093000\r"
    "OBX|1|NM|GLU^Glucose^LN||5.6|mmol/L|3.9-6.1|N|||F\r"
    "OBX|2|NM|CHOL^Cholesterol^LN||4.8|mmol/L|<5.2|N|||F\r"
    "OBX|3|NM|CREA^Creatinine^LN||78|umol/L|60-110|N|||F\r"
)


class SeamatySD3Simulator(MLLPSimulator):
    def __init__(self, host: str = "127.0.0.1", port: int = 6000) -> None:
        super().__init__(host=host, port=port, hl7_body=SEAMATY_SD3_ORU)


class SeamatySD1Simulator(MLLPSimulator):
    def __init__(self, host: str = "127.0.0.1", port: int = 6002) -> None:
        # SD1 sends fewer analytes but same format
        body = SEAMATY_SD3_ORU.replace("SD3", "SD1")
        super().__init__(host=host, port=port, hl7_body=body)
