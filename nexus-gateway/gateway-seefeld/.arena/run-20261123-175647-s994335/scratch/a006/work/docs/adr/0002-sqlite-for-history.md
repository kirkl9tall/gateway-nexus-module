# ADR-0002 — SQLite for dispatch history

- **Status:** Accepted
- **Date:** 2026-08-05
- **Deciders:** core engineering, DPO

## Context

The gateway needs to remember every dispatch (patient_id, sample_id,
targets, status, timestamp) for audit and troubleshooting. Retention
is 90 days by default. Typical clinic volume: 50–500 dispatches/day.

Options:
1. SQLite file on the Pi.
2. PostgreSQL container on the Pi.
3. Remote database in the vendor cloud.

## Decision

**SQLite** at `logs/history.db`, WAL mode, exclusive to the
`jerumednexus` user.

## Consequences

- Positive: **no patient data leaves the Pi** — hard requirement from
  Swiss nDSG. Zero admin overhead. Backed up by the tar script.
- Positive: 500/day × 90 days = 45k rows — SQLite handles this
  trivially, no risk of hitting size limits.
- Negative: no cross-Pi query. Multi-Pi deployments must aggregate at
  the LIS side (they already do).
- Rejected Postgres: adds a systemd unit, an RCE surface, and 100 MB of
  RAM for no benefit at this scale.
- Rejected vendor cloud: violates data-residency requirements and the
  DPA (see [docs/PRIVACY.md](../PRIVACY.md)).
