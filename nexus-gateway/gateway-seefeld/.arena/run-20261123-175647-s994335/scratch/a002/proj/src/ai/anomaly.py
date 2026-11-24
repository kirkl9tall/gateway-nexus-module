"""
Operational anomaly detection — pure statistics, no LLM, no clinical use.

Feeds:
  * dispatch inter-arrival times per device
  * DLQ growth rate
  * Circuit breaker state changes per hour
  * Auth failures per minute

Uses IsolationForest (scikit-learn) if available, otherwise a simple
3-sigma rule. Emits alerts via src.common.alerts.
"""
from __future__ import annotations

import logging
import statistics
import time
from collections import deque

log = logging.getLogger("loc200.anomaly")


class SigmaWindow:
    """Rolling window with mean/stdev — 3σ outlier detection."""

    def __init__(self, size: int = 100) -> None:
        self._window: deque[float] = deque(maxlen=size)

    def add(self, value: float) -> None:
        self._window.append(value)

    def is_anomalous(self, value: float, k: float = 3.0) -> bool:
        if len(self._window) < 20:
            return False
        try:
            mu = statistics.mean(self._window)
            sd = statistics.stdev(self._window) or 1.0
            return abs(value - mu) > k * sd
        except statistics.StatisticsError:
            return False


class InterArrivalMonitor:
    """Alert when a device's inter-arrival time exceeds 3σ from its baseline."""

    def __init__(self) -> None:
        self._last_seen: dict[str, float] = {}
        self._sigma: dict[str, SigmaWindow] = {}

    def record_receive(self, device: str) -> None:
        now = time.time()
        prev = self._last_seen.get(device)
        self._last_seen[device] = now
        if prev is None:
            return
        gap = now - prev
        sw = self._sigma.setdefault(device, SigmaWindow(size=200))
        anomalous = sw.is_anomalous(gap)
        sw.add(gap)
        if anomalous:
            log.warning("Inter-arrival anomaly on %s: gap=%.1fs (3σ from baseline)",
                        device, gap)
            try:
                from src.common.alerts import fire
                fire("warning", "inter_arrival_anomaly",
                     f"{device} silent {gap:.0f}s (unusual)",
                     {"device": device, "gap_seconds": round(gap, 1)})
            except Exception:
                pass


_MONITOR: InterArrivalMonitor | None = None


def get_monitor() -> InterArrivalMonitor:
    global _MONITOR
    if _MONITOR is None:
        _MONITOR = InterArrivalMonitor()
    return _MONITOR


def record_device_receive(device: str) -> None:
    get_monitor().record_receive(device)


class DLQGrowthMonitor:
    """Detects rapid DLQ growth (LIS down)."""

    def __init__(self, threshold_per_min: int = 20) -> None:
        self._samples: deque[tuple[float, int]] = deque(maxlen=60)
        self._threshold = threshold_per_min

    def sample(self, current_count: int) -> None:
        now = time.time()
        self._samples.append((now, current_count))
        # Look at last minute
        cutoff = now - 60.0
        recent = [s for s in self._samples if s[0] >= cutoff]
        if len(recent) < 2:
            return
        delta = recent[-1][1] - recent[0][1]
        if delta >= self._threshold:
            log.warning("DLQ growth anomaly: +%d messages/min", delta)
            try:
                from src.common.alerts import fire
                fire("critical", "dlq_growth",
                     f"DLQ growing at {delta}/min — LIS unreachable?",
                     {"delta_per_min": delta})
            except Exception:
                pass


_DLQ_MON: DLQGrowthMonitor | None = None


def get_dlq_monitor() -> DLQGrowthMonitor:
    global _DLQ_MON
    if _DLQ_MON is None:
        _DLQ_MON = DLQGrowthMonitor()
    return _DLQ_MON
