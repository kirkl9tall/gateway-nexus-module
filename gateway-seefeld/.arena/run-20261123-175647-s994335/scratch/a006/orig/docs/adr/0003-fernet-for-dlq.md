# ADR-0003 — Fernet (AES-128-CBC + HMAC-SHA-256) for DLQ encryption

- **Status:** Accepted
- **Date:** 2026-08-22
- **Deciders:** security, DPO

## Context

Dead-letter files contain full HL7 bodies — patient identifiers,
analyte values, physician notes. Even with filesystem perms, an
attacker with root or a stolen SD card reads plaintext.

Options for encryption at rest:
1. LUKS full-disk (system responsibility).
2. Application-level Fernet.
3. Application-level libsodium `secretbox`.
4. Age.

## Decision

**Fernet from the `cryptography` package**, key at `config/dlq_key`
(mode 600, owner `jerumednexus`). Encrypted files carry a
`b"FRNT1"` magic header so we can decrypt legacy plaintext on read
without renaming files.

## Consequences

- Positive: standard, audited primitive; single library (`cryptography`)
  already a dep; key rotation is a one-liner.
- Positive: doesn't preclude LUKS — clinics wanting defense in depth
  turn on both.
- Negative: 5–10% write throughput cost, negligible at this rate.
- Rejected libsodium: extra dependency without a security win at 128-bit.
- Rejected LUKS-only: doesn't help when the OS is running (an
  attacker with a shell reads the DLQ). Fernet does.
