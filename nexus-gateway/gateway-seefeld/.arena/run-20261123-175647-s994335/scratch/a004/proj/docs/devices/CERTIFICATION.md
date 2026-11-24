# Device Certification Report

Aggregated verification signals for every device profile.

**Certification tiers:**
- 💎 **PLATINUM** — real production + field sign-off
- 🟢 **GOLD** — real production, no field sign-off yet
- 🟡 **SILVER** — vendor manual confirmed + E2E simulator passes
- 🟠 **BRONZE** — vendor manual only, or E2E simulator only
- ⚪ **UNCERTIFIED** — speculative, not yet validated

| Device | Vendor | Protocol | Prod | Doc | E2E | Golden | Field | Tier |
|--------|--------|----------|:----:|:---:|:---:|:------:|:-----:|:----:|
| `abbott_i_stat` | Abbott | `mllp_hl7` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `afinion_2` | Abbott (ex Alere) | `cobas_poct` | — | ✓ | — | — | — | 🟠 BRONZE |
| `beckman_au480` | Beckman Coulter | `mllp_hl7` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `biorad_d100` | Bio-Rad | `mllp_hl7` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `cobas_b101` | Roche | `cobas_poct` | ✓ | — | — | — | ✓ | 💎 PLATINUM |
| `dirui_h800` | Dirui | `mllp_hl7` | — | — | ✓ | — | — | 🟠 BRONZE |
| `erba_xl200` | Erba Mannheim | `mllp_hl7` | — | — | ✓ | — | — | 🟠 BRONZE |
| `hemocue_hb_801` | HemoCue | `mllp_hl7` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `hemocue_wbc_diff` | HemoCue (Radiometer) | `mllp_hl7` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `horiba_microsemi` | Horiba | `sysmex_astm` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `isens_caresens` | i-SENS | `cobas_poct` | — | ✓ | — | — | — | 🟠 BRONZE |
| `menarini_ha8180t` | Menarini (A. Menarini Diagnostics) | `mllp_hl7` | — | — | ✓ | — | — | 🟠 BRONZE |
| `mindray_bc5000` | Mindray | `mllp_hl7` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `mindray_bs240` | Mindray | `sysmex_astm` | — | — | ✓ | — | — | 🟠 BRONZE |
| `nova_statstrip` | Nova Biomedical | `mllp_hl7` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `pixcell_hemoscreen` | PixCell Medical | `mllp_hl7` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `radiometer_abl80` | Radiometer | `mllp_hl7` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `roche_cobas_c111` | Roche | `sysmex_astm` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `roche_cobas_h232` | Roche | `cobas_poct` | — | ✓ | — | — | — | 🟠 BRONZE |
| `roche_reflotron_plus` | Roche | `reflotron_serial` | — | ✓ | — | — | — | 🟠 BRONZE |
| `seamaty_smt120` | Seamaty | `mllp_hl7` | ✓ | — | ✓ | — | — | 🟢 GOLD |
| `siemens_clinitek_novus` | Siemens Healthineers | `mllp_hl7` | — | — | ✓ | — | — | 🟠 BRONZE |
| `siemens_dca_vantage` | Siemens Healthineers | `mllp_hl7` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `sysmex_xn1000` | Sysmex | `sysmex_astm` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `sysmex_xn550` | Sysmex | `sysmex_astm` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `sysmex_xp300` | Sysmex | `sysmex_astm` | — | ✓ | ✓ | — | — | 🟡 SILVER |
| `sysmex_xq320` | Sysmex | `sysmex_astm` | ✓ | — | ✓ | — | ✓ | 💎 PLATINUM |
| `uc1000` | Menarini | `uc1000_serial` | ✓ | — | — | — | ✓ | 💎 PLATINUM |

## Aggregato
Totale device: **28**

- 💎 **PLATINUM**: 3
- 🟢 **GOLD**: 1
- 🟡 **SILVER**: 15
- 🟠 **BRONZE**: 9
