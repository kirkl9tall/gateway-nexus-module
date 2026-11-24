"""Sysmex XQ-320 simulator — E1381-02 mode (ENQ→ACK→STX...ETX+CHK→ACK→EOT)."""
from __future__ import annotations

import asyncio
from tests.simulators.base import DeviceSimulator, SimulatorResult

ENQ = 0x05
ACK = 0x06
EOT = 0x04
STX = 0x02
ETX = 0x03


def _frame(text: str, seq: int = 1) -> bytes:
    body = bytes([seq + ord("0")]) + text.encode("ascii") + bytes([ETX])
    chk = sum(body) & 0xFF
    trailer = f"{chk:02X}\r\n".encode("ascii")
    return bytes([STX]) + body + trailer


DEFAULT_MESSAGE = [
    "H|\\^&|||XQ-320^00-00^11001^^^^12345678||||||||E1394-97\r",
    "P|1|||100|^Muster^Anna||19850101|F\r",
    "O|1||SN0042||R\r",
    "R|1|^^^^WBC^1|7.4|10*3/uL||N||||||20260828093000\r",
    "R|2|^^^^HGB^1|14.2|g/dL||N||||||20260828093000\r",
    "L|1|N\r",
]


class SysmexXQ320Simulator(DeviceSimulator):
    def __init__(self, host: str = "127.0.0.1", port: int = 5006,
                 records: list[str] | None = None) -> None:
        super().__init__(host=host, port=port)
        self._records = records or DEFAULT_MESSAGE

    async def play(self) -> SimulatorResult:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=3.0,
            )
        except Exception as exc:
            return SimulatorResult(ok=False, bytes_sent=0, error=str(exc))

        bytes_sent = 0
        try:
            # ENQ
            writer.write(bytes([ENQ])); await writer.drain(); bytes_sent += 1
            ack = await asyncio.wait_for(reader.read(1), timeout=3.0)
            if not ack or ack[0] != ACK:
                return SimulatorResult(ok=False, bytes_sent=bytes_sent,
                                        error=f"expected ACK, got {ack!r}")
            # Framed records
            for seq, rec in enumerate(self._records, start=1):
                frame = _frame(rec, seq=seq % 8)
                writer.write(frame); await writer.drain()
                bytes_sent += len(frame)
                ack = await asyncio.wait_for(reader.read(1), timeout=3.0)
                if not ack or ack[0] != ACK:
                    return SimulatorResult(ok=False, bytes_sent=bytes_sent,
                                            error=f"NAK on frame {seq}: {ack!r}")
            # EOT
            writer.write(bytes([EOT])); await writer.drain(); bytes_sent += 1
            return SimulatorResult(ok=True, bytes_sent=bytes_sent, ack_received=b"\x06")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


class SysmexXQ320RawSimulator(DeviceSimulator):
    """E1381-95 mode — plain records, no ENQ/ACK/EOT."""

    async def play(self) -> SimulatorResult:
        payload = "".join(DEFAULT_MESSAGE).encode("ascii")
        return await self.send_bytes(payload, wait_for_ack=False)
