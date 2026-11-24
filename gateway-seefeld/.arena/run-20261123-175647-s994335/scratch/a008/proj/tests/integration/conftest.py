"""
Integration test fixtures: fake analyzer + fake MLLP receiver.

These are lightweight asyncio servers that accept a real socket connection,
speak just enough of the protocol to unblock the gateway, and record what
they saw so tests can assert on it.
"""
from __future__ import annotations

import asyncio
import re
from typing import List

import pytest


@pytest.fixture(autouse=True)
def _reset_breaker_state(tmp_path, monkeypatch):
    """Ensure each integration test starts with clean circuit-breaker state."""
    monkeypatch.setattr("src.transport.circuit_breaker._STATE_FILE",
                        tmp_path / "breakers.json")
    yield


class FakeMLLPServer:
    """Accepts an MLLP-framed message and replies with an ACK (AA or configurable)."""

    def __init__(self, ack_code: str = "AA") -> None:
        self.ack_code = ack_code
        self.received: List[bytes] = []
        self._server: asyncio.AbstractServer | None = None
        self.port: int = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        buf = bytearray()
        in_msg = False
        try:
            while True:
                data = await asyncio.wait_for(reader.read(4096), timeout=5.0)
                if not data:
                    break
                for byte in data:
                    b = bytes([byte])
                    if b == b"\x0B":
                        buf.clear(); in_msg = True
                    elif b == b"\x1C" and in_msg:
                        in_msg = False
                        msg = bytes(buf); buf.clear()
                        self.received.append(msg)
                        writer.write(self._make_ack(msg))
                        await writer.drain()
                    elif in_msg:
                        buf.extend(b)
        except asyncio.TimeoutError:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    def _make_ack(self, original: bytes) -> bytes:
        text = original.decode("utf-8", errors="replace")
        m = re.search(r"MSH\|[^|]+\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|([^|]+)\|",
                      text)
        ctrl = m.group(1) if m else "UNKNOWN"
        body = (f"MSH|^~\\&|LIS|PRAXIS|LOC200_GW|PRAXIS|20250825120000||ACK^R01|"
                f"ACK{ctrl}|P|2.5\rMSA|{self.ack_code}|{ctrl}\r")
        return b"\x0B" + body.encode("utf-8") + b"\x1C\x0D"


class FakeLoc200Http:
    """Accepts an HTTP POST with a Bearer token and records the body."""

    def __init__(self, token: str = "test-token") -> None:
        self.token = token
        self.posts: List[dict] = []
        self._runner = None
        self.port: int = 0

    async def start(self) -> None:
        from aiohttp import web
        app = web.Application()

        async def handle(request):
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {self.token}":
                return web.json_response({"error": "unauthorized"}, status=401)
            body = await request.read()
            self.posts.append({
                "path": request.path,
                "body": body,
                "content_type": request.content_type,
            })
            return web.json_response({"status": "ok"})

        app.router.add_post("/", handle)
        app.router.add_post("/hl7", handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()


@pytest.fixture
async def fake_mllp():
    srv = FakeMLLPServer()
    await srv.start()
    yield srv
    await srv.stop()


@pytest.fixture
async def fake_mllp_reject():
    srv = FakeMLLPServer(ack_code="AR")
    await srv.start()
    yield srv
    await srv.stop()


@pytest.fixture
async def fake_loc200_http():
    srv = FakeLoc200Http()
    await srv.start()
    yield srv
    await srv.stop()
