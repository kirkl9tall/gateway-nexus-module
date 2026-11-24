# Catalogo device supportati

Ogni file in `config/devices/*.yaml` descrive un analizzatore.
`enabled: false` di default — vai in Web UI → **Configurazione → Passo 4**
per abilitare quello che ti serve.

Tutti i device sono **collegati al Raspberry Pi in uno di questi due modi**:
- **USB** (RS-232 tramite adattatore, oppure USB CDC seriale)
- **TCP** (cavo Ethernet — il device manda al Pi tramite rete)

Il WiFi non è un trasporto separato: se un device è sulla rete via WiFi,
il gateway lo vede come TCP.

## Analizzatori pre-configurati

| ID | Vendor | Modello | Trasporto | Protocollo | Uso tipico |
|----|--------|---------|-----------|------------|------------|
| `sysmex_xp300` | Sysmex | XP-300 | TCP :5000 | ASTM E1381 | Emocromo praxis |
| `sysmex_xq320` | Sysmex | XQ-320 | TCP :5001 | ASTM E1381 | Emocromo (nachfolger XP-300) |
| `sysmex_xn550` | Sysmex | XN-550 | TCP :5011 | ASTM E1381 | Emocromo lab medio |
| `sysmex_xn1000` | Sysmex | XN-1000 | TCP :5012 | ASTM E1381 | Emocromo ospedale |
| `cobas_b101` | Roche | Cobas b 101 | USB CDC | POCT1-A2 | HbA1c + lipidi + CRP POCT |
| `roche_cobas_c111` | Roche | Cobas c 111 | TCP :5020 | HL7 v2 MLLP | Chimica clinica benchtop |
| `roche_cobas_h232` | Roche | Cobas h 232 | USB CDC | POCT1-A2 | Cardio-markers POCT |
| `roche_reflotron_plus` | Roche | Reflotron Plus | TCP :5021 | HL7 v2 MLLP | Photometer strisce (lipidi, glu) |
| `afinion_2` | Abbott | Afinion 2 | USB CDC | POCT1-A2 | HbA1c/CRP/ACR POCT |
| `abbott_i_stat` | Abbott | i-STAT 1 | TCP :5070 | HL7 v2 MLLP | POCT emogas + cTnI (docking) |
| `hemocue_wbc_diff` | HemoCue | WBC DIFF | TCP :5030 | HL7 v2 MLLP | Emocromo POCT semplificato |
| `hemocue_hb_801` | HemoCue | Hb 801 | TCP :5031 | HL7 v2 MLLP | Emoglobina POCT |
| `biorad_d100` | Bio-Rad | D-100 | TCP :5040 | HL7 v2 MLLP | HbA1c HPLC |
| `radiometer_abl80` | Radiometer | ABL80 FLEX | TCP :5050 | HL7 v2 MLLP | Emogas / elettroliti |
| `siemens_dca_vantage` | Siemens | DCA Vantage | TCP :5060 | HL7 v2 MLLP | HbA1c/uACR POCT |
| `siemens_clinitek_novus` | Siemens | CLINITEK Novus | TCP :5061 | HL7 v2 MLLP | Urine analyzer |
| `nova_statstrip` | Nova Biomedical | StatStrip | TCP :5071 | HL7 v2 MLLP | Glucometro ospedaliero |
| `dirui_h800` | Dirui | H-800 | TCP :5080 | HL7 v2 MLLP | Urine analyzer economico |
| `erba_xl200` | Erba | XL-200 | TCP :5081 | HL7 v2 MLLP | Chimica clinica |
| `menarini_ha8180t` | Menarini | HA-8180T | TCP :5082 | HL7 v2 MLLP | HbA1c HPLC (alta produttività) |
| `beckman_au480` | Beckman Coulter | AU480 | TCP :5090 | HL7 v2 MLLP | Chimica clinica media capacità |
| `horiba_microsemi` | Horiba | Microsemi CRP | TCP :5004 | HL7 v2 MLLP | Emocromo + CRP POCT |
| `seamaty_smt120` | Seamaty | SMT-120 | TCP :6000 | HL7 v2 MLLP | Chimica dry-chem |
| `uc1000` | Menarini | UC-1000 | USB RS-232 | UC-1000 native | Urinstatus |

> ⚠️ **Verificato in laboratorio: solo LOC-200, Cobas b101, UC-1000, i profili
> Sysmex/Seamaty/Horiba testati con hardware simulato.**
> Le voci restanti sono **template basati su documentazione pubblica dei vendor** —
> vanno testate con il device reale prima del deploy in una clinica.

## Come aggiungere un device nuovo (via Web UI)

1. Vai su **Analizzatori** → clicca `+ Aggiungi device` (in alto a destra)
2. **Passo 1** — scegli **USB** o **TCP** in base a come è collegato al Pi
3. **Passo 2** — parametri (porta seriale + baudrate, oppure listen host + porta TCP)
4. **Passo 3** — dai un ID, nome, vendor, modello, protocollo
5. Lascia **disattivato** finché non hai testato la connessione
6. Web UI → **Trace protocollo** per verificare che i frame arrivino
7. Quando OK, attiva il toggle in **Configurazione → Passo 4**

Il gateway riceve un SIGHUP automatico e ricarica la config: **nessun restart necessario**.

## Come aggiungere un protocollo NON in lista

Il wizard permette di scegliere **Custom** dal menu Protocollo.
Serve però un adapter Python corrispondente:

1. Copia `src/adapters/mllp_reader.py` → `src/adapters/mio_reader.py`
2. Modifica il parser per il tuo formato
3. Registra il tipo in `src/devices/registry.py::_create_reader`
4. Restart del gateway

Vedi [CONTRIBUTING.md](../CONTRIBUTING.md) per il flow completo.

## Archivio device

I device rimossi vanno in `config/devices/_archive/` (mai eliminati veramente).
Ripristina dalla **Web UI → /devices/archive**.
