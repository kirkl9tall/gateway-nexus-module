# Load tests

Locust-driven simulation of many analyzers pushing HL7.

## Prerequisites

```bash
pip install locust
```

The gateway must be running and `LOC200_HTTP_TOKEN` set (same value both sides).

## Baseline expected performance (Raspberry Pi 4 with 4GB RAM)

| Load | Success | p95 latency | Notes |
|------|---------|-------------|-------|
| 10 msg/s sustained  | 100% | < 20 ms | comfortable |
| 30 msg/s sustained  | 100% | < 40 ms | typical hospital lab peak |
| 100 msg/s burst 30s | > 99% | < 200 ms | queue absorbs, no drops |
| 200 msg/s sustained | > 90% | < 500 ms | expect queue_full events + DLQ |

## Run

```bash
# 50 concurrent virtual analyzers, spawning 5 users/sec
LOC200_HTTP_TOKEN=xxxxxxxx locust -f tests/load/locustfile.py \
    --host http://127.0.0.1:5003 --users 50 --spawn-rate 5

# Headless one-off:
LOC200_HTTP_TOKEN=xxxxxxxx locust -f tests/load/locustfile.py \
    --host http://127.0.0.1:5003 --users 50 --spawn-rate 5 \
    --run-time 5m --headless --csv results/loc200
```

Open http://localhost:8089 for the interactive dashboard.

## What to watch

- `/metrics` on the WebUI port -- watch `jerumednexus_queue_size` and
  `jerumednexus_queue_full_events` counter
- `logs/gateway.log` for any WARN/ERROR
- `logs/dead_letter/` -- should stay empty in normal load; if items appear
  something is dropping downstream
