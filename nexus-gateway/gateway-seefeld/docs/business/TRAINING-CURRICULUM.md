# Training curriculum

Four role-based modules, each with lecture + hands-on lab + assessment.
Successful completion of the operator + admin modules qualifies the
holder for the **JerumedNexus Certified Operator** badge, renewed every
2 years.

## Module 1 — Setup (0.5 day, sysadmin)

**Audience:** clinic IT / MSP staff.

**Learning objectives**
- Provision a Pi from image + apt repo.
- Wire an analyzer (serial + Ethernet) and confirm the wizard sees it.
- Configure one LIS output.
- Read the audit log and answer "who changed what, when".

**Lab**
1. Fresh install on a Pi (image already flashed).
2. Add Sysmex XQ-320 via wizard.
3. Configure `mllp_hl7` LIS output pointing at a demo receiver.
4. Trigger a test frame; confirm it landed.

**Assessment**: 10-question multiple choice (80% to pass).

## Module 2 — Operator (0.5 day, lab staff / MPA)

**Audience:** medical practice assistants who run daily lab work.

**Objectives**
- Read the Web UI status page.
- Retry a failed dispatch from the DLQ.
- Use `patient export` and `patient purge` (rights fulfilment).
- Escalate correctly when a device is red.

**Lab**
1. Trigger a failure (unplug LIS network cable), confirm DLQ grows.
2. Reconnect; retry from DLQ.
3. Run `export` and `purge` on a test patient.
4. Read `/readyz` output and identify the failing subsystem.

**Assessment**: written scenario with graded response.

## Module 3 — Admin (1 day, senior sysadmin or DPO)

**Audience:** the person responsible under nDSG/GDPR.

**Objectives**
- Understand the retention & PII hashing model.
- Rotate the DLQ key and re-encrypt existing DLQ.
- Perform a full DR drill from a backup.
- Configure OIDC / LDAP / TOTP.
- Read Prometheus alerts + the Grafana dashboard.

**Lab**
1. Rotate DLQ key.
2. Restore a backup to a fresh Pi (RTO target 2h).
3. Wire OIDC against a test IdP.
4. Trigger a chaos scenario (kill DLQ writer) and verify recovery.

**Assessment**: proctored DR-drill walkthrough.

## Module 4 — Developer (2 days, integrator)

**Audience:** vendor engineers or partner integrators.

**Objectives**
- Add a new device profile via YAML.
- Write a new adapter (subclass of `Reader`).
- Extend the golden-file test suite.
- Cut a release (semver, changelog, signed .deb).

**Lab**
1. Add a new speculative device with a mock frame.
2. Write a parser + property test.
3. Land a PR under CODEOWNERS review.
4. Cut a `1.4.0-rc.1` release from a branch.

**Assessment**: PR merged after code review.

## Certification & renewal

- **Operator** — Module 1 + 2 → renewal every 2 years (self-paced).
- **Admin** — Module 1 + 2 + 3 → renewal every 2 years (proctored).
- **Certified Integrator** — all 4 → renewal every 3 years.

Records kept in `docs/business/certifications-<year>.md` per the
Vendor's ISO 13485-aligned training procedure.
