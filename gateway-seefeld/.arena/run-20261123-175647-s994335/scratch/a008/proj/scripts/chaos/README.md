# Chaos engineering scripts

Small fault-injection scripts to validate the gateway's resilience.
**Run only in staging**, never in production.

| Script | Fault injected | Verifies |
|--------|---------------|----------|
| `kill-reader.sh <sec>` | SIGSTOP/CONT the process | watchdog + supervisor |
| `fill-queue.sh <url> <rps> <sec>` | Floods HTTP ingestion | backpressure + DLQ + rate limiter |
| `drop-packets.sh <ip> <sec>` | iptables drop to target | circuit breaker + retry backoff |
| `corrupt-msg.py --iterations N` | Malformed HL7 payload | escape + validator + no crash |

## Pre-flight checklist

```bash
# Baseline healthy metrics before chaos
curl -s http://127.0.0.1:8080/metrics | grep -E "up|queue"

# Enable JSON logs during chaos so you can grep by field
export LOG_FORMAT=json
```

## Post-mortem template per run

- Fault:
- Duration:
- Observed behavior:
- Recovery time:
- Any DLQ entries:
- Any alerts fired:
- Fix / follow-up:

Save these under `docs/chaos-reports/YYYY-MM-DD.md`.
