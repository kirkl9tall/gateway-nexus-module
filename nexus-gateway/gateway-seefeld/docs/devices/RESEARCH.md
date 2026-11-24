# Device protocol research — findings & sources

> **Scope.** This document records the protocol details discovered through
> vendor documentation, open-source middleware projects, and integration
> guides for every device profile shipped in `config/devices/`. It is the
> authoritative reference for the YAML metadata and the parsers.
>
> **Legend**
> - **[VERIFIED-PROD]** — device already worked in real Swiss/DACH praxis
>   before the JerumedNexus refactor (owner has real frame samples).
> - **[VERIFIED-DOC]** — protocol confirmed via vendor manual or a
>   trustworthy third-party integration guide.
> - **[SPECULATIVE]** — YAML profile derived from marketing pages or
>   generic vendor family behavior; **do not ship to a clinic without
>   validating on real hardware**.

---

## 1. Sysmex family

### Sysmex XQ-320  [VERIFIED-PROD]
- Physical: **1 serial (RS-232) + 2 LAN ports**.
- Protocol: HL7 v2 via LAN (MLLP framing) **or** ASTM E1394 via serial.
- Message: ORU^R01 with OBX per parameter (WBC, RBC, HGB, HCT, MCV, MCH,
  MCHC, PLT, RDW, MPV, ...).
- Baud: 9600 8-N-1 when using serial ASTM.
- Adapter: `sysmex_astm` (serial) or `mllp_hl7` (LAN).
- Source: Sysmex XQ-Series Communication Specification (vendor manual);
  owner's production installs at 3 Swiss praxis.

### Sysmex XN-550, XN-1000, XP-300  [VERIFIED-DOC]
- Protocol: **ASTM E1394 over TCP/IP** (XN family), classical serial ASTM
  E1381 for XP-300.
- Frame structure: H|\^&|... P| O| R| ... L| with ENQ/ACK/STX/ETX/EOT
  handshake per E1381 low-level layer.
- Sources: [python-astm](https://github.com/kxepal/python-astm) library
  documentation; Sysmex XN-L Interface Specification.

---

## 2. Roche Cobas family

### Cobas b101  [VERIFIED-PROD]
- Protocol: **POCT1-A2** (XML over HTTP or serial framing).
- Purpose: HbA1c + lipids POCT.
- Adapter: `cobas_poct`.
- Source: Roche cobas b 101 POCT1-A2 Host Interface Manual.

### Cobas c 111  [VERIFIED-DOC — CORRECTED]
- Protocol: **Roche-specific ASTM (LIS2-A2)** via RS-232 or TCP/IP.
- **NOT HL7 MLLP** (previous YAML was wrong; fixed 2026-08-27).
- Roche timeout on ENQ: **15 seconds** (default in most ASTM libs is 30s;
  configure explicitly).
- Sender ID contains: manufacturer + instrument type + SW version +
  protocol version + serial number.
- Sources: [LISBridge/cobas-c311](https://lisbridge.com/instruments/cobas-c311);
  [senaite.astm](https://github.com/senaite/senaite.astm) test fixture
  `cobas_c111.txt`; Cobas c111 Host Interface Manual v3.0.

### Cobas h 232
- Protocol: **POCT1-A** via docking station.
- Handheld cardiac marker analyzer; delivers results in batch when
  cradled.
- Adapter: `cobas_poct`.

### Cobas Liat
- Protocol: **HL7 v2.5.1 encapsulated in POCT1-A envelope**.
- Molecular POCT (flu, strep, COVID).
- Reference: [Cobas Liat Host Interface Manual v11.3](https://manuals.plus/m/1479906d40b2a65333839740f7b3782efc8cce2efe48f7eb508c90d3d741df3a).

### Roche Reflotron Plus  [VERIFIED-DOC]
- Protocol: **RS-232, 9600 or 4800 baud, 8-N-1**, semicolon-separated
  data records.
- Frame: `date;time;patient_id;test_code;result;unit;flag<CR><LF>`.
- Adapter: custom `reflotron_serial` (existing `uc1000` CSV adapter
  works as a starting point).

---

## 3. Abbott / Alere family

### Afinion 2  [VERIFIED-DOC]
- Protocol: **POCT1-A2** (default) — also supports HL7 or ASTM
  1381-95/1394-97 (selectable at configuration).
- Purpose: HbA1c, CRP, ACR POCT.
- Connectivity: TCP/IP (native network module).
- Adapter: `cobas_poct` for POCT1-A2; `mllp_hl7` if HL7 is enabled.
- Source: [Abbott Afinion 2 product page](https://www.globalpointofcare.abbott/ww/en/product-details/afinion2-analyzer.html)
  + Afinion 2 User Manual.

### Abbott i-STAT
- Protocol: **POCT1-A + Abbott ASTM variant** (via docking station).
- Handheld blood gas + chemistry.

---

## 4. Seamaty (from user's list)

### Seamaty SD1 / SD3  [VERIFIED-PROD]
- Protocol: **HL7 v2 ORU^R01 / ACK** via RS-232 (LIS Connection Manual).
- Segments used: MSH, MSA (in ACK), PID, OBR, OBX (per analyte).
- Baud: 9600 8-N-1 default.
- Adapter: `mllp_hl7` or plain HL7-over-serial (add framing wrapper).
- Reference: [Seamaty LIS Connection Manual on Scribd](https://www.scribd.com/document/818875867/LOCMEDT-LOC-200)
  and vendor's ASTM/HL7 dual-mode datasheet.

### Seamaty SMT-120 (kept for backward compatibility)
- Bench-top chemistry, HL7 v2 or ASTM E1394.

---

## 5. Menarini / Sebia / others

### UC-1000 (urine strip reader by Menarini)  [VERIFIED-PROD]
- Protocol: **RS-232 CSV** semicolon-separated at 9600 baud.
- Frame: `patient_id;strip_no;LEU;NIT;URO;PRO;pH;BLD;SG;KET;BIL;GLU<CR>`.
- Adapter: `uc1000` (existing).

### Menarini HA-8180T (HbA1c HPLC)
- Protocol: RS-232 semi-proprietary; supports LIS1-A option.
- [SPECULATIVE] — no manual obtained yet.

---

## 6. LOC-200 (LOCMEDT dry chemistry)  [VERIFIED-PROD]
- Protocol: custom serial framing — parsed by `loc200_reader.py`.
- Notes: 12 preset panels; result frame contains a list of
  test_code=value pairs.
- **DO NOT REFACTOR** the existing parser without a real device to test
  against — owner reports it works in 3 clinics.
- Reference: [LOC-200 Manual (Scribd)](https://www.scribd.com/document/818875867/LOCMEDT-LOC-200).

---

## 7. Bio-Rad HbA1c family

### D-100  [VERIFIED-DOC — CORRECTED]
- Protocol: **bi-directional HL7 v2** via the Bio-Rad Data Manager
  module (add-on PC).
- **Direct instrument** interface is ASTM/LIS-2 at RS-232; HL7 requires
  the Data Manager layer. YAML profile assumes the Data Manager is
  present (typical DACH setup).

### D-10 (older sibling)
- Protocol: **LIS1-A / LIS2-A (ASTM)** at 9600 baud RS-232.
- Adapter: `sysmex_astm` compatible.
- Source: [D-10 LIS Interface Guide (Scribd)](https://www.scribd.com/document/475859984/D-10-LIS-manual).

---

## 8. HemoCue

### HemoCue HB 801, WBC Diff
- Protocol: **manual entry + optional POCT1-A dock** (HemoCue 201 DM
  supports POCT1-A).
- Baseline handhelds send no data; the dock/DMS is the connectivity
  layer.
- [SPECULATIVE] YAML — depends on whether the clinic has the DMS module.

---

## 9. Horiba (BC/hematology)

### Microsemi CRP  [VERIFIED-DOC — CORRECTED]
- Protocol: **unidirectional ASTM (LIS2-A2)**.
- **NOT HL7 MLLP** (previous YAML was wrong; fixed 2026-08-27).
- Physical: RS-232 or Ethernet.
- Sender only (device transmits results, no host queries).
- Source: [HORIBA Microsemi CRP product page](https://www.horiba.com/usa/healthcare/products/detail/action/show/Product/microsemi-crp-lc-767g-3302/)
  + AQURE integration guide.

---

## 10. Radiometer (blood gas)

### ABL80 Flex / ABL800 Flex
- Protocol: **HL7 v2 via Ethernet** to AQURE middleware; direct HL7 via
  TCP if AQURE is not present.
- [VERIFIED-DOC] via AQURE Device Connectivity manual v2.6.0.

---

## 11. Siemens POCT

### DCA Vantage (HbA1c, ACR)
- Protocol: **POCT1-A** over Ethernet.

### Clinitek Novus (urine analyzer)
- Protocol: **POCT1-A** over Ethernet.

Both connect via Siemens' Radiance / POC data manager typically.

---

## 12. Others

### Nova StatStrip (glucose/lactate POCT)  [VERIFIED-DOC]
- Protocol: **POCT1-A2 + HL7 + ASTM** — tutti supportati.
- Physical: **RJ-45 Ethernet TCP/IP 100 Mbit**.
- Middleware: **NovaNet** (bidirectional).
- Source: [Nova Biomedical — StatStrip Lactate](https://novabiomedical.com/welcome/statstrip-lactate/)

### Siemens DCA Vantage  [VERIFIED-DOC]
- Protocol: **POCT1-A2** — supporta HbA1c + ACR.
- Middleware: **RAPIDComm Data Management System**.
- Source: [Siemens DCA Vantage](https://www.siemens-healthineers.com/diabetes/diabetes/dca-vantage-analyzer)

### HemoCue Hb 201 DM / WBC DIFF  [VERIFIED-DOC — CORRECTED]
- Protocol: **POCT1-A** (NON HL7 diretto — non ha porta MLLP).
- Docking station gestisce la connessione LIS/HIS.
- Fino a 5 analizzatori per docking station.
- Il gateway riceve tramite adapter `cobas_poct` (POCT1-A2 compat).
- Source: [HemoCue Hb 201 DM](https://hemocue.com/us/products/hematology/hemocue-hb-201-dm-system/)

### Radiometer ABL80 FLEX / ABL800 FLEX  [VERIFIED-DOC — CORRECTED]
- Protocol: **Statlink** (high-level Radiometer proprietary) via **AQURE** middleware.
- HL7 v2 supportato ma con **ADR_A19** invece di ADT — implementazione custom.
- Non collegabile direttamente al gateway senza AQURE nel mezzo.
- Source: [Radiometer AQURE Device Drivers](https://radiometer.com/en/products/poc-it-solution-aqure/device-drivers)

### Abbott i-STAT Alinity  [VERIFIED-DOC]
- Protocol: **POCT1-A** via **AlinIQ Network Connectivity (NCi)**.
- Wireless o wired.
- Source: [Abbott i-STAT Alinity](https://www.globalpointofcare.abbott/ww/en/product-details/apoc/istat-alinity-ous.html)

### Beckman Coulter AU480 (Chemistry)  [VERIFIED-DOC]
- Protocol: **ASTM E1394-91** su LAN (5 livelli: physical/network/message
  control/message/application).
- Source: [AU480 Online LAN Specification](https://www.scribd.com/document/545809198/AU680-AU480-Online-LAN-Specification-ver-1)

### Beckman AU480 (chemistry)
- Protocol: ASTM or HL7 via LabBridge / LabTrak middleware.
- [SPECULATIVE] YAML.

### DIRUI H-800 (chemistry)
- Protocol: HL7 v2 or ASTM. [SPECULATIVE].

### Erba XL-200
- Protocol: RS-232 CSV or ASTM. [SPECULATIVE].

---

## Additional useful devices to consider adding

Based on DACH market presence:

| Device | Protocol | Rationale |
|--------|----------|-----------|
| **Mindray BC-3000/BC-5000** | HL7 v2 via USB/LAN | Popular budget hematology in DACH praxis |
| **Mindray BS-240/BS-300** | HL7/ASTM | Chemistry counterpart |
| **i-SENS CareSens Expert Plus** | POCT1-A2 or HL7 IHE DEC | Blood gas POCT with i-SmartCare middleware |
| **PixCell HemoScreen** | HL7 v2 over MLLP | 5-diff CBC POCT — direct MLLP without middleware, per senaite.astm docs |
| **EKF DiaSpect Tm** | Manual + POCT dock | HGB POCT common in rural DACH |
| **Convergent Technologies ConvergentIA** | HL7/ASTM | Immunoassay POCT |

Add YAML profiles for these on demand.

---

## Open-source reference implementations

If we need to extend a parser, these are the best places to look:

1. **[python-astm](https://github.com/kxepal/python-astm)** — Python
   implementation of ASTM E1381/E1394. Sysmex driver in-repo. MIT license.
2. **[senaite.astm](https://github.com/senaite/senaite.astm)** — asyncio
   ASTM + HL7 middleware. Ships Cobas c111 test fixture. GPL. Ports:
   ASTM 4010 / HL7 MLLP 2575.
3. **[node-astm](https://github.com/dexterlabora/node-astm)** — Node.js
   ASTM parser. Useful for understanding frame layer.
4. **HL7 apy** ([python-hl7](https://github.com/johnpaulett/python-hl7))
   — canonical HL7 v2 parser used everywhere.

For real ORU^R01 examples:
```
MSH|^~\&|SysmexXN|Lab|LIS|Clinic|20260827120000||ORU^R01|MSG00001|P|2.5
PID|1||PAT-42^^^Clinic^MR||Muster^Anna||19850101|F
OBR|1|SN0001|SP12345|CBC^Complete Blood Count^LN|||20260827115000
OBX|1|NM|WBC^Leukocytes^LN||7.4|10*3/uL|4.0-10.0|N|||F
OBX|2|NM|RBC^Erythrocytes^LN||4.8|10*6/uL|3.9-5.2|N|||F
OBX|3|NM|HGB^Hemoglobin^LN||14.2|g/dL|12.0-16.0|N|||F
```

---

## Change log

- **2026-08-27**: Initial version.
  - Corrected Horiba Microsemi CRP: MLLP → ASTM (unidirectional).
  - Corrected Cobas c 111: MLLP → Roche-specific ASTM, added 15s
    timeout note.
  - Clarified Bio-Rad D-100 uses HL7 via Data Manager module.
  - Confirmed Afinion 2 POCT1-A2 assumption was correct.
- Author: research from vendor docs + open-source ASTM/HL7 middleware
  projects (python-astm, senaite.astm, LISBridge). See per-device
  sources above.
