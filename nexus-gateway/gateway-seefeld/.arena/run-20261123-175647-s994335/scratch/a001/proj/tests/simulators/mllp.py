"""Generic HL7 v2 MLLP-over-TCP simulator (used by Cobas c111, Mindray,
Seamaty, PixCell, Bio-Rad D-100, etc. — everything that uses mllp_hl7)."""
from __future__ import annotations

from tests.simulators.base import DeviceSimulator, SimulatorResult

VT = 0x0B
FS = 0x1C
CR = 0x0D

DEFAULT_ORU = (
    "MSH|^~\\&|SIMULATED|SIM|LIS|CLINIC|20260828093000||ORU^R01|MSG00001|P|2.5\r"
    "PID|1||PAT-42||Muster^Anna||19850101|F\r"
    "OBR|1|SN0042|SN0042|CBC^Complete Blood Count^LN|||20260828093000\r"
    "OBX|1|NM|WBC^Leukocytes^LN||7.4|10*3/uL|4.0-10.0|N|||F\r"
    "OBX|2|NM|HGB^Hemoglobin^LN||14.2|g/dL|12.0-16.0|N|||F\r"
)


class MLLPSimulator(DeviceSimulator):
    def __init__(self, host: str = "127.0.0.1", port: int = 6000,
                 hl7_body: str = DEFAULT_ORU) -> None:
        super().__init__(host=host, port=port)
        self._hl7 = hl7_body

    async def play(self) -> SimulatorResult:
        wrapped = bytes([VT]) + self._hl7.encode("utf-8") + bytes([FS, CR])
        return await self.send_bytes(wrapped, wait_for_ack=True)
