"""Roche Reflotron Plus simulator — semicolon-CSV over serial.

Frame: date;time;patient_id;test_code;value;unit;flag<CR><LF>
Multiple analytes = multiple lines with same (date,time,patient_id).
"""
from __future__ import annotations

from tests.simulators.base import DeviceSimulator, SimulatorResult

DEFAULT_REFLOTRON_LINES = [
    "28.08.2026;09:30:00;PAT-42;GLU;5.6;mmol/L;N",
    "28.08.2026;09:30:00;PAT-42;CHOL;4.9;mmol/L;N",
    "28.08.2026;09:30:00;PAT-42;GGT;42;U/L;N",
    "28.08.2026;09:30:00;PAT-42;AST;28;U/L;N",
    "28.08.2026;09:30:00;PAT-42;ALT;32;U/L;N",
]


class ReflotronSimulator(DeviceSimulator):
    def __init__(self, host: str = "127.0.0.1", port: int = 5005,
                 lines: list[str] | None = None) -> None:
        super().__init__(host=host, port=port)
        self._lines = lines or DEFAULT_REFLOTRON_LINES

    async def play(self) -> SimulatorResult:
        payload = "\r\n".join(self._lines).encode("ascii") + b"\r\n"
        return await self.send_bytes(payload, wait_for_ack=False)
