"""
FHIR REST dispatcher.

POSTs a FHIR transaction Bundle to `<target.fhir_endpoint>` (typically
something like `https://fhir.hospital.example/`) with optional Bearer token
(loaded from secrets.env as `<TARGET>_FHIR_TOKEN`).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

log = logging.getLogger("loc200.fhir_dispatcher")


class FHIRDispatcher:
    def __init__(
        self,
        endpoint: str,
        token: Optional[str] = None,
        timeout: float = 15.0,
        verify_tls: bool = True,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._token    = token
        self._timeout  = timeout
        self._verify   = verify_tls

    async def dispatch(self, bundle: Dict[str, Any]) -> None:
        import aiohttp
        headers = {"Content-Type": "application/fhir+json",
                   "Accept":       "application/fhir+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        body = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
        timeout = aiohttp.ClientTimeout(total=self._timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self._endpoint, data=body,
                                    headers=headers, ssl=self._verify) as resp:
                text = await resp.text()
                if resp.status >= 300:
                    raise RuntimeError(
                        f"FHIR endpoint returned {resp.status}: {text[:400]}"
                    )
                log.info("FHIR dispatch OK (%d bytes -> %d)", len(body), resp.status)
