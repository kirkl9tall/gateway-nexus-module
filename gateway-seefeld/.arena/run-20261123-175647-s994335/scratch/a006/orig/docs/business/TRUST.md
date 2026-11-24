# Trust & transparency

Vendor: **Jerumed Nexus GmbH**, CH-6300 Zug.

## Compliance status

| Framework | Status | Evidence |
|-----------|--------|----------|
| Swiss nDSG (LPD) | Compliant by design | [docs/PRIVACY.md](../PRIVACY.md) + DPA template |
| EU GDPR | Compliant as processor | [docs/PRIVACY.md](../PRIVACY.md) + Art. 28 template |
| IVDR Annex I (Class A) | Fascicolo tecnico in preparation | Not yet CE marked |
| ISO 13485 (QMS) | Partner-manufactured, gap-assessed | Roadmap H2 2026 |
| ISO 14971 (risk mgmt) | Risk file maintained | [docs/regulatory/RISK-FILE.md](../regulatory/RISK-FILE.md) |
| ISO 27001 (ISMS) | Aligned, not certified | Roadmap 2027 |
| SOC 2 Type I | Not applicable (vendor doesn't host data) | — |

## What the vendor never sees

- No patient identifier, sample identifier, analyte value.
- No credentials (LDAP/OIDC bind to your IdP directly).
- No logs by default (support bundle is opt-in per incident).

**Every byte of patient data stays on the Pi in the clinic**. Support
sessions happen over WireGuard with a short-lived certificate you
issue; every session is logged in your audit log.

## Public status

- [status.jerumednexus.example](https://status.jerumednexus.example) —
  historical uptime, incidents timeline, RCA post-mortems.
- [github.com/jerumed-nexus](https://github.com/jerumed-nexus) —
  open-source repositories, signed releases.
- [security.txt](https://jerumednexus.example/.well-known/security.txt) —
  disclosure address + PGP.

## Third-party audits

_(Fill in as they happen.)_

- 2026-Q4 — external penetration test (planned).
- 2027-Q2 — SBOM + supply-chain audit (planned).
- 2027-Q4 — ISO 13485 pre-audit.

## Sub-processor list

The following third parties may process **operational data only** (never
patient data):

| Sub-processor | Purpose | Data class | Location |
|---------------|---------|------------|----------|
| GitHub (Microsoft) | Source control, issue tracking | code, config templates | EU/US |
| Cloudflare | DNS, TLS termination for `docs.jerumednexus.example` | none | Global |
| Fastmail | Corporate email | operational | AU/EU |

If you require a full DPA including sub-processor list, contact
`legal@jerumednexus.example`.
