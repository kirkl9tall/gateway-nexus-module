"""
Mock LIS receiver — accepts HL7 v2 MLLP, decodes and stores messages,
responds with MSA|AA. Used by E2E tests to verify what the gateway sent.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

VT = 0x0B
FS = 0x1C
CR = 0x0D


@dataclass
class MockLIS:
    host:     str = "127.0.0.1"
    port:     int = 12575
    received: list[str] = field(default_factory=list)
    _server:  asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle, self.host, self.port,
        )

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader,
                       writer: asyncio.StreamWriter) -> None:
        buf = bytearray()
        try:
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=5.0)
                if not chunk:
                    break
                buf.extend(chunk)
                if FS in buf:
                    end = buf.index(FS)
                    payload = bytes(buf[:end])
                    if payload and payload[0] == VT:
                        payload = payload[1:]
                    msg = payload.decode("utf-8", errors="replace")
                    self.received.append(msg)
                    # Build ACK
                    control_id = self._extract_control_id(msg)
                    ack = self._build_ack(control_id)
                    wrapped = bytes([VT]) + ack.encode("utf-8") + bytes([FS, CR])
                    writer.write(wrapped)
                    await writer.drain()
                    del buf[:end + 2]  # +2 to skip FS + CR
        except (asyncio.TimeoutError, ConnectionResetError):
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    def _extract_control_id(self, hl7: str) -> str:
        try:
            msh = hl7.split("\r")[0]
            fields = msh.split("|")
            return fields[9] if len(fields) > 9 else "?"
        except Exception:
            return "?"

    def _build_ack(self, control_id: str) -> str:
        return (
            f"MSH|^~\\&|MOCK_LIS|LIS|SIMULATED|SIM|20260828093000||ACK|"
            f"ACK{control_id}|P|2.5\r"
            f"MSA|AA|{control_id}\r"
        )
