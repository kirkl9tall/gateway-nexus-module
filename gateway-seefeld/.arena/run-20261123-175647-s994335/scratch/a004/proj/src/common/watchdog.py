"""
Reader watchdog — every reader emits a heartbeat. If we don't hear it for
`silence_threshold_seconds`, restart it. If restart fails 3× in 10 min,
open a circuit-breaker on that reader and alert the operator.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger("loc200.watchdog")


@dataclass
class ReaderState:
    name:           str
    last_heartbeat: float = field(default_factory=time.time)
    restart_events: deque = field(default_factory=lambda: deque(maxlen=10))
    disabled:       bool = False


class Watchdog:
    """
    Poll-based watchdog. Every reader calls `heartbeat(name)` after each
    successful read. Watchdog loop wakes every 30 s and checks silence.
    """

    def __init__(
        self,
        restart_fn: Callable[[str], None],
        silence_threshold_seconds: float = 60.0,
        max_restarts_per_window: int = 3,
        window_seconds: float = 600.0,
        check_interval_seconds: float = 30.0,
        alert_fn: Callable[[str, str], None] | None = None,
    ) -> None:
        self._restart_fn    = restart_fn
        self._silence       = silence_threshold_seconds
        self._max_restarts  = max_restarts_per_window
        self._window        = window_seconds
        self._interval      = check_interval_seconds
        self._alert         = alert_fn
        self._readers: dict[str, ReaderState] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def heartbeat(self, name: str) -> None:
        with self._lock:
            r = self._readers.get(name)
            if r is None:
                r = ReaderState(name=name)
                self._readers[name] = r
            r.last_heartbeat = time.time()

    def register(self, name: str) -> None:
        self.heartbeat(name)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                         name="reader-watchdog")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval):
            self._tick()

    def _tick(self) -> None:
        now = time.time()
        with self._lock:
            names = list(self._readers.keys())
        for name in names:
            with self._lock:
                r = self._readers[name]
                if r.disabled:
                    continue
                silence = now - r.last_heartbeat
            if silence < self._silence:
                continue
            # Reader silent — restart, unless throttled
            with self._lock:
                # Prune old restart events
                cutoff = now - self._window
                while r.restart_events and r.restart_events[0] < cutoff:
                    r.restart_events.popleft()
                if len(r.restart_events) >= self._max_restarts:
                    r.disabled = True
                    log.error("Reader %r restarted %d× in %ds — DISABLING",
                              name, self._max_restarts, int(self._window))
                    if self._alert:
                        try:
                            self._alert("critical",
                                        f"reader {name} disabled after "
                                        f"{self._max_restarts} restarts")
                        except Exception:
                            pass
                    continue
                r.restart_events.append(now)
            log.warning("Reader %r silent for %.0fs — restarting", name, silence)
            try:
                self._restart_fn(name)
                self.heartbeat(name)  # reset the clock
            except Exception as exc:
                log.error("Restart of %r failed: %s", name, exc)

    def status(self) -> list[dict]:
        with self._lock:
            return [{
                "name":            r.name,
                "last_heartbeat":  r.last_heartbeat,
                "silence_seconds": time.time() - r.last_heartbeat,
                "restart_count":   len(r.restart_events),
                "disabled":        r.disabled,
            } for r in self._readers.values()]
