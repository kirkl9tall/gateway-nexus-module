# Multi-region backup (ransomware-proof)

The nightly GPG-encrypted backup can be pushed to **two independent
destinations** with **object-lock retention**. This protects against
ransomware that also encrypts the NAS.

## Recommended pattern

```yaml
# gateway.yaml
backup:
  gpg_recipient: "backup@clinic.example"
  keep_local_days: 14
  destinations:
    - kind: nas
      path: /mnt/nas/jerumednexus
      keep_days: 30
    - kind: s3
      endpoint: "https://s3.eu-central-1.amazonaws.com"
      bucket: "clinic-jerumednexus-backups"
      prefix: "zurich-01/"
      object_lock: {mode: GOVERNANCE, days: 90}
      credentials_env: BACKUP_S3_CREDENTIALS
```

## Why two destinations

- **Local NAS** — fast restore for the common case (SD dead, human error).
  Fast RPO/RTO, but on the clinic LAN — same blast radius as
  ransomware.
- **Immutable object store** — S3 with Object-Lock in `GOVERNANCE` or
  `COMPLIANCE` mode, or Backblaze B2 with equivalent. Even the vendor
  admin cannot delete an object before the retention window ends.
  Slow to restore, but survives the worst case.

## Providers vetted

| Provider | EU region | Object-lock | Notes |
|----------|-----------|-------------|-------|
| AWS S3 | eu-central-1, eu-west-3, eu-south-1 | Yes | Well-understood, most expensive. |
| Backblaze B2 | eu-central-002 | Yes (Object Lock) | Cheapest per GB. |
| Wasabi | eu-central-1 | Yes | Flat-rate, no egress fee. |
| Cubbit | Italy | Yes | Fully-EU-jurisdictional. Recommended for it/ch clinics. |
| OVHcloud Cold Archive | France, Germany | Yes | Deep archive; slow restore. |

## Encryption chain

1. Local: tar.gz + GPG asymmetric encryption to the clinic's recipient.
2. In transit: TLS to the object store.
3. At rest in the bucket: server-side encryption with AWS KMS (or
   equivalent) — the vendor never touches the KMS key.

The clinic's private GPG key is the only way to decrypt. Store it in
a physical safe + a copy at the DPO's residence. Losing it means the
backups are unreadable — this is by design.

## Restore drill

Schedule a monthly restore from **the S3 leg** into a scratch Pi:

```bash
aws s3 cp s3://clinic-jerumednexus-backups/zurich-01/latest.tar.gz.gpg \
    /tmp/restore.tar.gz.gpg
sudo /opt/jerumednexus/scripts/verify_backup.sh /tmp/ <keyid>
```

Fail loudly to `syslog` + email if the check does not return `OK`.
