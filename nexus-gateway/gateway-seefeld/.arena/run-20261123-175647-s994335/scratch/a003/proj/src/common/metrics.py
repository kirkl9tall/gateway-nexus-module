"""
Prometheus metrics for the conversion audit + operational counters.

Exposed on /metrics. Fresh metric families that complement what
`src/telemetry.py` already exposes.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("loc200.metrics")


# Fallback stubs — real registration happens if prometheus_client is installed.
class _Stub:
    def labels(self, **kwargs: Any) -> "_Stub":
        return self

    def inc(self, amount: float = 1.0) -> None:
        pass

    def observe(self, amount: float) -> None:
        pass

    def set(self, amount: float) -> None:
        pass


_METRICS: dict[str, Any] = {}


def _init() -> None:
    global _METRICS
    if _METRICS:
        return
    try:
        from prometheus_client import Counter, Histogram, Gauge
    except ImportError:
        log.debug("prometheus_client not installed — metrics stubs in use")
        for name in ("conversion_warnings_total", "plausibility_flags_total",
                      "dispatch_latency_seconds", "device_up",
                      "wal_in_flight", "dlq_backlog", "queue_evictions_total"):
            _METRICS[name] = _Stub()
        return

    _METRICS["conversion_warnings_total"] = Counter(
        "jerumednexus_conversion_warnings_total",
        "Conversion audit warnings emitted",
        ["device", "kind"],
    )
    _METRICS["plausibility_flags_total"] = Counter(
        "jerumednexus_plausibility_flags_total",
        "Values that triggered a plausibility TC flag",
        ["analyte"],
    )
    _METRICS["dispatch_latency_seconds"] = Histogram(
        "jerumednexus_dispatch_latency_seconds",
        "End-to-end latency from device receive to LIS ACK",
        ["device", "target"],
        buckets=(0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0),
    )
    _METRICS["device_up"] = Gauge(
        "jerumednexus_device_up",
        "1 if the device reader is connected, 0 otherwise",
        ["device"],
    )
    _METRICS["wal_in_flight"] = Gauge(
        "jerumednexus_wal_in_flight",
        "Number of messages currently in the WAL awaiting LIS ACK",
    )
    _METRICS["dlq_backlog"] = Gauge(
        "jerumednexus_dlq_backlog",
        "Number of messages in the dead-letter queue",
    )
    _METRICS["queue_evictions_total"] = Counter(
        "jerumednexus_queue_evictions_total",
        "Priority-queue evictions when full",
        ["evicted_priority"],
    )


def get(name: str) -> Any:
    _init()
    return _METRICS.get(name, _Stub())


def snapshot() -> dict[str, Any]:
    """For unit tests — return the current metric values as a dict."""
    _init()
    return {k: type(v).__name__ for k, v in _METRICS.items()}
