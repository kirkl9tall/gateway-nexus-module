"""
Multi-LIS dispatch semantics: mirror | failover | roundrobin.

Configured in gateway.yaml:
    outputs:
      - {name: "Tomedo primary",  kind: mllp_hl7, host: 10.0.0.10, port: 2575}
      - {name: "Tomedo backup",   kind: mllp_hl7, host: 10.0.0.11, port: 2575}
    output_mode: mirror       # or "failover" or "roundrobin"

- mirror     — send to all, success = at least one ACK
- failover   — send to primary; on breaker open → send to next
- roundrobin — alternate targets, one at a time (load balancing)
"""
from __future__ import annotations

import asyncio
import itertools
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

log = logging.getLogger("loc200.multi_target")


@dataclass
class TargetResult:
    target_name: str
    ok:          bool
    latency_ms:  float
    error:       str = ""


class MultiTargetDispatcher:
    """
    Wraps N single-target senders and applies mode-specific policy.
    Each `sender` is an async callable that takes (target_dict, hl7_body)
    and returns TargetResult.
    """

    def __init__(
        self,
        targets: list[dict[str, Any]],
        sender: Callable[[dict[str, Any], bytes], Awaitable[TargetResult]],
        mode: str = "failover",
    ) -> None:
        self._targets = targets
        self._sender  = sender
        self._mode    = mode
        self._rr_iter = itertools.cycle(range(len(targets))) if targets else iter([])
        self._breaker_state: dict[str, bool] = {t["name"]: True for t in targets}

    def mark_target_healthy(self, name: str, healthy: bool) -> None:
        self._breaker_state[name] = healthy

    async def dispatch(self, hl7_body: bytes) -> list[TargetResult]:
        if self._mode == "mirror":
            return await self._mirror(hl7_body)
        if self._mode == "roundrobin":
            return await self._roundrobin(hl7_body)
        return await self._failover(hl7_body)

    async def _mirror(self, body: bytes) -> list[TargetResult]:
        coros = [self._sender(t, body) for t in self._targets
                 if self._breaker_state.get(t["name"], True)]
        results = await asyncio.gather(*coros, return_exceptions=True)
        out: list[TargetResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                out.append(TargetResult(target_name=self._targets[i]["name"],
                                         ok=False, latency_ms=0,
                                         error=str(r)))
            else:
                out.append(r)
        ok_count = sum(1 for r in out if r.ok)
        log.info("Mirror dispatch: %d/%d targets ACK", ok_count, len(out))
        return out

    async def _failover(self, body: bytes) -> list[TargetResult]:
        out: list[TargetResult] = []
        for t in self._targets:
            if not self._breaker_state.get(t["name"], True):
                out.append(TargetResult(target_name=t["name"], ok=False,
                                         latency_ms=0, error="breaker open"))
                continue
            try:
                r = await self._sender(t, body)
            except Exception as exc:
                r = TargetResult(target_name=t["name"], ok=False,
                                  latency_ms=0, error=str(exc))
            out.append(r)
            if r.ok:
                return out
        log.warning("Failover exhausted all %d targets", len(self._targets))
        return out

    async def _roundrobin(self, body: bytes) -> list[TargetResult]:
        idx = next(self._rr_iter)
        # Try up to N times, moving forward until one succeeds
        for _ in range(len(self._targets)):
            t = self._targets[idx]
            if self._breaker_state.get(t["name"], True):
                try:
                    r = await self._sender(t, body)
                    if r.ok:
                        return [r]
                except Exception as exc:
                    log.warning("RR target %s error: %s", t["name"], exc)
            idx = next(self._rr_iter)
        return [TargetResult(target_name="(all)", ok=False, latency_ms=0,
                              error="no target accepted")]
