# SLO / SLI framework

Formal Service Level Objectives + Indicators for JerumedNexus Gateway.

## Overview

- **SLI** — Service Level Indicator: a metric we can measure (e.g. dispatch
  success rate).
- **SLO** — Service Level Objective: a target for an SLI (e.g. 99.9% success
  rate over 30 days rolling).
- **Error budget** — allowed non-compliance (e.g. 0.1% of 30d ≈ 43 min).

## Our SLOs

| SLI | Target | Window | Severity |
|-----|--------|--------|----------|
| `dispatch_success_rate` | 99.9% | 30d | high |
| `gateway_availability`  | 99.9% | 30d | critical |
| `ingest_latency_p99`    | <5000 ms | 7d | medium |
| `queue_backpressure`    | 99.5% (buckets w/o queue-full) | 30d | medium |
| `device_freshness`      | 99% (devices reporting <1h) | 7d | high |

Defined in `config/slo.yaml`.

## Generate Prometheus rules

```bash
python -m src.common.slo > /etc/prometheus/rules/jerumednexus-slos.yml
sudo systemctl reload prometheus
```

## Burn rate alerts

Multi-window burn detection à la Google SRE book:

| Alert | Window | Burn rate | Action |
|-------|--------|-----------|--------|
| `fast_burn` | 1h + 6h | 14.4× normal | page on-call |
| `slow_burn` | 24h + 3d | 6× normal | ticket |

## Enterprise SLA contract

Customer-facing SLA is derived from these SLOs. Example clause:

> The Vendor commits to a monthly dispatch success rate of at least 99.5%
> for enabled targets, measured from the timestamp of receipt at the
> gateway HTTP ingestion endpoint to the ACK from the target PIS.
> If breached, service credits apply as follows: …

See [SLA report](API.md#sla-report) endpoint for automated monthly reports.
