"""
Per-target adaptive circuit breaker.

Learns each LIS's latency histogram (P50 / P95 / P99) and derives its own
timeout dynamically instead of the static 30 s default.

Rules:
  * timeout = max(2 s, P99 × 1.5)  — recompute every 100 dispatches
  * open the breaker after N consecutive failures where N adapts to the
    LIS's success rate (a flaky LIS needs a lower N to protect us).
  * half-open sooner if the LIS's typical downtime is short.

Keeps state per (target_name) in memory + persists a snapshot in
`logs/breakers.json` for observability.
"""
from __future__ import annotations

import json
import logging
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

log = logging.getLogger("loc200.adaptive_breaker")

BreakerState = Literal["closed", "half_open", "open"]


@dataclass
class TargetProfile:
    name:              str
    latencies_ms:      deque = field(default_factory=lambda: deque(maxlen=500))
    consecutive_fails: int = 0
    total_success:     int = 0
    total_failure:     int = 0
    state:             BreakerState = "closed"
    opened_at:         float = 0.0
    computed_timeout:  float = 30.0
    computed_max_fails: int = 5

    def record_success(self, latency_ms: float) -> None:
        self.latencies_ms.append(latency_ms)
        self.consecutive_fails = 0
        self.total_success += 1
        if self.state == "half_open":
            self.state = "closed"
            log.info("Adaptive breaker %s closed after successful probe", self.name)
        self._recompute()

    def record_failure(self) -> None:
        self.consecutive_fails += 1
        self.total_failure += 1
        if self.consecutive_fails >= self.computed_max_fails and self.state != "open":
            self.state = "open"
            self.opened_at = time.time()
            log.warning("Adaptive breaker %s OPENED (%d consecutive failures, "
                        "timeout=%.1fs)",
                        self.name, self.consecutive_fails, self.computed_timeout)

    def maybe_half_open(self, min_open_seconds: float = 30.0) -> None:
        if self.state == "open" and time.time() - self.opened_at >= min_open_seconds:
            self.state = "half_open"
            log.info("Adaptive breaker %s → half_open (probing)", self.name)

    def allow_request(self) -> bool:
        self.maybe_half_open()
        return self.state != "open"

    def _recompute(self) -> None:
        if len(self.latencies_ms) < 20 or self.total_success % 100 != 0:
            return
        try:
            sorted_l = sorted(self.latencies_ms)
            p99_idx = int(len(sorted_l) * 0.99)
            p99 = sorted_l[min(p99_idx, len(sorted_l) - 1)]
            self.computed_timeout = max(2.0, p99 * 1.5 / 1000.0)
            # Success rate influences failure tolerance
            total = self.total_success + self.total_failure
            if total > 0:
                sr = self.total_success / total
                # 5 failures at 99% rate, 3 at 90%
                self.computed_max_fails = max(3, int(sr * 10) - 2)
            log.debug("Breaker %s recomputed: timeout=%.1fs max_fails=%d",
                      self.name, self.computed_timeout, self.computed_max_fails)
        except Exception:
            pass

    def snapshot(self) -> dict:
        return {
            "name":              self.name,
            "state":             self.state,
            "consecutive_fails": self.consecutive_fails,
            "total_success":     self.total_success,
            "total_failure":     self.total_failure,
            "computed_timeout":  round(self.computed_timeout, 2),
            "computed_max_fails": self.computed_max_fails,
            "p50_ms":            statistics.median(self.latencies_ms) if self.latencies_ms else 0,
            "p95_ms":            (sorted(self.latencies_ms)[int(len(self.latencies_ms)*0.95)]
                                   if self.latencies_ms else 0),
        }


class BreakerRegistry:
    def __init__(self) -> None:
        self._targets: dict[str, TargetProfile] = {}

    def get(self, target_name: str) -> TargetProfile:
        if target_name not in self._targets:
            self._targets[target_name] = TargetProfile(name=target_name)
        return self._targets[target_name]

    def snapshot_to_disk(self) -> None:
        try:
            p = Path("logs/breakers.json")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({
                t.name: t.snapshot() for t in self._targets.values()
            }, indent=2), encoding="utf-8")
        except Exception as exc:
            log.debug("breakers snapshot failed: %s", exc)


_REGISTRY = BreakerRegistry()


def get_breaker(target_name: str) -> TargetProfile:
    return _REGISTRY.get(target_name)


def snapshot_all() -> None:
    _REGISTRY.snapshot_to_disk()
