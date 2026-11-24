# Runbook — Sysmex XQ-320 TCP session times out with "No data received"

**Symptom**
```
[SYSMEX XQ320 Haematologie] Connection from ('192.168.0.187', 50806)
[SYSMEX XQ320 Haematologie] Aspetto ENQ da ('192.168.0.187', 50806)
[SYSMEX XQ320 Haematologie] No data received from ('192.168.0.187', 50806)
```

The Sysmex opens a TCP session on port 5006, no data flows, gateway
closes it after ~10 seconds. Repeats indefinitely.

**Root cause**
Per XQ-Series ASTM Host Interface Specifications v1.4 §6.4, the analyzer
has **two TCP/IP modes**, wire-incompatible with each other:

| Mode | Behaviour | Handshake |
|------|-----------|-----------|
| **E1381-95** | Raw records only, terminated by CR | none (no ENQ / no ACK / no EOT) |
| **E1381-02** | Full framing per §4.2 | ENQ → ACK, [STX][F#][Text][ETX][CHK][CR][LF] → ACK, EOT |

If the IPU is in **E1381-95** and the gateway waits for an ENQ, the
connection sits idle until timeout — exactly what the log shows. If the
IPU is in **E1381-02** but no analysis has completed, the same silence
occurs (nothing to send).

## Fix — 3 steps

### 1. Set the Sysmex IPU to E1381-02 with ACK/NAK  ← **the technician's action**

On the IPU service screen:
```
Setup → Communication → Host connection
  Protocol:        XR-Series ASTM1381-02 / ASTM1394-97
  Handshake:       ACK / NAK (bidirectional)
  Timing:          Real-time (NOT Batch)
  Host IP:         <Pi IP>
  Host Port:       5006
```

### 2. Confirm the device profile matches (gateway side)

Edit `config/devices/sysmex_xq320.yaml`:
```yaml
type: sysmex_astm
astm_mode: "1381-02"          # or "1381-95" if the tech chose that mode
unidirectional: false          # XQ-320 supports Query
idle_timeout_seconds: 300      # tolerate 5 min TCP silence
read_timeout_seconds: 15       # per-frame timeout from spec
listen_port: 5006
```

Then restart:
```bash
sudo systemctl restart jerumednexus-gateway
```

### 3. Verify

Trigger a test analysis on the Sysmex. Expected log:
```
[XQ-320] Connection from (192.168.0.187, ...) (astm_mode=1381-02, unidirectional=False)
[XQ-320] ENQ → ACK
[XQ-320] EOT — message complete (317 bytes)
[XQ-320] Parsed: sample=SN0001 patient=SN0001 analytes=22
```

If instead you set the tech to E1381-95, the log looks like:
```
[XQ-320] Connection from (192.168.0.187, ...) (astm_mode=1381-95, ...)
[XQ-320] E1381-95 message complete (289 bytes)
[XQ-320] Parsed: sample=SN0001 ...
```

Either is fine — just keep the gateway `astm_mode` in sync with the IPU
setting.

## If it still fails

- **The Sysmex opens TCP but never sends anything, even after a run** —
  check "Timing" is set to **Real-time** in the IPU. Batch mode holds
  everything until the operator presses "Send" on the IPU screen.
- **Frames arrive but checksum fails** — verify the IPU is set to
  ASTM E1394-97 record format (not the older -95 records).
- **Wrong sample_id parsed** — the XQ-320 puts the ID in field 4 of
  the O record (`O|1||SN0001|...`). Some firmware variants use field 3
  (`O|1|SN0001|...|`). Both are handled by our parser.
- **Sysmex XP-300 shows the same problem** — the XP-300 is
  **unidirectional** (send-only). Its profile must have
  `unidirectional: true`.

## Reference

- XQ-Series ASTM Host Interface Specifications v1.4 (Sysmex R320081).
- Test coverage: [tests/test_sysmex_astm_modes.py](../../tests/test_sysmex_astm_modes.py) — 7 tests.
- Adapter code: [src/adapters/sysmex_reader.py](../../src/adapters/sysmex_reader.py)
  — `_handle_client_e1381_02()` and `_handle_client_e1381_95()`.
- Fixed in JerumedNexus Gateway v1.3.0 (2026-08-28) based on production
  report from hausarztpraxis2 / `loc200-connect02`.
