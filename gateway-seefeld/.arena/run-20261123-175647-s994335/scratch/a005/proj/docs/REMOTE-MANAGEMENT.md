# Gestione remota della flotta

Come gestire N gateway JerumedNexus da un'unica console.
**Nessuna scelta è stata implementata ancora** — questo doc esiste per
decidere quale approccio adottare per la v1.2.

## Il problema

- Un cliente ha 3 sedi con 3 Raspberry Pi
- Un rivenditore ha 30 clienti
- Vuoi:
  - Vedere lo stato di tutti da una schermata sola
  - Aggiornare tutti a una nuova versione con un click
  - Fare debug remoto senza chiedere accesso VPN al cliente
  - Ricevere alert centralizzati

## Opzioni

### Opzione A — Reverse SSH tunnel (rapido, low-tech)

**Come funziona:** ogni Pi apre un tunnel SSH persistente verso un tuo server
centrale. Da lì fai `ssh loc200-clinic-1@central` e sei dentro.

**Pro:**
- 2 righe di cron, funziona in 1 giorno
- Nessun requisito lato cliente (basta uscita internet 22 o 443)
- Sicurezza gestita da OpenSSH (bene documentato)

**Contro:**
- Non è una console unificata — vedi 1 Pi alla volta
- Il tuo server centrale diventa punto di fallimento
- Nessuna dashboard aggregata

**Costo:** €10/mese VPS + 4 ore di setup.

### Opzione B — WireGuard mesh (rete privata unificata)

**Come funziona:** ogni Pi entra in una VPN WireGuard con IP fisso.
Da un tuo hub fisso vedi tutti come se fossero in LAN.

**Pro:**
- Puoi puntare Prometheus / Grafana centralizzato ai `/metrics` di ogni Pi
- Basso overhead (kernel-level VPN)
- Più moderno di SSH

**Contro:**
- Devi gestire chiavi + rotazione + firewall di ogni Pi
- Il tuo hub è ancora SPOF

**Costo:** €10/mese VPS + 1-2 giorni setup.

### Opzione C — MQTT broker centrale

**Come funziona:** ogni Pi pubblica stato/eventi/DLQ su un topic MQTT
`jerumednexus/<clinic-id>/…`. Un dashboard (Grafana o custom) sottoscrive.

**Pro:**
- Push-based, real-time
- Un solo canale in uscita (443 TLS)
- Bidirezionale — puoi anche mandare comandi dal centro (reload, restart)

**Contro:**
- Richiede modifiche al codice del gateway (client MQTT)
- MQTT broker HA è complicato

**Costo:** €30/mese broker (o EMQX self-hosted) + 1 settimana di lavoro.

### Opzione D — SaaS console (endgame commerciale)

**Come funziona:** i Pi mandano telemetria a jerumed-nexus.ch/console via
HTTPS (JWT-authenticated). La console mostra flotta, alert, remote-config,
log tail, remote SIGHUP, upgrade rollout con canary.

**Pro:**
- Vera esperienza enterprise
- Multi-tenant (ogni rivenditore vede solo i suoi)
- Base per fatturazione a consumo

**Contro:**
- 1-3 mesi di lavoro
- Devi mantenere backend, DB, availability
- Compliance (dati clienti che passano dal tuo cloud)

**Costo:** €500-2000/mese infrastruttura + effort dedicato.

## Raccomandazione a tappe

**Fase 1 (subito):** Opzione A — reverse SSH.
Ti sblocca il supporto remoto ai primi 5 clienti senza infrastruttura pesante.

**Fase 2 (a 10 clienti):** Opzione B — WireGuard + Prometheus centrale.
Ora hai dashboard aggregata, alert, ma niente ancora di commerciale visibile.

**Fase 3 (a 30+ clienti):** Opzione D — SaaS console.
A quel punto il fatturato giustifica il team che la mantiene.

## Cosa serve nel codice del gateway per abilitarle

Zero per A (è tutto lato server).
Piccole cose per B: `/metrics` già pronto, ma serve un flag per bindarlo
al WireGuard interface.
Per C serve un componente `src/telemetry/mqtt_pusher.py` — 1 file, ~200 righe.
Per D serve un componente `src/telemetry/console_client.py` con JWT + heartbeat + config pull.

Tutte queste **coesistono** con il codice attuale — non richiedono refactoring
di quello che c'è.

## Decisione

**Chi decide:** tu (product owner).
**Quando serve:** al secondo o terzo cliente reale.
**Come preparo il codice:** posso aggiungere hook point (`src/telemetry/__init__.py`
vuoto ora) così che quando decidi, il collegamento è mezz'ora di lavoro.
