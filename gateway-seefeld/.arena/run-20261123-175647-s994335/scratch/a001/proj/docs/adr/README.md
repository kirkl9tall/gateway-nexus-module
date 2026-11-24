# Architecture Decision Records (ADR)

Short, dated, immutable records of decisions that shaped the system.
When a decision is revisited, we **do not edit** the old ADR — we
supersede it with a new one and link them.

Format: [MADR 3.0](https://adr.github.io/madr/).

## Index

- [ADR-0001](0001-python-async-runtime.md) — Python asyncio as the
  runtime.
- [ADR-0002](0002-sqlite-for-history.md) — SQLite for dispatch
  history.
- [ADR-0003](0003-fernet-for-dlq.md) — Fernet (AES-128-CBC + HMAC) for
  DLQ encryption at rest.
- [ADR-0004](0004-yaml-device-profiles.md) — YAML device profiles under
  `config/devices/`.
- [ADR-0005](0005-mllp-and-astm-both.md) — Support both HL7 MLLP and
  ASTM E1381/1394 first-class.

Add a new ADR by copying the template below into
`docs/adr/NNNN-slug.md` (four-digit, incrementing).

## Template

```markdown
# ADR-NNNN — <title>

- **Status:** Proposed | Accepted | Deprecated | Superseded by ADR-XXXX
- **Date:** YYYY-MM-DD
- **Deciders:** <names / roles>

## Context

Why this decision is needed. What forces are at play (business,
regulatory, technical).

## Decision

The choice, stated in one sentence, then the rationale.

## Consequences

What changes because of this — good and bad. Which alternatives were
rejected and why.
```
