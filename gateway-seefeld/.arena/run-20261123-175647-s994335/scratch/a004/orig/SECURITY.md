# Security Policy

## Supported versions

We accept security reports for the following versions of JerumedNexus Gateway:

| Version | Supported |
|---------|-----------|
| 1.3.x   | :white_check_mark: |
| 1.2.x   | :white_check_mark: (patches until 2026-12-31) |
| < 1.2   | :x: |

## Reporting a vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, email **security@jerumednexus.example** (PGP key
`0x4A5B6C7D8E9F0A1B` — publish at first release).

We commit to:

| Step | Target time |
|------|-------------|
| Acknowledge receipt | ≤ 48 hours |
| Initial assessment (severity, in-scope confirmation) | ≤ 5 business days |
| Coordinated fix + advisory | ≤ 90 days (CVSS < 9), ≤ 30 days (CVSS ≥ 9) |
| Public disclosure | After a patched release is available |

## Scope

**In scope:**
- The gateway process, adapters, web UI, licensing, and the update flow.
- The `.deb` package and Docker image publishing pipeline.
- Documented deployment topologies on Raspberry Pi 4/5.

**Out of scope:**
- Third-party analyzer firmware (report to vendor).
- Denial of service against a single Pi via unlimited malformed frames
  from a device on the local wire (mitigated by rate limiter + DLQ; new
  DoS surfaces are welcome as reports).
- Social-engineering of the clinic's operator.

## What we consider a vulnerability

- Remote code execution, privilege escalation, authentication bypass.
- Reading/writing patient data without the required role.
- Persistent injection into HL7/FHIR output that could mislead the LIS.
- Cryptographic mistakes in Fernet DLQ encryption or GPG backups.
- Any leak of `config/dlq_key`, `config/secrets.env`, or license
  private keys.

## Coordinated disclosure

We follow the **90-day industry-standard** disclosure window. If we
cannot ship a fix within 90 days, we will negotiate an extension with
the reporter. Reports that result in a CVE will credit the researcher
by name (or handle) in the release notes.

## Hall of fame

_(Reporters who responsibly disclosed will be listed here.)_
