"""Integration: LOC-200 HTTP ingestion server."""
from __future__ import annotations

import asyncio

import pytest
from aiohttp import ClientSession

from src.http_server import Loc200HttpServer


@pytest.mark.asyncio
async def test_http_ingestion_requires_bearer(monkeypatch):
    monkeypatch.setenv("LOC200_HTTP_TOKEN", "s3cret-token")
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    srv = Loc200HttpServer(queue, host="127.0.0.1", port=0)
    await srv.start()
    site = next(iter(srv._runner.sites))
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with ClientSession() as sess:
            # Missing token -> 401
            r = await sess.post(f"http://127.0.0.1:{port}/",
                                data=b"MSH|^~\\&|X|Y|Z|Q|20250101120000||ORU^R01|1|P|2.5\r"
                                     b"OBX|1|NM|1920-8^AST^LN|1|10|U/L|15-40|||||F\r",
                                headers={"Content-Type": "text/plain"})
            assert r.status == 401
    finally:
        await srv.stop()


@pytest.mark.asyncio
async def test_http_ingestion_accepts_valid_bearer(monkeypatch):
    monkeypatch.setenv("LOC200_HTTP_TOKEN", "s3cret-token")
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    srv = Loc200HttpServer(queue, host="127.0.0.1", port=0)
    await srv.start()
    site = next(iter(srv._runner.sites))
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with ClientSession() as sess:
            r = await sess.post(
                f"http://127.0.0.1:{port}/",
                data=b"MSH|^~\\&|X|Y|Z|Q|20250101120000||ORU^R01|1|P|2.5\r"
                     b"PID||PAT123|PAT123||Mueller^Hans||||M\r"
                     b"OBR|1|||PAT123^PAT123^L||20250101120000|20250101120000|||||||||||||F\r"
                     b"OBX|1|NM|1920-8^AST^LN|1|10|U/L|15-40|||||F\r",
                headers={"Content-Type": "text/plain",
                         "Authorization": "Bearer s3cret-token"})
            assert r.status == 200
            item = await asyncio.wait_for(queue.get(), timeout=2.0)
            assert item["observations"]
            assert item["observations"][0]["analyte"] == "1920-8"
    finally:
        await srv.stop()


@pytest.mark.asyncio
async def test_http_ingestion_rejects_when_token_unset():
    # LOC200_HTTP_TOKEN unset -> the server logs a warning at start and 503s POSTs
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    srv = Loc200HttpServer(queue, host="127.0.0.1", port=0)
    await srv.start()
    site = next(iter(srv._runner.sites))
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with ClientSession() as sess:
            r = await sess.post(f"http://127.0.0.1:{port}/",
                                data=b"MSH|...\r",
                                headers={"Content-Type": "text/plain",
                                         "Authorization": "Bearer whatever"})
            assert r.status == 503
    finally:
        await srv.stop()
