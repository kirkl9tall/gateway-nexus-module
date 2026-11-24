"""
Token-bucket rate limiter per source (device or LIS).

Protects the gateway from a device that suddenly floods (firmware bug,
DoS, stuck loop). Default: 60 messages/minute per source, burst of 30.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Lock

log = logging.getLogger("loc200.rate_limit")


@dataclass
class Bucket:
    tokens:      float
    capacity:    float
    refill_rate: float   # tokens per second
    last_refill: float


class RateLimiter:
    def __init__(self, capacity: int = 30, per_minute: int = 60) -> None:
        self._capacity = float(capacity)
        self._rate = per_minute / 60.0
        self._buckets: dict[str, Bucket] = {}
        self._lock = Lock()

    def check(self, source: str) -> bool:
        """Return True if the request is allowed; consume a token if so."""
        now = time.time()
        with self._lock:
            b = self._buckets.get(source)
            if b is None:
                b = Bucket(tokens=self._capacity, capacity=self._capacity,
                            refill_rate=self._rate, last_refill=now)
                self._buckets[source] = b
            # Refill
            elapsed = now - b.last_refill
            b.tokens = min(b.capacity, b.tokens + elapsed * b.refill_rate)
            b.last_refill = now
            if b.tokens >= 1.0:
                b.tokens -= 1.0
                return True
            log.warning("Rate limit hit for source %r (bucket empty)", source)
            return False

    def stats(self) -> dict[str, dict]:
        with self._lock:
            return {
                s: {"tokens": round(b.tokens, 2), "capacity": b.capacity}
                for s, b in self._buckets.items()
            }


_GLOBAL: RateLimiter | None = None


def get() -> RateLimiter:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = RateLimiter()
    return _GLOBAL
