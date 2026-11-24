"""Cobas b101 POCT1-A2 simulator.

Sends the DEV.R01 observation XML that the cobas_reader adapter expects.
"""
from __future__ import annotations

from tests.simulators.base import DeviceSimulator, SimulatorResult

DEFAULT_COBAS_B101_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OBS.R01>
  <HDR>
    <SessionID>SES-00042</SessionID>
    <ManufacturerName>Roche</ManufacturerName>
    <ManufacturerModel>Cobas b 101</ManufacturerModel>
    <PID>PAT-42</PID>
    <SID>SN0042</SID>
    <DTM>20260828093000</DTM>
    <OperatorID>OP01</OperatorID>
  </HDR>
  <RESULTS>
    <RESULT>
      <CODE>HBA1C</CODE>
      <VAL>5.7</VAL>
      <UNIT>%</UNIT>
      <FLAG>N</FLAG>
    </RESULT>
    <RESULT>
      <CODE>CHOL</CODE>
      <VAL>4.9</VAL>
      <UNIT>mmol/L</UNIT>
      <FLAG>N</FLAG>
    </RESULT>
    <RESULT>
      <CODE>HDL</CODE>
      <VAL>1.3</VAL>
      <UNIT>mmol/L</UNIT>
      <FLAG>N</FLAG>
    </RESULT>
  </RESULTS>
</OBS.R01>
"""


class CobasB101Simulator(DeviceSimulator):
    def __init__(self, host: str = "127.0.0.1", port: int = 5030,
                 xml: str = DEFAULT_COBAS_B101_XML) -> None:
        super().__init__(host=host, port=port)
        self._xml = xml

    async def play(self) -> SimulatorResult:
        return await self.send_bytes(self._xml.encode("utf-8"), wait_for_ack=False)
