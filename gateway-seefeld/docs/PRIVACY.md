# Privacy & data protection

**Compliance target: Swiss nDSG (LPD) + EU GDPR + IVDR Annex I.**
This document is the authoritative map of *what the gateway stores about
patients, where, and how long*. Show it to your DPO.

## Data categories processed

| Category | Fields | Legal basis (nDSG art. / GDPR art.) |
|----------|--------|-------------------------------------|
| Patient identifier | patient_id, sample_id, patient_name (optional) | processing on behalf of controller (nDSG art. 9 / GDPR art. 28) |
| Health data | analyte code + value + unit + reference range + abnormal flag | same |
| Operational | login events, service actions, admin identities | legitimate interest (auditability) |

All processing happens **on the Raspberry Pi at the clinic**. **No patient
data is ever transmitted to the vendor.** Support requires the clinic to
provide log excerpts voluntarily.

## Where data lives

| Location | Contents | Persistence |
|----------|----------|-------------|
| `logs/history.db` (SQLite) | dispatch history: patient_id + sample_id + status + targets | retention.history_days (90 default) |
| `logs/dead_letter/*.hl7[.enc]` | **full HL7 body** (all analytes + patient info) | retention.dlq_days (30 default). **Encrypted at rest (Fernet/AES-128)** by default. |
| `logs/dead_letter/*.meta.json` | error context, sample_id, targets | same as body |
| `logs/orders/*.json` | bidirectional orders received from LIS | retention.orders_days (7) |
| `logs/status.json` | rolling window of last 500 dispatches (patient_id in clear) | in-memory + periodic snapshot; wiped on restart |
| `logs/seen_samples.json` | dedup cache: sample_id + timestamp | retention.seen_samples_days (7) |
| `logs/audit.jsonl` | login/config events; **patient_id/sample_id HASHED** | retention.audit_days (730) — 2 years for regulatory |
| `logs/gateway.log` | operational log; **patient_id HASHED by default** | retention.gateway_log_days (30) + logrotate |

## Encryption at rest

- **DLQ**: encrypted with Fernet (AES-128-CBC + HMAC-SHA-256). Key at
  `config/dlq_key` (mode 600, owner `jerumednexus`). Turn off with
  `dlq_encryption_enabled: false` in `gateway.yaml` (not recommended).
- **history.db, orders, status.json**: **not encrypted at rest** — protected
  by filesystem permissions (owner `jerumednexus`, group-none). For
  additional protection use full-disk LUKS on the SD card.
- **Backups**: use `scripts/backup.sh --gpg-recipient <keyid>` to encrypt
  the archive before it leaves the Pi.

## Retention policy

Configurable in `gateway.yaml`:

```yaml
retention:
  history_days:      90        # SQLite dispatches
  dlq_days:          30        # dead-letter files
  orders_days:       7         # unprocessed orders
  gateway_log_days:  30        # gateway.log.N (rotated)
  audit_days:        730       # audit.jsonl.N -- 2 years
  seen_samples_days: 7         # dedup cache
```

A background worker runs **once per day** (24h after start) and deletes
data older than the configured window. Setting a value to `0` disables
purge for that category (indefinite retention — only for exceptional
compliance requirements).

## PII in logs

`gateway.log` used to write `sample=PAT-42` in clear.
**Since v1.2** the root logger has a PII filter that hashes:
- `patient_id`, `sample_id`, `patient_name`
- HL7 PID segment content

To disable for debug (**never in production**):
```
LOG_PII=1 sudo systemctl restart jerumednexus-gateway
```

Audit log has always hashed patient IDs.

## Patient rights fulfilment

### Right to access (nDSG art. 25 / GDPR art. 15)

```bash
sudo -u jerumednexus jerumednexus patient export PAT-42 --out patient42.json
```
Or via Web UI (admin): `GET /api/patient/PAT-42/export`

Produces a JSON with **every** trace found for that patient across all
stores. Give this file to the patient (or their attorney) within 30 days
of request.

### Right to erasure (nDSG art. 25 / GDPR art. 17)

```bash
sudo -u jerumednexus jerumednexus patient purge PAT-42
```
Or via Web UI: `POST /api/patient/PAT-42/purge` (body must include
`{"confirm": "PAT-42"}` as safety).

The command prints how many records would be deleted and asks for `YES`
confirmation before proceeding. **Cannot be undone.** Audit log records
the operation with the operator identity.

### What survives a purge

- Audit log entries are **hashed** — the patient is no longer identifiable
  from them, but the hash remains. This is compatible with GDPR (art. 17(3)(b)
  legal obligation to keep audit records).
- Rotated `gateway.log.N` may still contain the hashed identifier only —
  no clear-text patient info.
- Backups written to NAS **before** the purge are outside the gateway's
  reach. The controller (clinic) must purge those separately.

## Backup security

```bash
sudo /opt/jerumednexus/scripts/backup.sh /mnt/nas/jerumednexus \
    --gpg-recipient backup@clinic.example --keep 30
```

Without `--gpg-recipient`, backups are **plaintext tar.gz** — the script
warns loudly. Only use plaintext for local testing.

## Data processor obligations (nDSG art. 9 / GDPR art. 28)

The Vendor (Jerumed Nexus GmbH) acts as **processor** on behalf of the
Controller (the clinic). Obligations:

- Process only on documented instructions (the `gateway.yaml` config)
- Ensure staff are bound by confidentiality (BYOD, MDM policy)
- Implement TOMs (technical & organisational measures) — this document
- Assist with data subject requests (this document + CLI commands above)
- Notify the Controller of any personal data breach within 72 hours
- Delete or return data on contract termination (see DPA)

Full template at [docs/regulatory/DPA-TEMPLATE.md](regulatory/DPA-TEMPLATE.md).

## Breach notification

If you detect unauthorised access to any of the paths listed above:

1. **Preserve evidence**: do not delete logs; snapshot the SD card.
2. **Notify the Controller** (clinic) within 24h — even if you're not sure
   yet whether it's a breach.
3. **Together with the Controller, notify the FDPIC** (Swiss Federal Data
   Protection and Information Commissioner) or the local supervisory
   authority within 72h if patient data may have been accessed.
4. **Document** in `docs/incidents/YYYY-MM-DD-breach.md` with a template.

## Verification

Audit that the privacy controls work:

```bash
# 1. Verify DLQ files are encrypted
head -c 5 logs/dead_letter/*.hl7.enc | xxd
# Expected: 46 52 4e 54 31 = "FRNT1"

# 2. Verify audit log hashes IDs
grep "patient_id" logs/audit.jsonl | head -1
# Expected: {"detail":{"patient_id":"a1b2c3d4e5f6a7b8", ...}}

# 3. Test retention (with a dry period of 1 day, then verify old data gone)
# temporarily set retention.history_days: 1 in gateway.yaml, wait, check DB
```
