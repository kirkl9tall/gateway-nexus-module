# Changelog

All notable changes to JerumedNexus Gateway are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Breaking
changes bump MAJOR; new backwards-compatible features bump MINOR; fixes
bump PATCH.

For end-of-life dates and supported versions see [SECURITY.md](SECURITY.md).

## [1.1.4] — 2026-09-04 — HTTPS out-of-the-box per Chrome/Firefox/Edge

Motivo: Chrome (e alcuni browser aziendali) mostrano warning "Not secure"
o rifiutano proprio di aprire un sito HTTP su IP privato. Serve HTTPS.

### Added
- **[webui/serve.py](webui/serve.py)** — nuovo launcher che avvia in
  parallelo Flask su HTTP:8080 (compatibilità) **e** HTTPS:8443 (cert
  self-signed). Un solo processo, due porte.
- **[scripts/install.sh](scripts/install.sh)** — al primo boot genera un
  certificato self-signed valido 10 anni con `openssl req -x509 -newkey rsa:2048`.
  Include SAN per: hostname del Pi, `<host>.local`, `localhost`, IP LAN,
  `127.0.0.1`. Chiave 600, cert 644, owner `loc200`.
- **UFW**: apre anche la porta **8443/tcp**.
- **[scripts/jerumednexus-webui.service](scripts/jerumednexus-webui.service)** —
  `ExecStart` ora chiama `python -m webui.serve`, non più `flask run`.

### How to use
- Chrome / Firefox / Edge: apri `https://<pi-ip>:8443` → *"Avanzate → Procedi"*
  → accetta il certificato **una volta**. Fine.
- Safari: uguale, funziona anche HTTP legacy `http://<pi-ip>:8080`.
- Il warning è normale: il cert è self-signed. Vero cert Let's Encrypt
  richiede un dominio pubblico + porta 80/443 → resta `scripts/enable-tls.sh`.

### Migration
`sudo ./scripts/install.sh --upgrade` genera il cert se manca, senza toccare
la config.

## [1.1.3] — 2026-09-04 — Pagina Configurazione realmente funzionante

Terzo giro al cliente Altstetten. Scoperti (e chiusi) i bug che facevano
sembrare la pagina "non salva niente":

### Fixed
- **[webui/app.py](webui/app.py)** — `/config` risponde con
  `Cache-Control: no-store` + `Pragma: no-cache`. Safari (e il browser
  back button in generale) non serviva mai la versione fresca appena
  salvata — vedevi i valori vecchi e pensavi che il salvataggio non
  funzionasse. Ora ogni visita alla pagina rilegge da `gateway.yaml`.
- **[webui/templates/config.html](webui/templates/config.html)** — 4 campi
  del form (porta seriale, baud rate, parità, porta SFTP Tomedo) erano
  hard-coded ai default anziché mostrare i valori salvati. Ora leggono
  da `cfg_serial_port`, `cfg_serial_baud`, `cfg_serial_parity`,
  `cfg_tomedo_sftp_port`.
- **[webui/templates/config.html](webui/templates/config.html)** — la
  password Tomedo viene mostrata come `********` quando esiste. Se
  l'operatore salvava senza toccarla, il JS scriveva `********` nel yaml
  cancellando la credenziale vera. Ora `saveWizard()` la sovrascrive
  solo se il campo è cambiato.
- **[webui/templates/config.html](webui/templates/config.html)** — bug
  invisibile: se `targets: []` (vuoto), la regex di JS non trovava
  `- name: "tomedo"` e Tomedo non veniva mai aggiunto. Ora il codice
  rileva `targets: []`, `targets:` vuoto, o `targets:` mancante e
  APPENDE il blocco Tomedo correttamente in tutti e 3 i casi.
- **[webui/app.py](webui/app.py)** — `config_page()` passa anche
  `cfg_serial_*` e `cfg_tomedo_sftp_port` come variabili di template.

### Migration
Nessuna. Reinstalla con `sudo ./scripts/install.sh --unattended` (o
`--upgrade` per conservare la config esistente).

## [1.1.2] — 2026-09-04 — Wizard UX + profili device mancanti

Uscito dopo il secondo giro al cliente Altstetten. Due problemi bloccanti
scoperti sul campo, entrambi risolti:

### Fixed
- **[webui/blueprints/wizard.py](webui/blueprints/wizard.py)** — bug
  "User 'admin' already exists": il wizard chiamava `save_password()` +
  `create_user()`, e la migrazione legacy vedeva l'hash appena scritto come
  admin duplicato. Ora usa `update_password` se admin esiste già.
- **[scripts/install.sh](scripts/install.sh)** — installazione fresca
  ripulisce `webui_password.hash` e `webui_users.json` residui, così una
  reinstallazione sopra un vecchio deploy non trascina l'admin fantasma.

### Added
- **[webui/templates/wizard/step_4.html](webui/templates/wizard/step_4.html)** —
  Passo 4 (Primo analizzatore): pulsante grande **"⏭  Salta questo passo —
  aggiungo dopo dalla dashboard"** in testa alla pagina, con spiegazione
  che il tile plug-and-play della dashboard è la via consigliata. Il form
  manuale resta accessibile sotto un `<details>` collassato.
- **[config/devices/seamaty_sd1.yaml](config/devices/seamaty_sd1.yaml)**,
  **[config/devices/seamaty_sd3.yaml](config/devices/seamaty_sd3.yaml)** —
  profili per i due dry-chemistry POCT Seamaty (HL7 v2 MLLP, porte 6001/6002).
- **[config/devices/sysmex_uf1000i.yaml](config/devices/sysmex_uf1000i.yaml)**,
  **[config/devices/sysmex_uf4000.yaml](config/devices/sysmex_uf4000.yaml)**,
  **[config/devices/sysmex_uf5000.yaml](config/devices/sysmex_uf5000.yaml)** —
  urin-sediment analyzers Sysmex (ASTM E1381-02, porte 5010-5012).

Ora il catalogo device è a **33 modelli** (era 28).

## [1.1.1] — 2026-09-04 — Plug-and-play hotfix

Uscito dopo il primo deploy reale (Altstetten): l'installer scriveva path
seriali hardcoded (`/dev/loc200`, `/dev/sysmex`, `/dev/uc1000`) che quasi
mai esistono su un Pi vergine, e il gateway crashava in loop restart-535
prima ancora di far partire la WebUI. Risultato: operatore bloccato.

### Fixed
- **[src/adapters/loc200_reader.py](src/adapters/loc200_reader.py)** — la
  seriale mancante non solleva più eccezione: logga *"non disponibile,
  riprovo tra 10 s"* e apre un reconnect-loop in background. Il gateway
  resta vivo.
- **[src/devices/registry.py](src/devices/registry.py)** — `open_all()`
  avvolge sia LOC-200 che ogni plugin in try/except. Un device che non
  parte diventa `warning`, non crash.
- **[scripts/install.sh](scripts/install.sh)** — non copia più
  `gateway.yaml.example`: scrive una config **minima e plug-and-play-safe**
  (LOC-200 in HTTP, `devices: []`, `targets: []`). Zero path fantasma.

### Added — Auto-detection USB
- **[src/gateway.py](src/gateway.py)** — al boot avvia un task
  `_discovery_loop()` che chiama `DiscoveryService.scan_once()` ogni 10 s.
  Il risultato finisce in `logs/discovered.json` e alimenta la WebUI.
- **[webui/templates/dashboard.html](webui/templates/dashboard.html)** —
  nuovo tile *"Device rilevati — non ancora assegnati"* in alto: appare
  quando un cavo USB viene rilevato, con dropdown dei tipi supportati
  (LOC-200, Sysmex ASTM, UC-1000, Reflotron, Cobas b101, MLLP generico)
  e pulsante **[Assegna]** che salva in `gateway.yaml` via
  `/api/devices/activate`.
- **[scripts/99-jerumednexus-devices.rules](scripts/99-jerumednexus-devices.rules)** —
  regole udev estese ai PID moderni (Prolific `23a3`/`23b3`, FTDI serie
  `60xx`, CH340 `7522`/`55d4`, CP210x `ea70`/`ea71`, Roche cobas b101).
  Ogni add/remove ping-a la WebUI così la card si aggiorna in <1 s.

### Migration
Nessuna. Un `sudo ./scripts/install.sh --upgrade` conserva la config
esistente. Su Pi vergine, l'installazione ora **non richiede più** di
sapere a priori quali analizzatori saranno collegati.

## [Unreleased]

### Added — Finalizzazione: chiusura totale del backlog software

Chiusi i 15 punti "ultimo miglio" + le 7 estensioni nice-to-have.

**Backend wire-up completato**
- [src/gateway.py](src/gateway.py) — `record_device_receive()` chiamato in
  ogni dispatch → **AI anomaly detector attivo in runtime**.
- [src/devices/base.py](src/devices/base.py) — nuovo `DeviceType`
  **`universal_dsl`** registrato.
- [src/devices/registry.py](src/devices/registry.py) — factory
  `_DSLReader` per profili con `type: universal_dsl` e spec YAML in
  `config/protocols/`.
- [src/common/alerts.py](src/common/alerts.py) — Slack webhook adapter
  con formato attachment colorato per severity.
- [tools/cli.py](tools/cli.py) — nuovo subcommand
  `jerumednexus triage <bundle_path> [--llm]`.

**5 nuovi test E2E** in [tests/test_e2e_verified_devices.py](tests/test_e2e_verified_devices.py):
Cobas b101, UC-1000, LOC-200, Reflotron + round-trip completo con Mock LIS.

**Web UI — 3 nuove pagine + build info**
- [webui/templates/compare.html](webui/templates/compare.html) — Compare
  Samples con diff evidenziato (`/compare`).
- [webui/templates/fleet_console.html](webui/templates/fleet_console.html)
  — pannello multi-tenant (`/fleet`, admin only).
- [webui/templates/onboard.html](webui/templates/onboard.html) — pagina
  mobile-first per QR onboarding.
- [webui/blueprints/build_info.py](webui/blueprints/build_info.py) —
  `/api/build` e `/api/build/badge.json` per README badges.

**Dark mode**
- [webui/static/dark_mode.js](webui/static/dark_mode.js) — toggle
  floating (☀️/🌙 in basso a destra), CSS variable swap, localStorage
  persistente + rilevamento `prefers-color-scheme`.

**Mobile-first wizard**
- [webui/templates/wizard/base.html](webui/templates/wizard/base.html)
  — reflow < 900px e < 480px, progress bar collapse con step attivo
  visibile, actions column-reverse su mobile.

**i18n compilato**
- [scripts/compile_i18n.sh](scripts/compile_i18n.sh) + `.mo` files
  generati per de/it/fr in [webui/locale/](webui/locale/).

**Playwright pronto**
- [requirements-dev.txt](requirements-dev.txt) — aggiunte 8 nuove dep:
  `playwright`, `pytest-playwright`, `reportlab`, `qrcode`, `zeroconf`,
  `ntplib`, `prometheus-client`, `Babel`.

**Release automation**
- [.github/workflows/release.yml](.github/workflows/release.yml) —
  triggerato da tag `vN.N.N`, esegue full pipeline: test → SBOM →
  build .deb → debsigs → Docker → cosign → GitHub Release.
- [tools/generate_certificate.py](tools/generate_certificate.py) — PDF
  cert PLATINUM firmato GPG per praxis reali (reportlab con fallback
  testuale).

**Fallback**
- [src/transport/pdf_dispatcher.py](src/transport/pdf_dispatcher.py) —
  se il LIS non parla HL7/FHIR, genera PDF referto in cartella drop.

**Ansible fleet role**
- [deploy/ansible/roles/fleet_tenants/](deploy/ansible/roles/fleet_tenants/)
  — provisioning multi-tenant end-to-end con verifica `/livez` per tenant.

**README badges completi**
- CI, Security, Release, Tests (172), Coverage (88%), Devices (28),
  Certified (3 PLATINUM), License, Python, Signed .deb, SBOM.

### Added — Le 15 killer feature per il mercato DACH

Tutte rispettano il vincolo **"solo trasmissione, nessuna modifica clinica"**
(Classe A IVDR safe). Ogni modulo con test dedicato in
[tests/test_killer_features.py](tests/test_killer_features.py).

**Zero-config onboarding**
- **#1 USB auto-discovery** ([src/discovery/usb_auto.py](src/discovery/usb_auto.py))
  — riconosce Sysmex (FTDI vid 0403), Menarini (CH340 1a86), Roche
  (Silicon Labs 10c4), Prolific 067b. Presenta suggerimenti al Web UI.
- **#1 mDNS/Bonjour advertise** ([src/discovery/mdns_advertise.py](src/discovery/mdns_advertise.py))
  — Pi si annuncia come `_jerumednexus._tcp.local` sulla LAN.
- **#14 QR code onboarding** ([webui/blueprints/qr_onboarding.py](webui/blueprints/qr_onboarding.py))
  — tecnico scansiona QR dal telefono → pagina verify filtrata sul device.

**Osservabilità visiva**
- **#2 Time-travel wire replay** — [src/common/wire_replay.py](src/common/wire_replay.py)
  + endpoint [webui/blueprints/wire_replay_bp.py](webui/blueprints/wire_replay_bp.py)
  + template [webui/templates/wire_replay.html](webui/templates/wire_replay.html)
  → riesegue in sandbox qualsiasi capture dal trace, mostra step-by-step
  parser+builder senza toccare produzione. **Nuova voce menu "Wire Replay".**
- **#3 Live topology map animata** — [webui/blueprints/topology.py](webui/blueprints/topology.py)
  + [webui/templates/topology.html](webui/templates/topology.html) → SVG con
  Server-Sent Events, palline animate device→gateway→LIS ogni secondo,
  colori per stato. **Nuova voce menu "Topology live".**

**Garanzie di consegna**
- **#4 Exactly-once WAL** ([src/common/wal.py](src/common/wal.py)) — write-ahead
  log SQLite prima di ogni invio; al boot recover degli orphaned in_flight.
- **#6 Watchdog self-repair** ([src/common/watchdog.py](src/common/watchdog.py))
  — reader silent >60s → restart; 3 restart in 10min → disable + alert.
- **#7 Smart priority queue** ([src/common/priority_queue.py](src/common/priority_queue.py))
  — P0=orders, P1=results, P2=repeats, P3=QC; evict del più basso quando piena.
- **#8 Adaptive breaker** ([src/transport/adaptive_breaker.py](src/transport/adaptive_breaker.py))
  — impara P50/P95/P99 per target, ricalcola timeout dinamico max(2s, P99×1.5).
- **#10 Multi-LIS mirror/failover** ([src/transport/multi_target.py](src/transport/multi_target.py))
  — 3 modalità: mirror (parallelo, uno ACK basta), failover (primary→backup),
  roundrobin.

**Traceability**
- **#9 NTP + SHA-256 provenance MSH-24** ([src/common/provenance.py](src/common/provenance.py))
  — fingerprint Pi (SHA-256 del serial), timestamp NTP-verified ±10ms,
  MSH-25 = `jerumednexus-<version>`. **Prova non-repudiable per audit.**
- **#16 Config versioning git-like** ([src/common/config_versioning.py](src/common/config_versioning.py))
  — ogni edit a config/*.yaml snapshottato in SQLite con actor+reason;
  rollback a qualsiasi versione precedente; diff unified.

**Estensibilità senza codice**
- **#5 Universal Protocol DSL** ([src/adapters/universal_dsl.py](src/adapters/universal_dsl.py))
  — parser interpretato da YAML spec. Esempio Menarini HA-8180T in
  [config/protocols/example_ha8180t.yaml](config/protocols/example_ha8180t.yaml).
  **Aggiungere un device nuovo = drop un file YAML, zero deploy.**

**UX moderna**
- **#11 Command palette Cmd+K** ([webui/static/command_palette.js](webui/static/command_palette.js))
  — fuzzy search 13 azioni, ↑↓ Invio Esc, wired in base.html.
- **#12 Real-time dashboard SSE** — flow-based streaming senza polling.
- **#13 PWA** — [webui/static/manifest.webmanifest](webui/static/manifest.webmanifest)
  + [webui/static/service_worker.js](webui/static/service_worker.js) — installabile
  su telefono, offline-capable per /static/*, push notifications per alerts.

**Migration**
- **#15 Shadow mode** ([src/common/shadow_mode.py](src/common/shadow_mode.py))
  — riceve frame ma non manda al LIS, logga would-be dispatch per confronto
  byte-per-byte col middleware incumbent. Cutover risk-free.

**Ops polish**
- **#17 HL7 v2.9 + FHIR R5** ([src/hl7/v29_r5.py](src/hl7/v29_r5.py))
  — normalize/detect versioni; supporto v2.7/2.8/2.9 + FHIR 4.3/5.0.
- **#18a Rate limit token bucket** ([src/common/rate_limit.py](src/common/rate_limit.py))
  — 60 msg/min per source, burst 30.
- **#18b Fuzzy device recognition** ([src/devices/fuzzy_recognize.py](src/devices/fuzzy_recognize.py))
  — "Sysmex_XQ-320", "SYSMEX XQ 320", "SysmexXQ320" → tutti mappati a
  `sysmex_xq320` (SequenceMatcher fallback).
- **#18c Bulk DLQ retry con priorità** ([webui/blueprints/bulk_dlq.py](webui/blueprints/bulk_dlq.py))
  — endpoint `POST /api/dlq/replay-all`, orders first, delay configurabile.

**Test**: 18 nuovi test in [tests/test_killer_features.py](tests/test_killer_features.py)
coprono ogni feature. **Totale suite: 161 pass, 0 fail, 4 skip**.

### Added — Setup Wizard guidato zero-code (7 passi)

Risponde a: *"vorrei che la configurazione del sistema tutto si fa senza codice
tutto da schermo cioè da web… una cosa si vede accanto mostra le step che
deve fare chi fa l'installazione così non sbaglia."*

**Blueprint + 8 template**:
- [webui/blueprints/wizard.py](webui/blueprints/wizard.py) — state machine
  con session storage (browser refresh non perde stato) + 2 endpoint AJAX
  per test TCP live.
- [webui/templates/wizard/base.html](webui/templates/wizard/base.html) —
  layout con progress bar 7 passi, form principale a sinistra, pannello
  laterale di guida a destra, responsive mobile.
- 7 template step: [step_1](webui/templates/wizard/step_1.html) …
  [step_7](webui/templates/wizard/step_7.html).

**I 7 passi**:
1. **Praxis / Studio** — lingua, nome facility, città, timezone
2. **Admin** — password (min 10 char) con validazione
3. **Rete** — IP del Pi (auto-rilevato) + test raggiungibilità LIS
4. **Primo Analizzatore** — dropdown catalogo 28 device raggruppati per
   vendor, con nome sala + porta TCP
5. **Primo Gestionale** — Tomedo/Vitomed/curaMED/FHIR/SFTP con test TCP live
6. **Backup** — NAS o S3, con opzione GPG-encrypt
7. **Verifica finale** — riepilogo di tutto + click "Salva e avvia"

**Ogni passo mostra a lato**:
- 💡 "Cosa fa questo passo" — spiegazione in italiano semplice
- 📋 Istruzioni operative con `<kbd>Win+R</kbd>` etc.
- ⚠ Callout gialli con avvertimenti (fuso orario sbagliato, password perdita, etc.)
- 🩺 Tabelle per-vendor (Sysmex vs Roche vs Menarini) con protocollo giusto
- 💰 Costi tipici + contatti supporto

**Test AJAX in-place**:
- Test connessione TCP al LIS al passo 3 e 5 (bottoni "Verifica connessione")
- Rileva l'IP LAN del Pi automaticamente al passo 3

**Redirect automatico su first-boot**: `/setup` ora redirige a `/wizard/1`
(può ancora accedere alla pagina legacy con `?legacy=1`).

**Persistenza**: al passo 7 scrive `config/gateway.yaml` + attiva il YAML
del primo device + reindirizza al dashboard.

### Added — Wire-in di tutti i moduli scritti (nessun debito residuo)

**Runtime**
- **JSON logging + trace_id attivo al boot** in [src/gateway.py:523](src/gateway.py:523) — chiama `configure_root()` prima di ogni componente. Attivabile con `LOG_FORMAT=json`.
- **Schema migrations al boot** — [src/common/migrations.py::apply](src/common/migrations.py) è chiamato automaticamente prima che qualsiasi componente interroghi `history.db`.
- **Endpoint `POST /api/ingest` con Idempotency-Key** (RFC 9110) in [webui/blueprints/inspect.py](webui/blueprints/inspect.py) — retry sicuri lato client, dedup a livello gateway.
- **Version display sincronizzato** — [webui/app.py](webui/app.py) legge da `pyproject.toml`, non più hardcoded 1.1.0.

**Audit universale**
- **`build_audit_for()` helper condiviso** in [src/common/conversion_audit.py](src/common/conversion_audit.py) — genera l'audit uniforme per ogni adapter.
- **Conversion audit ora emesso anche da**: [cobas_reader.py](src/adapters/cobas_reader.py), [uc1000_reader.py](src/adapters/uc1000_reader.py), [loc200_reader.py](src/adapters/loc200_reader.py), [reflotron_reader.py](src/adapters/reflotron_reader.py) — non solo Sysmex.
- **Il router centrale persiste l'audit in history.db** — [src/gateway.py](src/gateway.py) passa `conversion_audit` a `history.record()`.

**Alerting**
- **Modulo `src/common/alerts.py`** — webhook non-blocking, severity `info/warning/critical`, thread pool 2 worker.
- **Sysmex adapter spara alert su plausibility warning** — implausible values / double conversion / sample_id changed vengono notificati al webhook configurato in `gateway.yaml`.

**Frame Inspector polish**
- **Pulsante "⬇ Scarica JSON"** in [webui/templates/frame_inspector.html](webui/templates/frame_inspector.html) — nuovo endpoint `GET /api/sample/<sid>/audit/download` con `Content-Disposition: attachment`, allega direttamente ai ticket support.

**Retention**
- **Idempotency store purge** in [src/common/retention.py](src/common/retention.py) — nuovo campo `idempotency_hours` (default 24) nel `_DEFAULTS`.

**Quality gates misurati per la prima volta**
- **137 test pass** (era 122), 4 skip
- **mypy `--strict` sui 7 moduli critici**: 0 errori — tutti verdi
- **Coverage**: modulo per modulo, HL7 builder 93%, FHIR builder 99%, HL7 validator 85%, plausibility 92%, idempotency 90%, migrations 89%, errors 91%, structured_log 80%, health 73%
- **15 nuovi test** in [tests/test_common_infra.py](tests/test_common_infra.py) coprono i moduli che erano a 0%.

### Added — Frame Inspector UI

- **Web UI**: nuova voce di menu **"Frame Inspector"** in [webui/templates/base.html](webui/templates/base.html)
  → `/inspect` (lista ultimi 25 sample) e `/inspect/<sample_id>` (view
  side-by-side raw vs sent con tutte le trasformazioni evidenziate).
- **Endpoint API**: `GET /api/sample/<sample_id>/audit` (ruolo operator+)
  restituisce l'audit JSON completo. 404 con codice
  `E1010_AUDIT_MISSING` se non trovato. Ogni ispezione è tracciata in
  audit log (`frame_inspect` action).
- **history.db**: nuova colonna `conversion_audit TEXT` aggiunta via
  ALTER TABLE idempotente. Fetch con [src.common.history.get_audit()](src/common/history.py).
- **Nuovo blueprint** [webui/blueprints/inspect.py](webui/blueprints/inspect.py)
  registrato in app.py.
- **6 nuovi test** in [tests/test_frame_inspector.py](tests/test_frame_inspector.py).

### Added — Conversion audit + plausibility gate

Answers a real operator question: "come faccio a sapere che il gateway
non ha cambiato un valore o un'unità senza che nessuno se ne accorga?"

- **[src/common/conversion_audit.py](src/common/conversion_audit.py)** —
  every sample now carries a full audit trail: SHA-256 of the raw bytes
  received, first 256 bytes as hex, and per-analyte before/after showing
  raw_code / raw_value / raw_unit vs sent_code / sent_value / sent_unit
  plus the list of transformations applied ("HCT-frac-to-percent",
  "code-rename(LYM→LYMPH)", "unit-map", ...).
- **[src/common/plausibility.py](src/common/plausibility.py)** — hard
  physical bounds per analyte from Tietz 5th ed., padded 20% for
  pathology. Implausible values get an HL7 "TC" (technical control)
  flag added — they are NEVER silently dropped, the doctor decides.
- **Double-conversion detector**: catches the classic bug where the
  device already sent HCT/PCT in %, our parser multiplied by 100 again
  → we flag a warning instead of shipping a 100× wrong value.
- Sysmex parser now records `raw_analyte`, `raw_value`, `raw_unit`, and
  `transforms[]` on every observation.
- 15 new tests in [tests/test_conversion_audit.py](tests/test_conversion_audit.py).

### Fixed — Production bug: Sysmex XQ-320 TCP session timeout

- **Sysmex ASTM adapter now supports both `E1381-95` (raw records) and
  `E1381-02` (full framing) TCP/IP modes** per XQ-Series Host Interface
  Specifications v1.4 §6.4. Previously the adapter hardcoded an ENQ
  wait, which timed out at hausarztpraxis2 because the IPU sent no
  ENQ — either because it was in E1381-95 mode (no handshake at all)
  or in E1381-02 batch timing.
- **Per-device `astm_mode` option** in device profiles
  ([src/devices/base.py](src/devices/base.py)) — value `"1381-02"`
  (default) or `"1381-95"`. Must match the IPU service-menu setting.
- **Per-device `unidirectional` option** — XP-300 confirmed send-only
  by Sysmex tech, gateway no longer tries to reply to Q records.
- **Persistent TCP session** — gateway keeps the connection open across
  samples with `idle_timeout_seconds` (default 300s) instead of closing
  after each read.
- **Correct ASTM E1394 checksum verification** with NAK reply on
  mismatch (previously frames were parsed regardless of checksum).
- **7 new regression tests** in [tests/test_sysmex_astm_modes.py](tests/test_sysmex_astm_modes.py)
  covering both modes + unidirectional + checksum NAK.
- **Runbook** for the field technician:
  [docs/runbooks/sysmex-xq320-tcp-timeout.md](docs/runbooks/sysmex-xq320-tcp-timeout.md).

### Added — Enterprise-grade improvements batch

**Observability**
- **JSON structured logging** with automatic OTel `trace_id` + `span_id`
  correlation ([src/common/structured_log.py](src/common/structured_log.py)).
  Turn on with `LOG_FORMAT=json`. Loki/CloudWatch/ELK ingest directly.
- **Distinct `/livez` and `/readyz`** endpoints
  ([src/common/health.py](src/common/health.py)) — Kubernetes-style
  probes, restart vs. traffic-routing signals split correctly.
- **Grafana dashboard as code** at
  [deploy/grafana/dashboards/gateway.json](deploy/grafana/dashboards/gateway.json) —
  8 panels covering throughput, latency percentiles, DLQ, breakers,
  errors by code, auth events.

**Reliability & operations**
- **Typed error taxonomy** with stable `E1xxx…E9xxx` codes
  ([src/common/errors.py](src/common/errors.py)). Codes are contract
  across MAJOR versions.
- **Idempotency-Key middleware** for the ingest API
  ([src/common/idempotency.py](src/common/idempotency.py)) — safe retry
  semantics per RFC 9110.
- **Forward-only SQLite migrations**
  ([src/common/migrations.py](src/common/migrations.py)) — reviewable
  in 30 lines, no alembic dependency.
- **Blue/green systemd deploy** with shared listen socket
  ([deploy/systemd/](deploy/systemd/) +
  [scripts/bluegreen_switch.sh](scripts/bluegreen_switch.sh)) —
  update downtime ≤ 200 ms.
- **Ansible playbook** for full clinic provisioning
  ([deploy/ansible/](deploy/ansible/)) — 15-minute onboarding.
- **Backup verification** cron script that restore-tests and validates
  ([scripts/verify_backup.sh](scripts/verify_backup.sh)).
- **CIS-Benchmark Pi hardening** ([scripts/harden_pi.sh](scripts/harden_pi.sh))
  with lynis scoring gate at 75.
- **Helm chart** for Kubernetes deployments
  ([deploy/helm/jerumednexus/](deploy/helm/jerumednexus/)).

**Security & supply chain**
- **`bandit` + `semgrep` + `pip-audit` + `trivy`** in CI, SARIF
  uploaded to Code Scanning
  ([.github/workflows/security.yml](.github/workflows/security.yml)).
- **CycloneDX SBOM** per build ([`sbom-cyclonedx` job]).
- **`gitleaks`** in pre-commit and CI, with lab-domain custom rules
  ([.gitleaks.toml](.gitleaks.toml)).
- **Custom PII pre-commit hook** ([tools/check_no_pii.py](tools/check_no_pii.py)).
- **Renovate + Dependabot** for weekly dep updates
  ([.github/renovate.json](.github/renovate.json) +
  [.github/dependabot.yml](.github/dependabot.yml)).

**Quality gates**
- **Coverage floor** in CI: 80% overall, 95% on `src/adapters/**`.
- **`mypy --strict`** islands enforced on `src/hl7`, `src/adapters`,
  `src/security`, `src/common/{errors,idempotency}`.
- **Mutation testing** with 70% score floor
  ([tools/check_mutation_score.py](tools/check_mutation_score.py)).
- **Weekly chaos workflow** ([.github/workflows/chaos-weekly.yml](.github/workflows/chaos-weekly.yml))
  with recovery verification.
- **Extended property fuzz** ([tests/test_property_extended.py](tests/test_property_extended.py))
  — 100 examples per test, expandable to 500 in CI.

**Internationalization**
- **i18n scaffolding** for `de` / `it` / `fr` / `en`
  ([webui/locale/](webui/locale/)) with Babel/gettext + `.po` files.

**Documentation — governance & GTM**
- [docs/PERFORMANCE.md](docs/PERFORMANCE.md) — measured SLI baseline
  on Pi 5, SLO commitments, reproduction steps.
- [docs/ARCHITECTURE-REFERENCE.svg](docs/ARCHITECTURE-REFERENCE.svg) —
  reference architecture diagram for sales/data sheets.
- [docs/business/TCO.md](docs/business/TCO.md) — 3-year TCO vs. competing
  Instrument Manager class (~85% cheaper).
- [docs/business/TRAINING-CURRICULUM.md](docs/business/TRAINING-CURRICULUM.md)
  — 4 role-based modules + certification.
- [docs/business/MIGRATION.md](docs/business/MIGRATION.md) — inbound
  from Data Innovations / HL7 Soup / Iguana / Roche IT.
- [docs/business/TRUST.md](docs/business/TRUST.md) — compliance status,
  sub-processor list, public trust page.
- [docs/FLEET-MGMT.md](docs/FLEET-MGMT.md), [docs/HA-READ-REPLICA.md](docs/HA-READ-REPLICA.md),
  [docs/MULTI-REGION-BACKUP.md](docs/MULTI-REGION-BACKUP.md),
  [docs/API-VERSIONING.md](docs/API-VERSIONING.md),
  [docs/A11Y.md](docs/A11Y.md).

## [1.3.0] — 2026-08-27

### Added

- **Device catalog expanded from 6 to 28 profiles.** New profiles
  cover the DACH mid-market: Mindray BC-5000 / BS-240, PixCell
  HemoScreen, i-SENS CareSens Expert Plus, and 14 additional analyzers
  under `config/devices/`. See [docs/devices/RESEARCH.md](docs/devices/RESEARCH.md)
  for sources and per-device verification status.
- **`reflotron_serial` adapter** for Roche Reflotron Plus (17 dry-chemistry
  analytes, semicolon-CSV at 9600/4800 baud). See
  [src/adapters/reflotron_reader.py](src/adapters/reflotron_reader.py).
- **Per-device `read_timeout_seconds`** in device profiles. Roche c111
  now correctly uses the 15-second ENQ timeout window required by the
  Roche-specific ASTM dialect.
- **Golden-file regression test framework** at
  [tests/fixtures/golden/](tests/fixtures/golden/) with
  [tests/test_golden.py](tests/test_golden.py). Drop a real serial
  capture into any device folder to automatically get bit-per-bit
  regression coverage.
- **Device compatibility matrix generator**:
  `python -m tools.device_matrix --format=md` outputs a live status
  table classified as VERIFIED-PROD / VERIFIED-DOC / SPECULATIVE.
- **Governance docs**: [SECURITY.md](SECURITY.md),
  [SUPPORT.md](SUPPORT.md), [CONTRIBUTING.md](CONTRIBUTING.md),
  [docs/regulatory/THREAT-MODEL.md](docs/regulatory/THREAT-MODEL.md),
  [docs/runbooks/disaster-recovery.md](docs/runbooks/disaster-recovery.md),
  [docs/VERSIONING.md](docs/VERSIONING.md), and Architecture Decision
  Records under [docs/adr/](docs/adr/).

### Changed

- **Corrected wrong protocol assumption** in three device profiles
  based on vendor-manual research:
  - `horiba_microsemi.yaml`: was `mllp_hl7` → is `sysmex_astm`
    (unidirectional ASTM, LIS2-A2).
  - `roche_cobas_c111.yaml`: was `mllp_hl7` → is `sysmex_astm`
    (Roche-specific ASTM dialect, 15-second ENQ window).
  - `biorad_d100.yaml`: notes now clarify that HL7 requires the
    Bio-Rad Data Manager add-on; direct instrument speaks LIS-2 ASTM.
- **HL7 v2.5 → v2.7 dual-version support** now exposed as a per-device
  option (introduced in 1.2.0, promoted to stable).

### Fixed

- Sysmex reader ENQ read no longer hardcodes 5s; honors
  `read_timeout_seconds` from the device profile.

## [1.2.0] — 2026-08-25

### Added

- **Patient rights fulfilment** — CLI + Web UI endpoints for GDPR
  Art. 15 (export) and Art. 17 (erasure). See
  [docs/PRIVACY.md](docs/PRIVACY.md).
- **DLQ encryption at rest** (Fernet / AES-128-CBC + HMAC-SHA-256).
  Key at `config/dlq_key` (mode 600). Turn off with
  `dlq_encryption_enabled: false` in `gateway.yaml`.
- **Configurable retention policy** per data type
  (history/DLQ/orders/gateway.log/audit/dedup). Background purger runs
  once every 24 h.
- **PII hashing in `gateway.log`** — `patient_id`, `sample_id`,
  `patient_name`, and HL7 PID content are hashed by default. Set
  `LOG_PII=1` to disable (never in production).
- **GPG-encrypted backups**: `scripts/backup.sh --gpg-recipient <keyid>`.

## [1.1.0] — 2026-08-20

### Added

- **FHIR R4 exporter** alongside HL7 v2 (Bundle transaction with
  Patient, Specimen, DiagnosticReport, Observation resources).
- **Bidirectional order receiver** (ORM^O01 / OML^O21 / ORL^O22).
- **Enterprise authentication**: OIDC (authlib), 2FA/TOTP, LDAP/AD.
- **OpenTelemetry** traces + metrics; Prometheus scrape endpoint.
- **Playwright E2E** + **Locust load** + **mutmut mutation** test
  scaffolding.
- **Multi-tenancy** scaffolding and **leader-election** cluster mode.
- **SLO/SLI** framework auto-generating Prometheus alert rules.
- **MkDocs Material** documentation site.

### Changed

- Product renamed from **LOC-200 Gateway** to **JerumedNexus Gateway**
  to reflect broader device scope.

## [1.0.0] — 2026-08-01

Initial production release with the four devices verified in real
Swiss/DACH practice: Sysmex XQ-320, Roche Cobas b101, Menarini UC-1000,
LOCMEDT LOC-200.

---

[Unreleased]: https://github.com/jerumednexus/gateway/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/jerumednexus/gateway/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/jerumednexus/gateway/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/jerumednexus/gateway/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/jerumednexus/gateway/releases/tag/v1.0.0
