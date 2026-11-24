# Field Validation Checklist — Nuova installazione

**Da compilare e firmare dal tecnico** dopo l'installazione fisica del device
in praxis. Ogni checklist completata sposta il device di categoria
(BRONZE → SILVER → GOLD → PLATINUM) nel report `docs/devices/CERTIFICATION.md`.

Copia questo file in `logs/field_validation.json` con la struttura riportata
in fondo dopo aver completato tutti i punti.

---

## Dati installazione

| Campo | Valore |
|-------|--------|
| Praxis / Studio | |
| Device model | |
| Serial number del device | |
| Gateway hostname | |
| Data installazione | YYYY-MM-DD |
| Tecnico installatore | Nome + firma |
| Tecnico Sysmex/Roche/... coinvolto | Nome + azienda |

---

## Checklist tecnica — 15 punti da spuntare

### Sezione 1 — Connettività (5 min)

- [ ] **1.1** Cavo fisico collegato (USB seriale o Ethernet)
- [ ] **1.2** Il tecnico ha impostato l'IPU/device sul protocollo giusto
  - Sysmex XQ-320: ASTM E1381-02 + ACK/NAK
  - Cobas b101: POCT1-A2 su USB
  - UC-1000: RS-232 9600 8-N-1 senza handshake
  - Altri: vedi `docs/devices/RESEARCH.md`
- [ ] **1.3** Ping tra device e gateway funziona (se TCP)
- [ ] **1.4** La porta TCP configurata è raggiungibile (`nc -zv <gateway-ip> <port>`)
- [ ] **1.5** Firewall del router non blocca la porta

### Sezione 2 — Trasmissione (10 min)

- [ ] **2.1** Fai un test reale su un campione di controllo (QC)
- [ ] **2.2** Nel Web UI del gateway (`/`), la tessera del device diventa verde entro 30s
- [ ] **2.3** Nel Web UI, sezione "Risultati di oggi" appare il campione appena inviato
- [ ] **2.4** Il conteggio "Analisi oggi" incrementa
- [ ] **2.5** Nessun messaggio d'errore rosso in "Log di sistema" durante il test

### Sezione 3 — Ricezione al gestionale (10 min)

- [ ] **3.1** Apri il gestionale del medico (Tomedo, Vitomed, curaMED, etc.)
- [ ] **3.2** Il risultato del QC appare nella cartella paziente del QC
- [ ] **3.3** I valori sono uguali a quelli mostrati sul display del device
- [ ] **3.4** Le unità di misura sono corrette (mg/dL vs mmol/L, etc.)
- [ ] **3.5** Il flag di normalità (H/L/N) appare corretto nel gestionale

---

## Test di robustezza (opzionali, +15 min)

- [ ] **4.1** Stacca il cavo LIS/HIS, fai un test → il risultato appare in `/dlq`
- [ ] **4.2** Riattacca il cavo → il DLQ svuota entro 60s (retry automatico)
- [ ] **4.3** Riavvia il gateway (`sudo systemctl restart jerumednexus-gateway`) →
      tutto torna funzionante entro 60s senza intervento manuale
- [ ] **4.4** Fai due test consecutivi sullo stesso paziente (repeat) →
      **entrambi** arrivano al gestionale (non deduplicati)
- [ ] **4.5** Controlla che `/inspect/<sample_id>` mostri il payload raw + audit

---

## Firme

| Ruolo | Nome | Firma | Data |
|-------|------|-------|------|
| Tecnico installatore | | | |
| Responsabile praxis | | | |
| Rappresentante vendor device (se presente) | | | |

---

## Registrazione nel sistema

Copia i valori in `logs/field_validation.json`:

```json
{
  "sysmex_xq320": {
    "praxis":       "Hausarztpraxis Rossi",
    "device_serial": "12345678",
    "installed_at": "2026-08-28",
    "installer":    "Dr. Meier",
    "checks_completed": 15,
    "checks_optional_completed": 5,
    "signed_off":   true,
    "notes":        "Test QC OK, tempo end-to-end 180ms P95"
  }
}
```

Al prossimo run di `python -m tools.device_certification` il device
passerà a **PLATINUM** (💎) nel report ufficiale.

## Cosa succede dopo

- Il device è ora **certified** per quella praxis
- Se un altro cliente installa lo stesso modello, non serve rifare tutta
  la checklist — la vendor conserva la firma originale
- Il device compatibility matrix mostra il badge PLATINUM sul sito
  `docs.jerumednexus.example`
