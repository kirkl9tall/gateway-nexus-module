# Ansible rollout

Deploy the JerumedNexus Gateway `.deb` to a fleet of Raspberry Pis in one command.

## Prerequisites

- Ansible ≥ 2.14 on your workstation (`pipx install ansible-core`)
- `community.general` collection: `ansible-galaxy collection install community.general`
- SSH access with `sudo` to every target Pi
- A built `.deb` (run `scripts/build-deb.sh` and copy the artifact into
  `deploy/ansible/files/jerumednexus-gateway.deb`)

## Quick start

```bash
cp inventory.example.ini inventory.ini
cp vars.example.yml       vars.yml
ansible-vault encrypt vars.yml

# Edit inventory.ini + vars.yml
ansible-playbook -i inventory.ini site.yml -e "@vars.yml" --ask-vault-pass
```

## Target-specific overrides

Use group_vars/ or host_vars/ directories, e.g.

```
host_vars/praxis-zurich.yml
    facility_name: "Praxis Dr. Meier Zurich"
    http_token: "…"
```

## Idempotence

The playbook is idempotent:

- `.deb` install is a no-op when already at the same version.
- Password is only seeded on first install (uses `creates:` on the
  hash file).
- Systemd services are `state: started` (not `restarted`) — only the
  restart handler triggers a restart, and only when a task notifies it.

## What lands where

| Path | Purpose |
|------|---------|
| `/opt/jerumednexus/` | Application code |
| `/opt/jerumednexus/config/gateway.yaml` | Main config |
| `/opt/jerumednexus/config/secrets.env` | HTTP token + SFTP creds (mode 600) |
| `/opt/jerumednexus/config/webui_password.hash` | bcrypt admin hash |
| `/var/log/jerumednexus/` | Rotated logs |
| `/var/lib/jerumednexus/` | State (`seen_samples.json`, `discovered.json`) |
