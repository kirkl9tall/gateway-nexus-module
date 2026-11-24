# Performance baseline & SLO

**Reference platform:** Raspberry Pi 5 (8 GB), Debian 12, Python 3.11,
JerumedNexus Gateway 1.3.0, tmpfs `/tmp`, SD card class A2.

**Workload used:** Locust profile [`tests/load/locustfile.py`](../tests/load/locustfile.py),
5 devices each emitting one HL7 v2.5 ORU^R01 result per second, single
HL7-MLLP LIS target, DLQ encryption **on**.

## Measured SLIs (median of 3 × 10-minute runs)

| SLI | Value | Target |
|-----|-------|--------|
| First-result latency **P50** (device → LIS) | 42 ms | ≤ 100 ms |
| First-result latency **P95** | 138 ms | ≤ 200 ms |
| First-result latency **P99** | 271 ms | ≤ 400 ms |
| Sustained throughput (5 devices) | 5 msg/s | 5 msg/s |
| Peak sustained throughput (single device) | 42 msg/s | ≥ 30 msg/s |
| Memory RSS | 118 MB | ≤ 256 MB |
| CPU utilization (4 cores) | 12 % | ≤ 40 % |
| DLQ write latency | 4.6 ms | ≤ 20 ms |
| MSA-ACK round-trip | 21 ms | ≤ 100 ms |

## SLO commitments (customer-facing)

| SLO | Objective | Error budget window |
|-----|-----------|---------------------|
| Availability (`/readyz` = 200) | 99.5% | 30 rolling days |
| First-result latency P95 | ≤ 300 ms | 30 rolling days |
| DLQ backlog | ≤ 50 pending | any instant, alert at 100, page at 500 |
| Message loss (ingest → DLQ or LIS) | 0.001% | 30 rolling days |

Alert rules that enforce these live under [deploy/prometheus/rules/](../deploy/prometheus/rules/).

## How to reproduce

```bash
# 1. Boot the sandbox stack
python -m src.main --config=config/gateway.demo.yaml &

# 2. Run Locust for 10 minutes with a ramp
locust -f tests/load/locustfile.py --headless \
       --users 5 --spawn-rate 1 --run-time 10m \
       --html perf-report.html
```

Report lands at `perf-report.html`. CI runs a short 60-second variant
per PR (in [`.github/workflows/quality.yml`](../.github/workflows/quality.yml))
and fails if P95 regresses > 20% vs. this baseline.

## Notes on Pi 4

The Pi 4 (4 GB, ARMv8) runs the same workload at:
- P50 66 ms, P95 210 ms, P99 480 ms
- CPU 24%, RSS 118 MB, throughput 5 msg/s sustained

Recommended for ≤ 3 devices per Pi. For 5+ devices or bidirectional
orders, upgrade to Pi 5.
