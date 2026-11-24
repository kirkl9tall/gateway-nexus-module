"""
Common base for device simulators.

A simulator opens a TCP connection to the gateway's listen port for its
device type and sends a scripted message. The E2E test suite then verifies
the gateway parses the message and forwards HL7 to a mock LIS.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("test.simulator")


@dataclass
class SimulatorResult:
    ok:              bool
    bytes_sent:      int
    ack_received:    Optional[bytes] = None
    error:           str = ""


class DeviceSimulator:
    """Base — override play() in subclasses."""

    def __init__(self, host: str = "127.0.0.1", port: int = 5006,
                 timeout: float = 3.0) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout

    async def send_bytes(self, payload: bytes,
                         wait_for_ack: bool = True) -> SimulatorResult:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._timeout,
            )
        except Exception as exc:
            return SimulatorResult(ok=False, bytes_sent=0, error=str(exc))
        try:
            writer.write(payload)
            await writer.drain()
            ack = None
            if wait_for_ack:
                try:
                    ack = await asyncio.wait_for(reader.read(64),
                                                  timeout=self._timeout)
                except asyncio.TimeoutError:
                    pass
            return SimulatorResult(ok=True, bytes_sent=len(payload),
                                    ack_received=ack)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def play(self) -> SimulatorResult:
        raise NotImplementedError
