# Data Processing Agreement (Template)

**Fill in with your Quality Manager and legal counsel before signing.**

**Between:**

- **Controller** ("Practice"): _____________________________________
- **Processor** ("Vendor"): Jerumed Nexus GmbH (or your legal entity)

Concerning the JerumedNexus Gateway software deployed at the Practice.

---

## 1. Subject and duration

The Vendor processes personal data on behalf of the Controller to convert
laboratory analyzer results into HL7 v2.5 messages and forward them to the
practice's PIS/LIS. The agreement runs for as long as the software is
installed at the Practice and until the last log is purged.

## 2. Nature of data processed

| Category | Fields | Purpose |
|----------|--------|---------|
| Patient identifier | patient_id, sample_id, name (optional) | Message routing |
| Health data | analyte results, reference ranges, abnormal flags | Message payload |
| Operational | timestamps, service actions, admin logins | Audit, support |

Sensitive categories under nDSG Art. 5(c) / GDPR Art. 9 are involved.

## 3. Data location

All processing happens **on the Raspberry Pi at the Practice**. No patient
data is transmitted to the Vendor. Support is performed via read-only log
excerpts the Practice provides voluntarily.

## 4. Sub-processors

None by default. If remote support tools (e.g. TeamViewer) are used, they
require explicit Practice consent and are listed here:

- _____________________________________

## 5. Technical & organisational measures

- Web UI protected by bcrypt password, 12-char minimum, CSRF, rate limiting.
- HTTP ingestion protected by Bearer token (>= 32 char random).
- Patient identifiers hashed in audit logs.
- systemd hardening: dedicated user, `NoNewPrivileges`, `ProtectSystem=strict`.
- Log retention: 90 days by default. Configurable in `gateway.yaml`.
- Backups: the Practice's responsibility (config + `logs/` folder).

## 6. Breach notification

Vendor notifies the Practice within **72 hours** of becoming aware of any
personal data breach affecting the gateway. Practice is responsible for
subsequent notifications to the FDPIC (nDSG Art. 24) or supervisory
authority (GDPR Art. 33).

## 7. Data subject rights

The Practice remains the data controller. Requests for access, rectification
or erasure are handled by the Practice using the standard support channels
of the PIS/LIS -- the gateway itself only holds transient audit logs.

## 8. Return / deletion at end of contract

On termination, the Vendor removes any support access. The Practice deletes
the gateway data from `/opt/jerumednexus/logs/` and revokes the license.

## 9. Audit

Practice may request evidence of technical measures (release notes,
`SECURITY.md`, ISO/IVDR documentation) once per year. On-site audits are
possible with 30 days notice at the Practice's expense.

## Signatures

Controller:  _______________________  Date: __________

Processor:   _______________________  Date: __________
