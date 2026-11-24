"""LOCMEDT LOC-200 dry chemistry simulator.

Custom serial framing: newline-terminated ASCII with key=value pairs.
"""
from __future__ import annotations

from tests.simulators.base import DeviceSimulator, SimulatorResult

DEFAULT_LOC200_FRAME = (
    "Sample ID:PAT-42\r\n"
    "Disc Name:12-Panel Metabolic\r\n"
    "Kit:LOC-M12\r\n"
    "Lot:24A051\r\n"
    "Date:2026-08-28 09:30:00\r\n"
    "GLU=5.6 mmol/L N\r\n"
    "UREA=5.2 mmol/L N\r\n"
    "CREA=78 umol/L N\r\n"
    "ALT=32 U/L N\r\n"
    "AST=28 U/L N\r\n"
    "END\r\n"
)


class LOC200Simulator(DeviceSimulator):
    def __init__(self, host: str = "127.0.0.1", port: int = 5003,
                 frame: str = DEFAULT_LOC200_FRAME) -> None:
        super().__init__(host=host, port=port)
        self._frame = frame

    async def play(self) -> SimulatorResult:
        return await self.send_bytes(self._frame.encode("utf-8"),
                                       wait_for_ack=False)
