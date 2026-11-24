# FAQ

## Installazione

**D: Su quale hardware gira?**
R: Raspberry Pi 3B+ / 4 / 5 con Raspberry Pi OS Bookworm o Debian 12.
Testato anche in container Docker (multi-arch).

**D: Posso installare senza SSH?**
R: Sì. Usa l'immagine Raspberry Pi pre-flashed
(`scripts/build-rpi-image.sh`) — al primo boot punti il browser al Pi e
il setup wizard fa il resto.

**D: Posso installare su Windows?**
R: Solo per sviluppo. La produzione richiede systemd / udev.

**D: Come aggiorno?**
R: Se hai installato via `.deb`:
`sudo apt install --only-upgrade jerumednexus-gateway`.
Se hai installato via `install.sh`: `sudo ./scripts/install.sh --upgrade`.
Config, log, DLQ e password sono preservati.

## Sicurezza

**D: Devo aprire porte su internet?**
R: **No.** Il gateway va sulla LAN della clinica. Nessuna porta pubblica.
Se serve accesso remoto per supporto, usa VPN / SSH tunnel.

**D: È sicuro contro attacchi?**
R: Vedi `SECURITY.md` per il threat model dettagliato. Difese principali:
bcrypt password (12 char min), CSRF, rate limit su login, Bearer token
sull'ingestion HTTP, systemd hardening, audit log con hash dei PID.

**D: Posso mettere HTTPS?**
R: Sì: `sudo ./scripts/enable-tls.sh <fqdn>` (Let's Encrypt) o
`sudo ./scripts/enable-tls.sh --self-signed` (LAN privata).

## Device

**D: Che analizzatori supporta?**
R: LOCMEDT LOC-200 (HTTP/serial/TCP), Sysmex XP-300 / XQ-320 / pocH-100i
(ASTM E1381), Menarini UC-1000 (RS-232), Roche Cobas b101 (POCT1-A2),
Seamaty SMT-120/SD1/SD3 (HL7 MLLP), Horiba Microsemi CRP (HL7 MLLP).
Qualsiasi altro device che parli HL7 v2 MLLP standard funziona con
`type: mllp_hl7`.

**D: Come aggiungo un nuovo device?**
R: Crea un YAML in `config/devices/<nome>.yaml`. Vedi
`config/devices/sysmex_xp300.yaml` come esempio. Per protocolli custom
serve un adapter Python nuovo (vedi CONTRIBUTING.md).

**D: Il gateway rileva i device automaticamente?**
R: Sì per USB (chipset FTDI/PL2303/CH340/CP210x) e per HL7-MLLP/ASTM/etc.
Vai in Web UI → Analizzatori → "Scansione USB" o "Scansione LAN".
Un badge nella sidebar segnala device rilevati non ancora attivati.

## Gestionali (PIS/LIS)

**D: Con quali gestionali funziona?**
R: Adapter dedicati per Vitomed, curaMED, Aeskulap, Axenita, WinMed,
DnaMed, Tomedo. Qualsiasi altro LIS che accetti HL7 v2 MLLP standard
funziona con `type: generic_hl7_mllp`.

**D: Non arrivano messaggi al mio Tomedo!**
R: Prima cosa, testa dalla Web UI: Config → bottone "Test invio" accanto
al target Tomedo. Se il test passa, il problema è nell'import Tomedo.
Se fallisce, il messaggio non lascia neanche il gateway → segui
[TROUBLESHOOTING.md](TROUBLESHOOTING.md) step 3.

**D: Il gateway modifica i valori clinici?**
R: **No, mai.** Il gateway fa solo traduzione di formato
(analyzer → HL7 v2.5). I valori numerici e le unità di misura passano
inalterati. L'unica trasformazione è la mappatura del flag
(UP/DOWN → H/L) — se il PIS a valle applica logica clinica su H/L, è
responsabilità loro.

## Operazioni

**D: Cosa sono i "Dead-letter"?**
R: Messaggi che non sono stati recapitati a nessun target dopo tutti
i retry. Persistiti su disco per replay manuale. Vai in Web UI → 
Dead-letter, clicca "Replay" per rispedire.

**D: Cosa succede se la rete cade?**
R: I messaggi in coda vengono trattenuti. Al ritorno della rete,
il retry esponenziale (fino a 60s per tentativo) li recapita.
Se un target è persistentemente giù, il circuit breaker si apre
(dopo 5 fallimenti consecutivi) e riprova dopo 60s.
Se anche così non passa, il messaggio finisce in DLQ.

**D: Come faccio a fare backup?**
R: `sudo ./scripts/backup.sh /mnt/nas/jerumednexus`. Copia config, DLQ,
audit log, history. Metti in cron per backup giornaliero.

**D: Ci sono metriche per Grafana?**
R: Sì. Endpoint `/metrics` in formato Prometheus. Vedi
[docs/prometheus/](prometheus/) per dashboard e alert rules pronti.

## Regolatorio

**D: È un dispositivo medico?**
R: Cade nell'IVDR (Regolamento UE 2017/746) **Classe A** perché il
flag mapping (`UP → H`, `DOWN → L`) è una trasformazione semantica.
La documentazione per la self-certification è in `docs/regulatory/`.
**Devi far revisionare tutto a un notified body IVDR prima di vendere.**

**D: È compliant con DSG/GDPR?**
R: Il gateway ha le misure tecniche adeguate (bcrypt, audit log, log
patient-ID-hashed, systemd hardening). Serve un DPA firmato tra te (come
processor) e la clinica (come controller). Template in
`docs/regulatory/DPA-TEMPLATE.md`.

## Supporto

**D: Come ricevo supporto?**
R: Vedi `SECURITY.md` per vulnerabilità di sicurezza.
Per bug: GitHub Issues. Per assistenza commerciale: info@jerumed-nexus.ch.
