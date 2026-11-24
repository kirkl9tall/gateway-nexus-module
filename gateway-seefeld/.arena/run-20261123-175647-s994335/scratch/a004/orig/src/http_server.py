"""
LOC-200 HTTP ingestion server.

Accepts HL7 v2 or JSON result payloads from the LOC-200 analyzer over HTTP.

Security:
  * Bearer token required on all POST endpoints
    - token loaded from env LOC200_HTTP_TOKEN, or secrets.env key LOC200_HTTP_TOKEN
    - if unset, POSTs are rejected with 503 and a warning is logged at startup
  * Optional client IP allowlist via env LOC200_HTTP_ALLOW (comma-separated CIDRs / IPs)
  * Binds to LOC200_HTTP_BIND (default 0.0.0.0 — set to 127.0.0.1 when NAT/proxy fronts it)
  * Bodies capped at 256 KiB
  * GET /health is public and returns {"status":"ok"} only
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
from typing import Any, Dict, Optional

from aiohttp import web

from src.security.secrets import get_secret

log = logging.getLogger("loc200.http_server")

MAX_BODY_BYTES = 256 * 1024


def _load_token() -> Optional[str]:
    return get_secret("LOC200_HTTP_TOKEN")


def _load_allowlist() -> list[ipaddress._BaseNetwork]:
    raw = os.environ.get("LOC200_HTTP_ALLOW", "")
    nets: list[ipaddress._BaseNetwork] = []
    if not raw:
        return nets
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            nets.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            log.warning("Ignoring invalid entry in LOC200_HTTP_ALLOW: %r", item)
    return nets


class Loc200HttpServer:
    def __init__(self, queue, host: str | None = None, port: int = 5003):
        self._queue = queue
        # Safer default: localhost. Explicit opt-in via LOC200_HTTP_BIND=0.0.0.0
        # for LAN-attached analyzers.
        self._host  = host or os.environ.get("LOC200_HTTP_BIND", "127.0.0.1")
        self._port  = port
        # Simple per-IP rate limit: max 60 POST/min per source
        self._ratelimit_window = 60.0
        self._ratelimit_max    = 60
        from collections import defaultdict, deque as _deque
        self._ratelimit: dict[str, _deque] = defaultdict(lambda: _deque(maxlen=self._ratelimit_max))
        self._token = _load_token()
        self._allow = _load_allowlist()
        self._app   = web.Application(client_max_size=MAX_BODY_BYTES)
        self._runner = None

        for p in ["/", "/hl7", "/result", "/upload",
                  "/lis/detection", "/lis/upload", "/lis", "/detection"]:
            self._app.router.add_post(p, self._handle_post)
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/", self._handle_health)

    async def start(self):
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        await web.TCPSite(self._runner, self._host, self._port).start()
        log.info("HTTP server ready on http://%s:%d", self._host, self._port)
        # Log the actual reachable addresses instead of a hardcoded IP.
        try:
            import socket
            hostname = socket.gethostname()
            addrs = socket.gethostbyname_ex(hostname)[2]
            for ip in addrs:
                if ip and not ip.startswith("127."):
                    log.info("  LOC-200 should POST results to: http://%s:%d",
                             ip, self._port)
        except Exception:
            pass
        if not self._token:
            log.warning(
                "LOC200_HTTP_TOKEN is not set -- POST endpoints will reject with 503. "
                "Configure it in config/secrets.env or as an environment variable."
            )
        else:
            log.info("HTTP auth: Bearer token required (allowlist=%d net(s))",
                     len(self._allow))

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

    async def _handle_health(self, request):
        return web.json_response({"status": "ok"})

    # ── Security gates ────────────────────────────────────────────────────────

    def _check_ip(self, remote: str | None) -> bool:
        if not self._allow:
            return True
        if not remote:
            return False
        try:
            addr = ipaddress.ip_address(remote)
        except ValueError:
            return False
        return any(addr in net for net in self._allow)

    def _check_rate(self, ip: str | None) -> bool:
        import time as _time
        now = _time.time()
        dq = self._ratelimit[ip or "unknown"]
        while dq and now - dq[0] > self._ratelimit_window:
            dq.popleft()
        if len(dq) >= self._ratelimit_max:
            return False
        dq.append(now)
        return True

    def _check_token(self, request) -> bool:
        if not self._token:
            return False  # 503 upstream
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            supplied = header[7:].strip()
        else:
            supplied = request.headers.get("X-Auth-Token", "").strip()
        if not supplied:
            return False
        # constant-time compare
        import hmac as _hmac
        return _hmac.compare_digest(supplied, self._token)

    # ── POST handler ──────────────────────────────────────────────────────────

    async def _handle_post(self, request):
        remote = request.remote
        if not self._token:
            log.error("POST rejected — LOC200_HTTP_TOKEN not configured (from %s)", remote)
            return web.json_response(
                {"status": "error", "message": "server not configured"}, status=503)

        if not self._check_ip(remote):
            log.warning("POST rejected — %s not in LOC200_HTTP_ALLOW", remote)
            return web.json_response({"status": "forbidden"}, status=403)

        if not self._check_rate(remote):
            log.warning("POST rejected — rate limit exceeded for %s", remote)
            return web.json_response({"status": "rate_limited"}, status=429)

        if not self._check_token(request):
            log.warning("POST rejected — invalid or missing token (from %s)", remote)
            return web.json_response({"status": "unauthorized"}, status=401)

        try:
            body = await request.read()
        except web.HTTPRequestEntityTooLarge:
            return web.json_response(
                {"status": "error", "message": "body too large"}, status=413)
        except Exception as exc:
            log.error("Read error: %s", exc)
            return web.json_response({"status": "error"}, status=400)

        ct = request.content_type or ""
        log.info("POST from %s  size=%d bytes ct=%s", remote, len(body), ct)
        log.debug("Body head: %s", body[:500].decode("utf-8", errors="replace"))

        result = self._try_parse_json(body) if "json" in ct else None
        if result is None:
            result = self._try_parse_hl7(body)

        if result and result.get("observations"):
            try:
                self._queue.put_nowait(result)
            except Exception as exc:
                log.error("Queue full or error: %s", exc)
                return web.json_response(
                    {"status": "error", "message": "queue full"}, status=503)
            log.info("Result queued: sample=%s analytes=%d",
                     result.get("sample_id", "?"), len(result["observations"]))
            return web.json_response({"status": "ok"})

        log.warning("Payload had no parsable observations — see DEBUG")
        return web.json_response(
            {"status": "error", "message": "no observations parsed"}, status=422)

    # ── Parsers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _try_parse_json(body: bytes) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(body)
        except Exception:
            return None
        obs = []
        for item in (data.get("results") or data.get("items") or []):
            if not isinstance(item, dict):
                continue
            obs.append({
                "analyte":   str(item.get("name") or ""),
                "value":     str(item.get("value") or ""),
                "value_num": None,
                "flag":      str(item.get("flag") or ""),
                "ref_low":   None,
                "ref_high":  None,
                "unit":      str(item.get("unit") or ""),
            })
        if not obs:
            return None
        return {
            "sample_id":    str(data.get("sampleId") or ""),
            "patient_id":   str(data.get("patientId") or ""),
            "patient_name": str(data.get("patientName") or ""),
            "age":          data.get("age"),
            "gender":       str(data.get("gender") or ""),
            "disc_name":    str(data.get("discName") or ""),
            "lot_id":       str(data.get("lotId") or ""),
            "department":   "",
            "observations": obs,
            "_raw":         data,
        }

    @staticmethod
    def _try_parse_hl7(body: bytes) -> Optional[Dict[str, Any]]:
        """Delegate to the canonical LOC-200 HL7 parser (single source of truth)."""
        try:
            from src.adapters.loc200_reader import _parse_hl7
            text = body.decode("utf-8", errors="replace")
            if not ("MSH|" in text or "OBX|" in text):
                return None
            return _parse_hl7(text)
        except Exception as exc:
            log.debug("HL7 parse error: %s", exc)
            return None
