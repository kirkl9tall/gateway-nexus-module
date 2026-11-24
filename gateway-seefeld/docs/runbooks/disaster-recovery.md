# Runbook — Disaster recovery

**When to use:** the Pi is lost (theft, hardware failure, SD-card
corruption, ransomware, fire, flood). Goal: get a replacement Pi
running with the same configuration and history, minimizing patient-
data loss.

**Recovery time objective (RTO):** 2 hours from decision to restore.
**Recovery point objective (RPO):** 24 hours (nightly backup cadence).

## Prerequisites

- Latest backup archive (`.tar.gz.gpg` or `.tar.gz`) reachable.
- Private GPG key to decrypt (for encrypted backups).
- A blank Raspberry Pi 4 or 5, SD card ≥ 32 GB, Ethernet.

## Step 1 — Preserve evidence (if security incident)

If loss is suspected to be an attack (ransomware note, unauthorized
access), do **not** wipe the old SD card. Copy it bit-for-bit with
`dd` to an external drive first and log the timestamp. See also
[docs/PRIVACY.md](../PRIVACY.md) §Breach notification.

## Step 2 — Provision the replacement Pi

```bash
# Flash the base image (matches production distro)
sudo rpi-imager --cli --device /dev/sdb --os raspios-lite-arm64.img

# First boot: connect Ethernet, note IP
ssh pi@<new-ip>
sudo passwd     # set root password
```

## Step 3 — Install the gateway

```bash
# Add the signed apt repo
curl -fsSL https://apt.jerumednexus.example/gpg | sudo apt-key add -
echo "deb https://apt.jerumednexus.example/ stable main" \
    | sudo tee /etc/apt/sources.list.d/jerumednexus.list
sudo apt update && sudo apt install jerumednexus-gateway
```

Do **not** enable the service yet — we restore config first.

## Step 4 — Restore from backup

```bash
# Copy the archive to the new Pi
scp jerumednexus-YYYYMMDD-HHMMSS.tar.gz.gpg pi@<new-ip>:/tmp/

# Decrypt (if encrypted)
gpg --decrypt /tmp/jerumednexus-*.tar.gz.gpg > /tmp/restore.tar.gz

# Extract into place
sudo systemctl stop jerumednexus-gateway || true
sudo tar -xzf /tmp/restore.tar.gz -C /opt/jerumednexus/ --overwrite

# Restore ownership
sudo chown -R jerumednexus:jerumednexus /opt/jerumednexus/config
sudo chown -R jerumednexus:jerumednexus /opt/jerumednexus/logs
sudo chmod 600 /opt/jerumednexus/config/dlq_key
sudo chmod 600 /opt/jerumednexus/config/secrets.env
```

## Step 5 — Reconnect devices

- Plug the RS-232 / Ethernet cables into the same physical ports as
  before (the device profiles reference `/dev/ttyUSB0` etc.).
- If the USB enumeration order changed, edit
  `config/devices/*.yaml` and update `serial_port:`.
- If the LIS IP changed, edit `config/gateway.yaml` outputs section.

## Step 6 — Start & verify

```bash
sudo systemctl enable --now jerumednexus-gateway
sudo systemctl status jerumednexus-gateway
sudo -u jerumednexus jerumednexus health
```

Expected:
- `health` returns `OK` for every enabled device (green).
- `logs/status.json` shows the restored dispatch history.
- Web UI at `http://<pi-ip>:8088/` loads and login works.
- Audit log has an entry `restore_from_backup` (add manually via CLI
  since the restore was manual).

## Step 7 — Notify

- **Clinic operator** — DR complete, service restored at `<time>`,
  RPO gap is the delta since the last backup timestamp.
- **DPO** — if the loss involved unauthorized access, follow
  [docs/PRIVACY.md](../PRIVACY.md) §Breach notification (72h to
  FDPIC / supervisory authority).

## Step 8 — Post-incident

- Document the incident in `docs/incidents/YYYY-MM-DD-<slug>.md`.
- Review whether backup cadence (RPO) or restore playbook (RTO) needs
  tightening.
- If RTO was blown, escalate to the on-call architect for a root-cause
  review.

## Testing this runbook

**Schedule a DR drill every 6 months.** Provision a test Pi from a
recent backup and confirm the checklist above works end-to-end in
under RTO. Record the drill outcome in
`docs/incidents/YYYY-MM-DD-dr-drill.md`.
