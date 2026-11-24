# Support

## Support tiers

| Tier | Audience | Response SLA | Channels |
|------|----------|--------------|----------|
| **Community** | Any user | Best-effort | GitHub Discussions, `docs/FAQ.md` |
| **Standard**  | Paid license | 1 business day, 8×5 | Email `support@jerumednexus.example`, ticketing portal |
| **Enterprise** | Contracted clinics/labs | 4h business hours + 24×7 on-call | Standard + phone hotline + named CSM |

## Severity levels & response times (Enterprise)

| Severity | Definition | Initial response | Workaround | Fix |
|----------|------------|------------------|------------|-----|
| S1 — Critical | Gateway down, no results reach LIS, patient safety impact | 30 min | 4 h | 24 h |
| S2 — High     | Single device blocked, DLQ growing, degraded output | 2 h | 1 business day | 5 business days |
| S3 — Medium   | Non-blocking bug, cosmetic UI, docs error | 1 business day | Next release | Next release |
| S4 — Low      | Feature request, question | 3 business days | n/a | Roadmap discussion |

## Escalation matrix

1. **L1 — Clinic sysadmin** (owns the Pi hardware, filesystem, network).
2. **L2 — Vendor support engineer** (triage, remote diagnosis via
   `jerumednexus support-bundle` output).
3. **L3 — Core engineering** (patch author, protocol expertise).
4. **L4 — On-call architect** (data integrity, security incident).

Escalation to next tier happens automatically at 2× the tier SLA.

## Before opening a ticket

Please gather and attach:

```bash
sudo -u jerumednexus jerumednexus support-bundle --out bundle.tar.gz
```

The support bundle includes: `journalctl -u jerumednexus-gateway` (last
24h), `gateway.log`, `audit.jsonl` (redacted), `status.json`, breaker
state, discovered devices, list of enabled adapters. Patient data is
already hashed by the PII filter — safe to email.

## Business hours

- **CET / CEST** — Monday–Friday, 08:00–18:00.
- **On-call (Enterprise)** — 24×7 for S1/S2 incidents.

## Documentation

Read first:

- [Getting started](docs/getting-started.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [FAQ](docs/FAQ.md)
- [Runbooks](docs/runbooks/) — incident-specific step-by-steps.
