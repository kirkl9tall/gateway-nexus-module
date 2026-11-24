"""POCT1-A2 XML simulator — Cobas b101, Afinion 2, DCA Vantage, etc."""
from __future__ import annotations

from tests.simulators.base import DeviceSimulator, SimulatorResult

DEFAULT_POCT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OBS.R01>
  <HDR><PID>PAT-42</PID><SID>SN0042</SID><DTM>20260828093000</DTM></HDR>
  <RESULTS>
    <RESULT><CODE>HBA1C</CODE><VAL>5.7</VAL><UNIT>%</UNIT><FLAG>N</FLAG></RESULT>
  </RESULTS>
</OBS.R01>
"""


class POCTSimulator(DeviceSimulator):
    def __init__(self, host: str = "127.0.0.1", port: int = 5030,
                 xml: str = DEFAULT_POCT_XML) -> None:
        super().__init__(host=host, port=port)
        self._xml = xml

    async def play(self) -> SimulatorResult:
        return await self.send_bytes(self._xml.encode("utf-8"), wait_for_ack=False)
