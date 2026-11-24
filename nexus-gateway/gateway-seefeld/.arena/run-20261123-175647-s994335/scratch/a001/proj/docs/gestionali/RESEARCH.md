# Gestionali medici (LIS/HIS/PIS) — DACH research & sources

> Ricerca dei protocolli, porte e formato messaggi per i 6 gestionali
> principali del mercato Svizzero + Germania + Austria. Ogni voce ha
> **fonti verificabili** (URL vendor / documentazione pubblica).

**Legend**
- 🟢 **DIRECT-HL7** — riceve HL7 v2 MLLP nativo
- 🟡 **FILE-DROP** — file HL7/LDT in una cartella (via SFTP/CIFS)
- 🟠 **PROPRIETARY** — richiede middleware vendor-specifico
- ⚪ **UNKNOWN** — non trovato in docs pubblica, chiedere al vendor

---

## 🇨🇭 Svizzera

### Vitomed (Vitodata AG, Zürich) 🟡 FILE-DROP + 🟢 HL7

- **Vendor**: Vitodata AG (fondata 1985, sede Ottenbach ZH), ~5000 medici.
- **Base tecnica**: Windows/Server + client. Interoperabilità via
  **"connections"** (svariate centinaia in catalogo).
- **Laboratorio integrazione**: analisi da laboratori esterni vengono
  "fetched" e trasferite automaticamente al foglio paziente.
- **Protocollo verificato**: HL7 v2 MLLP + LDT (Labordatentransfer) via
  cartella condivisa. Setup con **connector app** fornita dal laboratorio.
- **Configurazione gateway** (per Vitomed): output `mllp_hl7` verso
  IP:2575 (standard) o file drop in cartella condivisa.
- **Fonte**: [Vitodata — Laboranbindung](https://www.vitodata.ch/de/vitomed-praxissoftware/patientenmanagement/labor-arztpraxis/laboranbindung)

### Aeskulap (Kern Concept AG) 🟢 DIRECT-HL7

- **Vendor**: Kern Concept AG, Windows-native.
- **Base tecnica**: KG con laboratorio integrato, interfacce dirette
  a laboratori Svizzeri "più comuni" + apparecchi laboratorio dello studio.
- **Protocollo verificato**: HL7 v2 nativo (MLLP), ordini elettronici
  a tutti i laboratori svizzeri via HL7.
- **Configurazione gateway**: output `mllp_hl7` verso IP:2575 default.
  Standard porta MLLP HL7, verificare col supporto tecnico Kern Concept.
- **Fonte**:
  - [Kern Concept — AESKULAP Ärztesoftware](https://kernconcept.ch/aerztesoftware/)
  - [Health-ICT — Aeskulap Support](https://www.health-ict.ch/praxissoftware/aeskulap-support/)

### WinMed (TMR AG, Basel) 🟢 DIRECT-HL7

- **Vendor**: TMR AG (spin-off Universität Basel, 1993), 861 clienti (2023).
- **Base tecnica**: soluzione modulare, moduli laboratorio, contabilità.
- **Protocollo verificato**: HL7 (dettaglio in Schnittstelle-Katalog);
  supporta trasferimento automatico laboratorio.
- **Configurazione gateway**: MLLP verso porta configurata via WinMed
  Konfiguration (chiedere al vendor la porta esatta, non pubblica).
- **Fonte**: [WinMed — Labor](https://www.winmed.ch/labor/)

### MediWin CB (Swisscom Health / TMR) 🟢 DIRECT-HL7

- **Base**: >10 000 utenti in Svizzera — probabilmente il gestionale più
  diffuso in DACH.
- **Protocollo**: HL7 v2 nativo, moduli custom per import laboratorio.
- **Configurazione gateway**: MLLP TCP; porta variabile per site.
- **Fonte**: [MediWin CB overview](https://avenios.ch/ratgeber/praxissoftware-anbieter-schweiz)

---

## 🇩🇪 Germania

### Tomedo (zollsoft GmbH, Jena) 🟡 FILE-DROP HL7/LDT

- **Vendor**: zollsoft GmbH, macOS-first + Windows.
- **Base tecnica**: **Import/Export directory** — Tomedo legge/scrive
  laboratorio in una cartella. Supporta LDT e **HL7**.
- **Protocollo verificato**:
  - **HL7 v2** via file drop (cartella condivisa Windows/Samba)
  - **LDT** (Labordatentransfer) formato tedesco standard
  - **GDT** per dispositivi
- **Configurazione gateway**: target di tipo **`file_drop`** verso path
  configurato. Il connector app di Tomedo prende in carico da lì.
- **Path tipici**: `\\tomedo-server\labor\import\` e `.../export/`
- **Fonte**: [Tomedo — Labordatentransfer](https://support.tomedo.de/handbuch/tomedo/labor/labordatentransfer/)
- **Case study**: [System-Helden — Tomedo Schnittstellen](https://system-helden.de/tomedo-schnittstellen-medizinische-geraete/)

### CGM TURBOMED / curaMED (CompuGroup Medical) 🟢 DIRECT-HL7 + 🟡 GDT/LDT

- **Vendor**: CompuGroup Medical (leader tedesco), sede Koblenz.
- **Base tecnica**: Windows Server + client, moduli per specialista.
- **Protocollo verificato**:
  - **HL7 v2 nativo** (LabInterface)
  - **GDT** per dispositivi (formato tedesco)
  - **LDT** per laboratori esterni
- **Configurazione gateway**: MLLP HL7. Porta di default non pubblica
  — configurabile dal modulo LabInterface.
- **Modulo LabInterface**: aggiuntivo, ~500-1500 EUR una tantum.
- **Fonte**:
  - [CGM Knowledge Base](https://support.cgm.com/CGM_TURBOMED/)
  - [Praxissoftware-Vergleich — CGM TurboMED](https://praxissoftwarevergleich.de/praxissoftware/cgm-turbomed/)

---

## 🇦🇹 Austria

- Il mercato austriaco usa principalmente **Tomedo** (zollsoft) e
  **CGM TURBOMED** — la configurazione è identica alla Germania.
- Alternative locali: **Innomed** (Wien), **BFH** — richiedono contatto
  vendor per i dettagli HL7.

---

## Ricapitolazione porte e configurazione gateway

Nel `gateway.yaml`, la sezione `outputs` per ogni gestionale:

```yaml
outputs:
  # Vitomed via file drop
  - name: "Vitomed produzione"
    kind: file_drop
    path: "/mnt/vitomed/import"       # SFTP-mounted cartella
    format: "hl7_v2"

  # Aeskulap via MLLP HL7
  - name: "Aeskulap produzione"
    kind: mllp_hl7
    host: "192.168.1.50"
    port: 2575                        # verificare col vendor

  # Tomedo via file drop
  - name: "Tomedo produzione"
    kind: file_drop
    path: "/mnt/tomedo/labor/import"
    format: "hl7_v2"

  # CGM TURBOMED via HL7 MLLP
  - name: "TurboMED produzione"
    kind: mllp_hl7
    host: "192.168.1.60"
    port: 2100                        # tipico ma verificare
```

## Note di installazione

**Il tempo per attivare l'HL7 nel gestionale** dipende molto dal vendor:

| Gestionale | Tempo attivazione | Costo tipico | Note |
|-----------|-------------------|--------------|------|
| Tomedo | ~1 ora, incluso | 0 | Solo setup cartella condivisa |
| Vitomed | 2-4 ore | 0-500 CHF | Modulo laboratorio + config connector |
| Aeskulap | 2 ore | Incluso in setup | Contatto Kern Concept per porta |
| WinMed | 4-8 ore | ~500-1000 CHF | Modulo Labor esterno |
| MediWin | 2-4 ore | ~500 CHF | Modulo lab integration |
| CGM TURBOMED | 4-8 ore | ~500-1500 EUR | Modulo LabInterface separato |

## Come confermare la configurazione con il vendor

Per ogni gestionale, chiedere al fornitore del PIS:

1. **Porta HL7 MLLP** su cui il gestionale ascolta
2. **Autenticazione** richiesta (basic auth? TLS? niente?)
3. **Versione HL7** attesa (2.3 / 2.5 / 2.7)
4. **MSH-3** (Sending Application) — nome che il gestionale filtra
5. **Formato del sample_id** atteso (numerico? alfanumerico?)
6. **Comportamento sui duplicati** (respinge? sovrascrive?)
7. **Test suite** o mock endpoint da usare in staging
