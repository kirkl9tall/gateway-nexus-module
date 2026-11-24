"""Menarini UC-1000 urinalysis simulator.

Sends the 157-field comma-separated frame the UC1000Reader adapter expects.
"""
from __future__ import annotations

import asyncio

from tests.simulators.base import DeviceSimulator, SimulatorResult

STX = 0x02
ETX = 0x03
ACK = 0x06
EOT = 0x04


def _build_uc1000_frame(patient_id: str = "PAT-42",
                        strip_no: int = 1) -> bytes:
    """Build a UC-1000 STX...ETX+CSH+CSL frame with 157 fields."""
    fields: list[str] = [""] * 157
    fields[0] = f"{patient_id:14s}"        # Barcode ID
    fields[7] = f"{strip_no:04d}"          # Analysis number
    fields[9] = ""                          # Error codes (empty = ok)
    fields[11] = "URIT-11G"                 # Strip name
    fields[13] = "2026/08/28"               # Date
    fields[15] = "09:30:00"                 # Time
    # Analyte groups from index 17 onward (30 bytes each): URO, BLD, BIL,
    # KET, GLU, PRO, pH, NIT, LEU, S.G, CRE, ALB, P/C, A/C, S.G(ref), Color
    demo_values = ["norm", "neg", "neg", "neg", "5.5",
                    "trace", "6.0", "neg", "neg", "1.020"]
    for i, val in enumerate(demo_values):
        fields[17 + i] = val

    data = ",".join(fields).encode("ascii")
    body = bytes([STX]) + data + bytes([ETX])
    chk = sum(body[1:]) & 0xFF
    return body + bytes([(chk >> 4) & 0xF | 0x30, chk & 0xF | 0x30])


class UC1000Simulator(DeviceSimulator):
    def __init__(self, host: str = "127.0.0.1", port: int = 5040) -> None:
        super().__init__(host=host, port=port)

    async def play(self) -> SimulatorResult:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=3.0,
            )
        except Exception as exc:
            return SimulatorResult(ok=False, bytes_sent=0, error=str(exc))
        frame = _build_uc1000_frame()
        bytes_sent = 0
        try:
            writer.write(frame); await writer.drain()
            bytes_sent += len(frame)
            # UC-1000 waits for ACK from host
            try:
                ack = await asyncio.wait_for(reader.read(1), timeout=2.0)
                if ack and ack[0] == ACK:
                    writer.write(bytes([EOT])); await writer.drain()
                    bytes_sent += 1
                    return SimulatorResult(ok=True, bytes_sent=bytes_sent, ack_received=ack)
            except asyncio.TimeoutError:
                pass
            return SimulatorResult(ok=True, bytes_sent=bytes_sent)
        finally:
            try:
                writer.close(); await writer.wait_closed()
            except Exception:
                pass
