"""
OpenTelemetry integration.

Optional -- gateway runs without opentelemetry installed.
Enable by setting:
  OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-collector.example:4317
  OTEL_SERVICE_NAME=jerumednexus-gateway
  OTEL_RESOURCE_ATTRIBUTES=deployment.environment=prod,service.namespace=lab

Traces:
  * dispatch                    -- one span per dispatch call, target as attr
  * dispatch.mllp_send          -- MLLP roundtrip
  * dispatch.fhir_send          -- FHIR POST
  * reader.parse                -- adapter parse (adapter as attr)

Metrics:
  * jerumednexus.messages.received   counter
  * jerumednexus.messages.dispatched counter
  * jerumednexus.dispatch.latency    histogram
"""
from __future__ import annotations

import contextlib
import logging
import os
from typing import Any, Iterator

log = logging.getLogger("loc200.telemetry")

_tracer = None
_meter  = None
_dispatch_counter = None
_received_counter = None
_dispatch_latency = None


def configure() -> None:
    """Idempotent OTEL setup. No-op if opentelemetry not installed."""
    global _tracer, _meter, _dispatch_counter, _received_counter, _dispatch_latency
    if _tracer is not None:
        return
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.debug("opentelemetry not installed -- telemetry disabled")
        return

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        log.debug("OTEL_EXPORTER_OTLP_ENDPOINT not set -- telemetry disabled")
        return

    resource = Resource.create({
        SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", "jerumednexus-gateway"),
    })

    # Traces
    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(tp)
    _tracer = trace.get_tracer("jerumednexus")

    # Metrics
    reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint),
                                            export_interval_millis=30000)
    mp = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(mp)
    _meter = metrics.get_meter("jerumednexus")

    _received_counter = _meter.create_counter(
        "jerumednexus.messages.received", unit="1",
        description="Messages received from analyzers",
    )
    _dispatch_counter = _meter.create_counter(
        "jerumednexus.messages.dispatched", unit="1",
        description="Messages dispatched to targets",
    )
    _dispatch_latency = _meter.create_histogram(
        "jerumednexus.dispatch.latency", unit="ms",
        description="End-to-end dispatch latency",
    )
    log.info("OpenTelemetry enabled -> %s", endpoint)


@contextlib.contextmanager
def span(name: str, **attrs: Any) -> Iterator[Any]:
    """Context manager that starts an OTEL span (no-op if OTEL not configured)."""
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as sp:
        for k, v in attrs.items():
            try:
                sp.set_attribute(k, v)
            except Exception:
                pass
        yield sp


def count_received(device: str = "") -> None:
    if _received_counter is not None:
        _received_counter.add(1, {"device": device or "unknown"})


def count_dispatched(target: str = "", success: bool = True) -> None:
    if _dispatch_counter is not None:
        _dispatch_counter.add(1, {"target": target or "unknown",
                                  "success": str(success).lower()})


def record_dispatch_latency(ms: float, target: str = "") -> None:
    if _dispatch_latency is not None:
        _dispatch_latency.record(ms, {"target": target or "unknown"})
