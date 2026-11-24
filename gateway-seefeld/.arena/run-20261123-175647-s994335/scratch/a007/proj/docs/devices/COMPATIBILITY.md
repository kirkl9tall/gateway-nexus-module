# Device compatibility matrix

| ID | Display name | Vendor | Type | Status |
|----|--------------|--------|------|--------|
| `abbott_i_stat` | Abbott i-STAT (POCT wireless) | Abbott | `mllp_hl7` | ⚪ SPECULATIVE |
| `afinion_2` | Abbott Afinion 2 (HbA1c POCT) | Abbott (ex Alere) | `cobas_poct` | 🟡 VERIFIED-DOC |
| `beckman_au480` | Beckman Coulter AU480 (Chimica) | Beckman Coulter | `mllp_hl7` | ⚪ SPECULATIVE |
| `biorad_d100` | Bio-Rad D-100 (HbA1c) | Bio-Rad | `mllp_hl7` | 🟡 VERIFIED-DOC |
| `cobas_b101` | Roche Cobas b 101 (POCT) | Roche | `cobas_poct` | 🟢 VERIFIED-PROD |
| `dirui_h800` | Dirui H-800 (Urine Analyzer) | Dirui | `mllp_hl7` | ⚪ SPECULATIVE |
| `erba_xl200` | Erba XL-200 (Chimica) | Erba Mannheim | `mllp_hl7` | ⚪ SPECULATIVE |
| `hemocue_hb_801` | HemoCue Hb 801 (Emoglobina) | HemoCue | `mllp_hl7` | ⚪ SPECULATIVE |
| `hemocue_wbc_diff` | HemoCue WBC DIFF (POCT) | HemoCue (Radiometer) | `mllp_hl7` | ⚪ SPECULATIVE |
| `horiba_microsemi` | Horiba Microsemi CRP | Horiba | `sysmex_astm` | 🟡 VERIFIED-DOC |
| `isens_caresens` | i-SENS CareSens Expert Plus (Blood Gas POCT) | i-SENS | `cobas_poct` | 🟡 VERIFIED-DOC |
| `menarini_ha8180t` | Menarini HA-8180T (HbA1c) | Menarini (A. Menarini Diagnostics) | `mllp_hl7` | ⚪ SPECULATIVE |
| `mindray_bc5000` | Mindray BC-5000 (5-diff Hematology) | Mindray | `mllp_hl7` | 🟡 VERIFIED-DOC |
| `mindray_bs240` | Mindray BS-240 (Chemistry) | Mindray | `sysmex_astm` | ⚪ SPECULATIVE |
| `nova_statstrip` | Nova StatStrip (Glucose POCT) | Nova Biomedical | `mllp_hl7` | ⚪ SPECULATIVE |
| `pixcell_hemoscreen` | PixCell HemoScreen (POCT CBC) | PixCell Medical | `mllp_hl7` | 🟡 VERIFIED-DOC |
| `radiometer_abl80` | Radiometer ABL80 FLEX (Blood Gas) | Radiometer | `mllp_hl7` | 🟡 VERIFIED-DOC |
| `roche_cobas_c111` | Roche Cobas c 111 Chemie | Roche | `sysmex_astm` | 🟡 VERIFIED-DOC |
| `roche_cobas_h232` | Roche Cobas h 232 (Kardiomarker POCT) | Roche | `cobas_poct` | 🟡 VERIFIED-DOC |
| `roche_reflotron_plus` | Roche Reflotron Plus (Dry Chemistry) | Roche | `reflotron_serial` | 🟡 VERIFIED-DOC |
| `seamaty_smt120` | Seamaty SMT-120 Chemie | Seamaty | `mllp_hl7` | 🟢 VERIFIED-PROD |
| `siemens_clinitek_novus` | Siemens CLINITEK Novus (Urine Analyzer) | Siemens Healthineers | `mllp_hl7` | ⚪ SPECULATIVE |
| `siemens_dca_vantage` | Siemens DCA Vantage (HbA1c/uACR) | Siemens Healthineers | `mllp_hl7` | ⚪ SPECULATIVE |
| `sysmex_xn1000` | Sysmex XN-1000 Hämatologie | Sysmex | `sysmex_astm` | 🟡 VERIFIED-DOC |
| `sysmex_xn550` | Sysmex XN-550 Hämatologie | Sysmex | `sysmex_astm` | 🟡 VERIFIED-DOC |
| `sysmex_xp300` | Sysmex XP-300 Hämatologie | Sysmex | `sysmex_astm` | 🟡 VERIFIED-DOC |
| `sysmex_xq320` | Sysmex XQ-320 Hämatologie | Sysmex | `sysmex_astm` | 🟢 VERIFIED-PROD |
| `uc1000` | Menarini UC-1000 Urinstatus | Menarini | `uc1000_serial` | 🟢 VERIFIED-PROD |

**Legend:**
- 🟢 **VERIFIED-PROD** — funzionante in cliniche reali DACH.
- 🟡 **VERIFIED-DOC** — protocollo confermato da vendor manual / middleware open-source.
- ⚪ **SPECULATIVE** — profilo derivato da materiale marketing; validare su hardware reale prima del deploy.
