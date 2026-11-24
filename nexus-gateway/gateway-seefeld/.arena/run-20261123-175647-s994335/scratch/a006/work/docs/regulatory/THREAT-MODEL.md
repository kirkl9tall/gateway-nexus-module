# Threat model — JerumedNexus Gateway

**Method:** STRIDE, applied per trust boundary.
**Scope:** the gateway running on a Raspberry Pi in a Swiss/DACH clinic,
its local devices, its LIS/HIS output, its update channel, its backup
target, and its remote support channel.
**Owner:** security team.
**Review cadence:** every minor release + on architectural change.

---

## 1. System diagram (verbal)

```
[Analyzer serial/TCP]  →  [Adapter]  →  [Router/DLQ]  →  [HL7 builder]  →  [LIS/HIS]
                                 ↕
                          [SQLite history]
                                 ↕
                          [Web UI + Auth]   →   [Admin browser]
                                 ↕
                          [Backup script]   →   [NAS / off-site]
                                 ↕
                          [Update channel]  ←   [APT repo + cosign]
```

## 2. Trust boundaries

- **B1** — Serial/RS-232 bus between the analyzer and the Pi.
- **B2** — Local network (Pi ↔ LIS, Pi ↔ admin browser).
- **B3** — Filesystem of the Pi (root, `jerumednexus` user, others).
- **B4** — Backup destination (NAS or cloud).
- **B5** — Update channel (APT repo, HTTPS, GPG signatures).
- **B6** — Remote support channel (SSH/VPN or WireGuard).

## 3. STRIDE table

| Boundary | Category | Threat | Impact | Mitigation |
|----------|----------|--------|--------|------------|
| B1 | Spoofing | Rogue device on the serial bus | Fake results | Physical access control; frames are matched to a configured device_id; unknown IDs go to DLQ |
| B1 | Tampering | Malformed frame → parser crash / RCE | DoS / RCE | Buffer guard (`guard_buffer`), regex parse only, `Hypothesis` fuzz suite, `MAX_FRAME_BYTES` cap |
| B1 | Info disclosure | Serial cable tap | Patient results leak | Bus is inside the clinic; physical control |
| B2 | Spoofing | Rogue LIS receiver | Results sent to wrong destination | LIS receiver pinned by IP + optional mTLS; MSH-4/6 placeholder warnings |
| B2 | Tampering | MITM on LIS wire | Result modification | HL7 over TLS recommended; audit log records what was sent |
| B2 | Repudiation | Admin denies making a config change | Compliance gap | Audit log (`audit.jsonl`) records operator identity + hashed patient IDs; 2-year retention |
| B2 | Info disclosure | Web UI leaks patient data to non-admin | Privacy breach | RBAC (viewer / operator / admin); TOTP for admin; OIDC/LDAP options |
| B2 | DoS | Broadcast storm from analyzer | DLQ overflow | Rate limiter + circuit breaker + DLQ with retention purge |
| B2 | Elevation | Web UI CSRF / XSS | Admin takeover | CSP header, CSRF token, escaped Jinja, no `eval`, Playwright tests for auth flows |
| B3 | Info disclosure | Unauthorized read of DLQ files | Full HL7 leak | Fernet AES-128 encryption at rest, key mode 600 owner `jerumednexus` |
| B3 | Tampering | Attacker with local access alters `history.db` | Wrong result history | Filesystem perms; audit log is append-only + hashed; recommend LUKS on SD card |
| B3 | Elevation | Service running as root | Full compromise | systemd unit runs as `jerumednexus`, `NoNewPrivileges`, `ProtectHome`, `ProtectSystem=strict`, read-only paths |
| B4 | Info disclosure | Backup on NAS read by other clinics | Cross-tenant leak | `--gpg-recipient` required for prod; script warns if plaintext |
| B4 | Tampering | Attacker restores a doctored backup | Wrong data | Restore procedure requires operator confirmation + audit entry |
| B5 | Spoofing | Malicious APT repo | Trojan update | GPG-signed `.deb` via `debsigs`; cosign-signed Docker; APT pin |
| B5 | Tampering | Update in transit modified | Trojan update | HTTPS + GPG signature verification |
| B6 | Elevation | Support engineer with wrong scope | Data access without patient consent | Support access via WireGuard with clinic-issued short-lived cert; every session logged; consent required per SLA |

## 4. Assumptions

- The Pi is inside a physically controlled clinic room.
- The clinic sysadmin controls SSH keys / physical access.
- The LIS/HIS is trusted infrastructure the clinic already operates.
- Analyzer firmware is trusted (vulnerabilities in device firmware are
  outside scope; we notify the vendor).

## 5. Non-mitigations (accepted risk, documented)

- **Compromised SD card imaged offline** — LUKS is recommended but not
  enforced. Accepted risk: clinic sysadmin's responsibility.
- **Analyzer sends numerically wrong result** — the gateway forwards
  what the device says. Sanity range checks flag but do not reject.
  Accepted risk: the clinician interprets the result.

## 6. Recommended next steps

- External pentest before v2.0 (see [SUPPORT.md](../../SUPPORT.md)).
- SBOM signing with cosign attest (partially done — extend to source
  archive).
- Runtime attestation via TPM on Pi 5 (roadmap).
