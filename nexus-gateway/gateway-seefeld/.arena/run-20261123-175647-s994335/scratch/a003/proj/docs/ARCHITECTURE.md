# Architecture

## System overview

```
     ┌───────────────────────────────────────────────────────────────┐
     │                      Raspberry Pi 4 / 5                       │
     │                                                               │
     │  ┌──────────────┐   ┌─────────────┐   ┌──────────────────┐    │
     │  │  loc200-     │   │             │   │   loc200-        │    │
LOC-200│  │  gateway    │   │  asyncio    │   │   webui          │    │
──────>│  │  (systemd)  ├─> │  Queue      ├─> │   Flask :8080    │<───┤ Admin
       │  │   main.py   │   │  maxsize=500│   │   /setup /login  │    │ browser
       │  └──────┬──────┘   └─────────────┘   │   /metrics       │    │
       │         │                            │   /api/devices/* │    │
       │         │  fan-out                   └────────┬─────────┘    │
       │         v                                     │              │
       │  ┌───────────────────────┐                    │ reads        │
       │  │  Dispatcher           │                    v              │
       │  │  - MLLP TCP           │            logs/status.json       │
       │  │  - File-drop atomic   │            logs/health.json       │
       │  │  - SFTP (Tomedo)      │            logs/discovered.json   │
       │  │  - retry+backoff      │            logs/audit.jsonl       │
       │  │  - ACK correlation    │                                   │
       │  └─────┬────┬────┬───────┘                                   │
       │        │    │    │                                           │
       └────────┼────┼────┼───────────────────────────────────────────┘
                v    v    v
            Vitomed / Aeskulap / WinMed / Tomedo …
```

## Process model

Two long-running systemd services:

| Service | User | Purpose |
|---------|------|---------|
| `jerumednexus-gateway.service` | `loc200` | Runs `main.py`. Owns the asyncio queue, the readers, the dispatcher. Writes `logs/status.json` and `logs/health.json`. |
| `jerumednexus-webui.service`   | `loc200` | Runs the Flask app. Serves the UI + REST API. Reads `status.json`, writes to `config/gateway.yaml` and `logs/audit.jsonl`. |

They communicate through the filesystem (JSON state files) — no shared
memory, no in-process coupling. A restart of the Web UI never disrupts the
gateway itself.

## Data flow

1. **Readers** (`src/adapters/*`) accept analyzer input:
   - `loc200_reader` — RS-232 / TCP / WiFi / HTTP
   - `sysmex_reader` — ASTM E1381 over TCP
   - `uc1000_reader` — RS-232
   - `cobas_reader` — USB CDC serial
   - `mllp_reader` — generic HL7 v2 MLLP
2. Each reader parses raw bytes into a **normalised result dict** and puts
   it on the shared `asyncio.Queue`.
3. The **worker** dedupes (by `device:sample_id`, 24h TTL) and invokes the
   builder.
4. The **HL7 builder** (`src/hl7/builder.py`) produces an ORU^R01 message
   with correct escaping, encoding, LOINC codes and TZ-aware timestamps.
5. The **dispatcher** (`src/transport/dispatcher.py`) fans out to every
   enabled target concurrently with retry+backoff and ACK correlation.
6. Success / failure is written to `logs/audit.jsonl` and reflected in
   `logs/status.json`.

## Plug-and-play discovery

```
udev event  ->  systemd oneshot  ->  POST /api/devices/notify_added
                                        │
                                        v
                             DiscoveryService.notify_added()
                                        │
                                        v
                    probe serial (open, read 512 bytes, match fingerprint)
                                        │
                                        v
              write logs/discovered.json  (confidence 40..100)
                                        │
                                        v
                    Web UI badge counter + Analizzatori page
                                        │
                                        v
             user clicks Attiva  ->  writes config/gateway.yaml
```

TCP discovery is triggered manually from the UI (or `POST /api/devices/discover`
with `tcp_range` + `tcp_ports`).

## Security boundaries

| Boundary | Threat | Control |
|----------|--------|---------|
| Web UI login | Brute force | bcrypt (cost 12), rate limit, 12-char min |
| Web UI forms | CSRF | Double-submit token |
| Web UI session | Hijack | HttpOnly + SameSite=Lax cookie, 8h TTL |
| HTTP ingestion | Result injection | Bearer token + optional IP allowlist |
| LAN MLLP | On-path tamper | (Out of scope; use IPSec / WireGuard on untrusted LAN) |
| SFTP dispatcher | Credential leak | Loaded from `secrets.env` (mode 600), never in `gateway.yaml` |
| Update endpoint | Remote RCE | Localhost-only + CSRF |
| systemd unit | Privilege escalation | `NoNewPrivileges`, `ProtectSystem=strict`, restricted syscalls |
| Serial port | Physical tamper | Assumed trusted (physical LAN of the practice) |

## File layout

```
jerumednexus-gateway/
├── main.py                     # entry point
├── config/
│   ├── gateway.yaml            # main config (user-edited)
│   ├── gateway.yaml.example    # template
│   ├── loinc_map.yaml          # optional analyte -> LOINC overrides
│   ├── secrets.env             # 600, tokens + SFTP creds
│   ├── webui_password.hash     # bcrypt admin password
│   ├── webui_secret.key        # Flask session key (600)
│   └── devices/*.yaml          # device profile catalog
├── src/
│   ├── gateway.py              # orchestrator
│   ├── adapters/               # per-protocol readers
│   ├── hl7/builder.py          # ORU^R01 assembly + escaping
│   ├── transport/              # dispatcher, MLLP, SFTP
│   ├── discovery/              # plug-and-play probes + service
│   ├── security/               # auth, secrets, audit
│   └── devices/                # DeviceDefinition + registry
├── webui/
│   ├── app.py                  # Flask app + REST API + /metrics
│   └── templates/              # jinja2 templates
├── tools/
│   ├── discover.py             # standalone discovery CLI
│   └── keygen.py               # license key gen
├── scripts/
│   ├── install.sh              # interactive installer
│   ├── bootstrap.sh            # curl | bash
│   ├── build-deb.sh            # dpkg-buildpackage wrapper
│   ├── build-rpi-image.sh      # pi-gen wrapper
│   ├── jerumednexus-gateway.service
│   ├── jerumednexus-webui.service
│   ├── jerumednexus-device-notify@.service
│   └── 99-jerumednexus-devices.rules
├── debian/                     # .deb packaging
├── deploy/ansible/             # fleet rollout playbook
├── tests/                      # pytest suite
└── docs/
    ├── ARCHITECTURE.md         # this file
    └── ...
```
