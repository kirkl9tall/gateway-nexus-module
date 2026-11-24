---
name: Bug report
about: Segnala un difetto riproducibile
title: "[BUG] "
labels: bug
assignees: ''
---

## Descrizione
Riassunto in 1-2 frasi.

## Come riprodurlo
1. Vai a "..."
2. Clicca "..."
3. Vedi errore

## Comportamento atteso

## Ambiente
- Versione JerumedNexus: <output di `jerumednexus status` o dalla sidebar Web UI>
- OS: <Raspberry Pi OS / Debian / …>
- Deploy: <install.sh / .deb / Docker / RPi image>

## Log
Attacca `/opt/jerumednexus/logs/gateway.log` (ultime 200 righe) e
`logs/status.json`, **rimuovendo dati paziente** prima di postare.

## Impatto su pazienti / clinica?
- [ ] Nessuno (dev/lab environment)
- [ ] Interruzione risultati
- [ ] Dati errati sul PIS
- [ ] Altro: …

> Se impatta un paziente, usa canale di sicurezza (SECURITY.md), non issue pubblico.
