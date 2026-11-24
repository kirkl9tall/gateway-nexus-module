# Total cost of ownership — 3-year TCO

Comparison for a typical Swiss/DACH group practice with **5 analyzers**
and **2 clinic sites**.

## Option A — JerumedNexus Gateway

| Item | One-time | Yr 1 | Yr 2 | Yr 3 | Total |
|------|---------:|-----:|-----:|-----:|------:|
| Hardware (2× Pi 5 8 GB + SD + case + PSU) | CHF 320 | — | — | — | 320 |
| Setup & installation (2× on-site half-day) | 1 200 | — | — | — | 1 200 |
| Software licence (Standard tier per site × 2) | — | 2 400 | 2 400 | 2 400 | 7 200 |
| Support (Standard, 8×5, 1 BD SLA) | included | — | — | — | 0 |
| Backups (existing NAS, no extra cost) | — | — | — | — | 0 |
| Training (2× 2h, all staff) | 400 | — | — | — | 400 |
| **Total** | **1 920** | **2 400** | **2 400** | **2 400** | **CHF 9 120** |

## Option B — Competing vendor (Instrument Manager class)

| Item | One-time | Yr 1 | Yr 2 | Yr 3 | Total |
|------|---------:|-----:|-----:|-----:|------:|
| Vendor server (2× Windows small server) | 6 000 | — | — | — | 6 000 |
| Windows licence + AV + patching | — | 900 | 900 | 900 | 2 700 |
| Integration project (per-device, 5 devices × 2 sites) | 24 000 | — | — | — | 24 000 |
| Annual maintenance (18% of one-time) | — | 5 400 | 5 400 | 5 400 | 16 200 |
| Support (business hours) | — | 2 400 | 2 400 | 2 400 | 7 200 |
| Backup software | 1 500 | 300 | 300 | 300 | 2 400 |
| Training | 1 200 | — | — | — | 1 200 |
| **Total** | **32 700** | **9 000** | **9 000** | **9 000** | **CHF 59 700** |

## Delta

**JerumedNexus 3-year TCO is ~85 % lower** for the same clinical value:

- Same 5 analyzers integrated end-to-end.
- Same HL7 v2.5 + FHIR R4 output to any LIS.
- Same audit + backup + retention.
- **Better**: nDSG data-residency guarantee (data never leaves the Pi),
  edge deployment (no dependence on central server), Web UI is open by
  design (no per-seat licence).

## Beyond direct cost

| Factor | Competitor server | JerumedNexus Pi |
|--------|-------------------|-----------------|
| Rack space | 2× 1U per site | 0 (Pi on shelf) |
| Power draw | ~180 W per server | ~5 W per Pi |
| Failure blast radius | site-wide | one Pi affects one exam room |
| Time to add a device | 3–6 weeks project | 15 min (YAML profile) |
| Time to migrate to a new LIS | 4–8 weeks | edit outputs section, restart |

## Ask us for a written quote

Prices above are indicative and vary by clinic size. Contact
**sales@jerumednexus.example** for a per-site written quote signed under
the [DPA template](../regulatory/DPA-TEMPLATE.md).
