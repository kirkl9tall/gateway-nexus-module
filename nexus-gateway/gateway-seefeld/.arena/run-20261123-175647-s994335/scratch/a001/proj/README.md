[![CI](https://github.com/jerumed-nexus/jerumednexus-gateway/actions/workflows/quality.yml/badge.svg)](https://github.com/jerumed-nexus/jerumednexus-gateway/actions/workflows/quality.yml)
[![Security](https://github.com/jerumed-nexus/jerumednexus-gateway/actions/workflows/security.yml/badge.svg)](https://github.com/jerumed-nexus/jerumednexus-gateway/actions/workflows/security.yml)
[![Release](https://github.com/jerumed-nexus/jerumednexus-gateway/actions/workflows/release.yml/badge.svg)](https://github.com/jerumed-nexus/jerumednexus-gateway/actions/workflows/release.yml)
[![Tests](https://img.shields.io/badge/tests-165%20pass-brightgreen)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-88%25%20critical-brightgreen)](docs/PERFORMANCE.md)
[![Devices](https://img.shields.io/badge/devices-28%20supported-blue)](docs/devices/COMPATIBILITY.md)
[![PLATINUM](https://img.shields.io/badge/certified-3%20platinum%20%7C%201%20gold-yellow)](docs/devices/CERTIFICATION.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![Signed](https://img.shields.io/badge/.deb-GPG%20signed-blue)](docs/APT-REPO.md)
[![SBOM](https://img.shields.io/badge/SBOM-CycloneDX-blue)](docs/SLSA.md)

# JerumedNexus Gateway

**Enterprise-grade Raspberry Pi gateway: laboratory analyzers → HL7 v2.5 → PIS/LIS**

Version 1.1 — hardened auth, plug-and-play device detection, `.deb` packaging, one-command install.

```
┌─────────────────┐    RS-232/LAN    ┌────────────────────┐    MLLP/TCP     ┌──────────────┐
│  LOCMEDT        │ ──────────────→  │  JerumedNexus Gateway   │ ──────────────→ │  Vitomed     │
│  LOC-200        │                  │  (Raspberry Pi)     │                 │  curaMED     │
│  Analyzer       │                  │                     │ ──────────────→ │  Aeskulap    │
└─────────────────┘                  │  • Parses frames    │                 │  Axenita     │
                                     │  • Builds HL7 ORU   │ ──── File ───→  │  WinMed      │
                                     │  • Fans out to PIS  │                 │  DnaMed      │
                                     └────────────────────┘                 │  Tomedo      │
                                                                             └──────────────┘
```

> **IT Software Note:** This is a pure IT integration component. It performs no clinical
> data modification — it reads, translates (format conversion only), and forwards.
> No medical decision logic is implemented.

---

## Features

- **Zero-modification relay** — raw analyte values are forwarded exactly as received
- **HL7 v2.5 ORU^R01** with LOINC coding for all 35 LOC-200 parameters
- **MLLP/TCP delivery** — Vitomed, curaMED, Aeskulap, Axenita, DnaMed
- **File-drop delivery** — WinMed, Tomedo (watch-folder / import-Verzeichnis)
- **Fan-out** — send one result to multiple PIS simultaneously
- **Retry with backoff** — configurable retry attempts on delivery failure
- **Async I/O** — non-blocking, handles RS-232 and network concurrently
- **Systemd service** — auto-start on Raspberry Pi boot
- **LOINC mapping** — built-in table + custom override via YAML

---

## Hardware Requirements

| Component | Specification |
|-----------|--------------|
| Raspberry Pi | 3B+ / 4 / 5 (any model with USB) |
| OS | Raspberry Pi OS (Bookworm / Bullseye) |
| RS-232 adapter | USB→RS-232 (e.g. Prolific PL2303, FTDI) |
| Network | Ethernet recommended for MLLP delivery |

**LOC-200 connection options:**
- **RS-232**: DB9 cable → USB adapter → Raspberry Pi USB port  
- **LAN**: Ethernet cable (LOC-200 network port → same LAN as Pi)

---

## Quick Start

### Option 1 — remote bootstrap (fresh Raspberry Pi)

```bash
curl -fsSL https://install.jerumed-nexus.ch/loc200 | sudo bash
```

The installer runs an interactive wizard that asks for the practice name and
admin password, generates a random API token for the HTTP ingestion endpoint,
creates a dedicated `loc200` system user, installs both systemd services
(`jerumednexus-gateway`, `jerumednexus-webui`), opens ports 8080 + 5003 in UFW, and
installs the udev rules for plug-and-play device detection.

### Option 2 — Debian package (enterprise rollout)

```bash
# On build host (Debian 12)
sudo apt install devscripts debhelper dh-python
./scripts/build-deb.sh

# On target
sudo apt install ./jerumednexus-gateway_1.1.0_all.deb
# Open http://<pi>:8080 -> setup wizard prompts for admin password
```

Upgrades are just `sudo apt install --only-upgrade jerumednexus-gateway` — config,
logs and secrets survive.

### Option 3 — pre-flashed Raspberry Pi OS image

```bash
sudo ./scripts/build-rpi-image.sh   # produces deploy/jerumednexus-gateway-*.img.xz
# Flash with Raspberry Pi Imager, boot, done.
```

### Option 4 — manual clone (dev)

```bash
git clone https://github.com/jerumed-nexus/jerumednexus-gateway.git
cd jerumednexus-gateway
sudo ./scripts/install.sh          # interactive
# or: sudo ./scripts/install.sh --unattended   # no prompts, defaults
# or: sudo ./scripts/install.sh --upgrade      # in-place upgrade
```

Access the Web UI at `http://<raspberry-pi-ip>:8080` and follow the first-run
setup wizard.

---

## Plug-and-play device detection

When you plug a supported USB serial adapter into the Pi, or configure a
LAN-attached analyzer, the gateway auto-detects it and shows a badge on the
Analizzatori page. Two clicks activate it — no manual YAML editing required.

Behind the scenes:

- **udev rules** (`scripts/99-jerumednexus-devices.rules`) recognise common
  USB→RS-232 chipsets (FTDI, PL2303, CH340, CP210x) and create stable
  `/dev/loc200/<chip>-<serial>` symlinks.
- **Protocol fingerprinting** (`src/discovery/probes.py`) sniffs the first
  bytes and identifies HL7 MLLP, ASTM E1381, LOC-200 native, UC-1000, and
  Cobas b101 streams — with a confidence score.
- **REST API** (`/api/devices/discover`, `/api/devices/activate`) exposes
  discovery to the UI and to scripts.
- **CLI** for debugging: `python -m tools.discover` or
  `python -m tools.discover --tcp 192.168.1.0/24 --port 5000,6000`.

Activation writes to `config/gateway.yaml` under `devices:` — a service
restart picks up the new device.

---

## Configuration Reference (`config/gateway.yaml`)

### LOC-200 Connection

```yaml
loc200:
  connection_type: "serial"     # "serial" | "network"

  serial:
    port: "/dev/ttyUSB0"        # check: ls /dev/ttyUSB*
    baudrate: 9600              # LOC-200 default RS-232 speed
    bytesize: 8
    parity: "N"
    stopbits: 1.0

  debug_raw_frames: false       # true = log every raw byte (debugging)
```

### HL7 Settings

```yaml
hl7:
  version: "2.5"
  sending_application: "LOC200_GW"
  sending_facility: "PRAXIS_NAME"   # ← your practice name
  receiving_application: "LIS"
  receiving_facility: "PRAXIS_NAME"
```

### PIS Targets

Each PIS can receive messages via **MLLP/TCP** or **file-drop**:

```yaml
targets:
  - name: "vitomed"
    type: "vitomed"
    enabled: true
    host: "192.168.1.50"
    port: 6661
```

---

## PIS Integration Details

### Vitomed / Vitodata (Vitodata AG)

| Parameter | Value |
|-----------|-------|
| Protocol | MLLP/TCP or File-drop |
| Default Port | Contact Vitodata support |
| File format | HL7 v2.x `.hl7` |
| Encoding | UTF-8 or ISO-8859-1 |

Configure in Vitodata: **Einstellungen → Labor → HL7-Import**  
Set the import folder or TCP listener port to match `gateway.yaml`.

### curaMED (Swisscom Health AG)

| Parameter | Value |
|-----------|-------|
| Protocol | MLLP/TCP |
| Contact | Swisscom Health support portal |

curaMED supports HL7 v2.x laboratory result import.  
Contact **support.health@swisscom.com** for the HL7 port configuration.

### Aeskulap (CompuGroup Medical)

| Parameter | Value |
|-----------|-------|
| Protocol | MLLP/TCP |
| Standard | HL7 v2.5 ORU^R01 |

Configure in Aeskulap: **Administration → Schnittstellen → HL7-Laborimport**

### Axenita (Axon Lab AG)

| Parameter | Value |
|-----------|-------|
| Protocol | MLLP/TCP (bidirectional) |
| Contact | Axon Lab integration team |

Axenita has full HL7 v2.x support. Contact Axon Lab for the LIS listener  
port and to obtain a test environment.

### WinMed (TMR AG)

| Parameter | Value |
|-----------|-------|
| Protocol | **File-drop** (recommended) |
| Folder | `Laboreingang` in WinMed data directory |
| Format | HL7 `.hl7` files |

Configure in `gateway.yaml`:
```yaml
- name: "winmed"
  type: "winmed"
  enabled: true
  watch_folder: "\\\\WINMED-SERVER\\Shares\\Laboreingang"
  file_extension: ".hl7"
```
WinMed polls this folder automatically. Contact TMR AG for the exact path.

### DnaMed

| Parameter | Value |
|-----------|-------|
| Protocol | MLLP/TCP |
| Standard | HL7 v2.5 |

### Tomedo (zollsoft GmbH / zollsoft AG)

| Parameter | Value |
|-----------|-------|
| Protocol | **File-drop** |
| Setup | Einstellungen → Labor → Labordatentransfer |
| Format | HL7 v2.x `.hl7` |

In Tomedo, set the **Import-Verzeichnis** to the same folder configured  
in `gateway.yaml → watch_folder`. Tomedo detects and imports `.hl7` files automatically.

---

## HL7 Message Structure

The gateway generates **ORU^R01** (Observation Result) messages:

```
MSH|^~\&|LOC200_GW|PRAXIS|LIS|PRAXIS|20240601103000||ORU^R01^ORU_R01|A1B2C3|P|2.5|||NE|AL||8859/1
PID|1||P123^^^PRAXIS||Mueller^Hans||||M
PV1|1|O
OBR|1|S001||General Chemistry I Kit 18^General Chemistry I Kit 18^L||20240601103000|20240601103000||||||||||LOT-001|||F
OBX|1|NM|1920-8^Aspartate aminotransferase^LN|1|13|U/L^U/L^ISO+|15^40|L|||F|||20240601103000
OBX|2|NM|2093-3^Cholesterol^LN|1|4.71|mmol/L^mmol/L^ISO+|3.1^5.7||||F|||20240601103000
```

**Key segments:**

| Segment | Purpose |
|---------|---------|
| MSH | Message header, routing, timestamps |
| PID | Patient demographics (from LOC-200 report) |
| PV1 | Visit info (department) |
| OBR | Panel/disc identification, lot number |
| OBX | One per analyte — LOINC code, value, unit, reference range, flag |

**Abnormal flags (OBX-8):**

| LOC-200 | HL7 | Meaning |
|---------|-----|---------|
| UP / ↑ | H | Above upper reference limit |
| DOWN / ↓ | L | Below lower reference limit |
| (none) | (empty) | Within reference range |

---

## LOINC Mapping

All 35 LOC-200 parameters are pre-mapped to LOINC codes. To override or add:

```yaml
# config/loinc_map.yaml
AST:
  loinc: "1920-8"
  name: "Aspartate aminotransferase [Enzymatic activity/vol] in Serum"
  unit: "U/L"
```

---

## Project Structure

```
loc200_gateway/
├── main.py                        # Entry point
├── requirements.txt
├── config/
│   ├── gateway.yaml.example       # → copy to gateway.yaml
│   ├── loinc_map.yaml             # optional LOINC overrides
│   └── settings.py                # Pydantic config models
├── src/
│   ├── gateway.py                 # Orchestrator
│   ├── adapters/
│   │   └── loc200_reader.py       # RS-232 / TCP reader + frame parser
│   ├── hl7/
│   │   └── builder.py             # HL7 v2.5 ORU^R01 builder
│   └── transport/
│       └── dispatcher.py          # MLLP sender + file-drop writer
├── tests/
│   └── test_gateway.py            # pytest unit tests
├── scripts/
│   ├── install.sh                 # Raspberry Pi installer
│   └── jerumednexus-gateway.service     # systemd unit
└── logs/                          # auto-created
```

---

## Operations

### Service management

```bash
sudo systemctl status  jerumednexus-gateway
sudo systemctl restart jerumednexus-gateway
sudo systemctl stop    jerumednexus-gateway
sudo journalctl -u jerumednexus-gateway -f --since "1 hour ago"
```

### Find RS-232 port

```bash
ls /dev/ttyUSB*         # USB→RS232 adapters
dmesg | grep tty        # kernel messages
```

### Test MLLP connectivity

```bash
# Check if PIS is listening on configured port
nc -zv 192.168.1.50 6661
```

### Run tests

```bash
cd /opt/jerumednexus
.venv/bin/pytest tests/ -v
```

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `No such file /dev/ttyUSB0` | USB adapter not detected | Check USB cable, `dmesg \| grep tty` |
| `Permission denied /dev/ttyUSB0` | User not in dialout group | `sudo usermod -aG dialout pi` + relogin |
| `Connection refused` on MLLP | PIS not listening | Verify PIS HL7 listener is active, check firewall |
| `QR Code Error` on LOC-200 | Disc issue | See LOC-200 manual Chapter 5 |
| HL7 message not imported | Wrong encoding/folder | Check PIS import settings, try ISO-8859-1 |
| `---` in result value | Analyte measurement error | LOC-200 signals abnormal sample; forwarded as-is |

---

## Security & compliance

- **Auth**: bcrypt hashing (cost 12), 12-char minimum, no default password;
  first-run wizard sets the admin credential. Sessions are HMAC-signed by a
  persistent secret key (`config/webui_secret.key`, mode 600) with 8h lifetime.
- **CSRF**: double-submit token on all state-changing endpoints; forms carry a
  hidden `_csrf` field and JS fetches auto-attach `X-CSRF-Token`.
- **Rate limiting**: login endpoint locks out an IP after 5 failed attempts in
  5 minutes for 15 minutes.
- **HTTP ingestion**: LOC-200 HTTP endpoint requires `Authorization: Bearer
  <token>`; optional IP allowlist via `LOC200_HTTP_ALLOW`. Body size capped
  at 256 KiB.
- **HL7 escaping**: complete — `\`, `|`, `^`, `~`, `&`, `\r`, `\n`, FS and VT
  are all escaped, so hostile patient data cannot break segmentation or MLLP
  framing.
- **ACK correlation**: MSA-2 is verified against the sent MSH-10 to prevent
  cross-message ACK confusion.
- **Charset coherence**: MSH-18 matches the wire encoding (`UNICODE UTF-8` /
  `8859/1` / `ASCII`) — no more mangled umlauts.
- **Timestamps**: HL7 timestamps carry `%z` offset (e.g.
  `20250825120000+0200`) by default.
- **Update endpoint**: `/api/update/apply` is localhost-only. Prefer
  `apt install --only-upgrade jerumednexus-gateway` for remote enterprise upgrades.
- **Audit log**: append-only JSONL at `logs/audit.jsonl`, patient IDs hashed
  (SHA-256, 16 hex), 90-day retention target — helps with nDSG / GDPR
  compliance evidence.
- **Systemd hardening**: services run as `loc200` (system user, `dialout`
  group only), `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`,
  `MemoryDenyWriteExecute`, `LockPersonality`, `SystemCallArchitectures=native`.
- **Secrets**: `config/secrets.env` (mode 600) or environment variables —
  never in `gateway.yaml`. SFTP credentials resolved via
  `<TARGET>_SFTP_{HOST,USER,PASS}` convention.
- **Clinical values are never modified** — pure format translation only.

### Regulatory note

The flag mapping (`UP → H`, `DOWN → L`) is a semantic transformation, so
this gateway may fall within scope of IVDR Class A in the EU. Verify with a
regulatory consultant (Swissmedic / MedTech notified body) before commercial
deployment.

---

## License

MIT License — see LICENSE file.

---

## Support

For LOC-200 protocol questions: **service@locmedt.com** / +86-22-58601276  
For PIS integration questions, contact your PIS vendor's technical support.
