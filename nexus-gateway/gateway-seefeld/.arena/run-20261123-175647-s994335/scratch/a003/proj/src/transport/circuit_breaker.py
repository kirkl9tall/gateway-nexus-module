"""
Per-target circuit breaker.

States:
  closed    -- normal operation; calls go through, failures counted.
  open      -- N consecutive failures; new calls short-circuit for
               ``recovery_timeout`` seconds without hitting the network.
  half-open -- after the timeout, one probe call is allowed; success closes
               the circuit, failure re-opens it.

Metrics: state transitions written to logs/status.json via the getter
``snapshot()``.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger("loc200.circuit_breaker")

_STATE_FILE = Path("logs/breakers.json")


class State(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half-open"


@dataclass
class Breaker:
    threshold:        int   = 5
    recovery_timeout: float = 60.0
    state:            State = State.CLOSED
    consecutive_failures: int = 0
    opened_at:        float = 0.0
    total_failures:   int   = 0
    total_successes:  int   = 0

    def allow(self) -> bool:
        if self.state == State.CLOSED:
            return True
        if self.state == State.OPEN:
            if time.time() - self.opened_at >= self.recovery_timeout:
                self.state = State.HALF_OPEN
                log.info("circuit breaker HALF-OPEN (probing)")
                return True
            return False
        # HALF_OPEN: allow one probe -- the next call decides
        return True

    def record_success(self) -> None:
        self.total_successes += 1
        self.consecutive_failures = 0
        if self.state != State.CLOSED:
            log.info("circuit breaker CLOSED (recovered)")
            self.state = State.CLOSED

    def record_failure(self) -> None:
        self.total_failures += 1
        self.consecutive_failures += 1
        if self.state == State.HALF_OPEN:
            self.state = State.OPEN
            self.opened_at = time.time()
            log.warning("circuit breaker re-OPENED after probe failure")
            return
        if self.state == State.CLOSED and self.consecutive_failures >= self.threshold:
            self.state = State.OPEN
            self.opened_at = time.time()
            log.warning("circuit breaker OPEN after %d consecutive failures",
                        self.consecutive_failures)


class BreakerRegistry:
    """One breaker per (target_name). State is persisted to logs/breakers.json."""

    def __init__(
        self,
        threshold: int = 5,
        recovery_timeout: float = 60.0,
        state_file: Optional[Path] = None,
    ) -> None:
        self._threshold = threshold
        self._recovery  = recovery_timeout
        self._store: Dict[str, Breaker] = {}
        self._state_file = state_file or _STATE_FILE
        self._load()

    def _load(self) -> None:
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("breaker state unreadable: %s -- starting fresh", exc)
            return
        for name, row in (data or {}).items():
            try:
                b = Breaker(
                    threshold=self._threshold,
                    recovery_timeout=self._recovery,
                    state=State(row.get("state", "closed")),
                    consecutive_failures=int(row.get("consecutive_failures", 0)),
                    opened_at=float(row.get("opened_at", 0.0)),
                    total_failures=int(row.get("total_failures", 0)),
                    total_successes=int(row.get("total_successes", 0)),
                )
                self._store[name] = b
            except Exception:
                continue
        log.info("Loaded %d breaker state(s) from %s",
                 len(self._store), self._state_file)

    def _save(self) -> None:
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = self.snapshot()
            tmp = self._state_file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(tmp, self._state_file)
        except Exception as exc:
            log.debug("breaker state save failed: %s", exc)

    def get(self, name: str) -> Breaker:
        b = self._store.get(name)
        if b is None:
            b = Breaker(threshold=self._threshold, recovery_timeout=self._recovery)
            self._store[name] = b
        return b

    def record_success(self, name: str) -> None:
        self.get(name).record_success()
        self._save()

    def record_failure(self, name: str) -> None:
        self.get(name).record_failure()
        self._save()

    def snapshot(self) -> Dict[str, Dict]:
        return {
            name: {
                "state":               b.state.value,
                "consecutive_failures": b.consecutive_failures,
                "total_failures":      b.total_failures,
                "total_successes":     b.total_successes,
                "opened_at":           b.opened_at,
            }
            for name, b in self._store.items()
        }
