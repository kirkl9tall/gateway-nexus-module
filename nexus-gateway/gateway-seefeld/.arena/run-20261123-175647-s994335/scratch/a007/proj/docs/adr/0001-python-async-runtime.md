# ADR-0001 — Python asyncio as the runtime

- **Status:** Accepted
- **Date:** 2026-08-01
- **Deciders:** core engineering

## Context

The gateway must talk to multiple analyzers simultaneously (2–10 per
Pi), each on its own serial port or TCP socket, each with its own
protocol state machine. Multiplex I/O on a 4-core Pi is the bottleneck,
not CPU.

Options considered:
1. Python + asyncio + `serial_asyncio`.
2. Python + threads.
3. Go rewrite.
4. Rust rewrite.

## Decision

**Python 3.11+ with asyncio**, `serial_asyncio` for RS-232 devices,
`asyncio.StreamServer` for TCP.

Rationale: (a) fits the I/O-bound workload with negligible CPU, (b)
the existing team is Python-fluent, (c) HL7/FHIR libraries in Python
are mature (`hl7apy`, `fhir.resources`), (d) ships as a plain `.deb`
via `dh_virtualenv` without needing a cross-compiler for ARM64.

## Consequences

- Positive: fast iteration, single language across gateway and Web UI,
  easy hiring.
- Negative: GIL means CPU-bound work (large FHIR bundles, TLS hs) can
  block the loop — we mitigate with `asyncio.to_thread` for parsers
  above 100 KB and TLS termination at the OS layer.
- Rejected Go/Rust: cost of rewrite not justified while I/O dominates.
  Reconsider if per-Pi throughput exceeds 5 msg/s sustained.
