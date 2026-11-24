# Fleet management — running many Pis

For deployments beyond ~10 clinics, a manual per-Pi workflow does not
scale. The vendor operates a **Fleet Management Console** (SaaS or
on-prem) that talks to each Pi over WireGuard for:

- **Health telemetry** — the same `/readyz` payload each Pi already
  emits, aggregated. Green / yellow / red per site, with 30-day
  history.
- **Version rollout** — pinned per site (canary → staging → prod) with
  automatic rollback on a spike in `E2xxx` / `E3xxx` errors.
- **Config drift alerts** — when someone edits `gateway.yaml` locally,
  the console shows the diff against the last approved template.
- **Support-bundle collection** — one click to request a support
  bundle; the Pi builds and pushes it over the same tunnel.

## Trust model

- The console **cannot** read patient data. It only sees:
  hashed sample IDs (via the audit log JSON structure), error codes
  from the `E1xxx…E9xxx` taxonomy, and `/readyz` payloads.
- The tunnel is **outbound-only** from the Pi (no port exposed).
- Each Pi rotates its WireGuard key every 30 days.
- Every console-initiated action is written to the Pi's audit log
  with actor = `fleet-console/<engineer-username>`.

## Deployment topology

```
                                  ┌──────────────┐
                                  │  Fleet UI    │
                                  │  (SaaS/on-p) │
                                  └──────┬───────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
              WireGuard ⇄        WireGuard ⇄           WireGuard ⇄
                    │                    │                    │
        ┌───────────▼───┐    ┌───────────▼───┐    ┌───────────▼───┐
        │ Clinic ZH Pi  │    │ Clinic LU Pi  │    │ Clinic BS Pi  │
        └───────────────┘    └───────────────┘    └───────────────┘
```

## Alternative: pull-based

Clinics that reject any outbound tunnel can instead run:

```bash
jerumednexus fleet-report --emit=json > /tmp/report.json
```

on a cron, and rsync the report to a NAS the vendor reads via a
scoped shared credential. Same information, no tunnel.

## Roadmap

| Version | Feature |
|---------|---------|
| 1.4 | Read-only console (view only) |
| 1.5 | Rollout orchestration (canary + rollback) |
| 1.6 | Bulk config template push |
| 2.0 | Multi-tenant SaaS with per-vendor isolation |
