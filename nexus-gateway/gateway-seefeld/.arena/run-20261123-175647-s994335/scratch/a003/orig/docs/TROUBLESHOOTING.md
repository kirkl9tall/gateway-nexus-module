# Troubleshooting

Segui in ordine. Ogni step ha comandi copia-incolla e ti dice cosa
scartare se non è il problema.

## SINTOMO 1: "Non arrivano messaggi al gestionale"

```
1. Il gateway sta girando?
   sudo systemctl status jerumednexus-gateway
   ├── active (running)  → step 2
   └── failed / inactive → sudo journalctl -u jerumednexus-gateway -n 100
                            (leggi l'ultimo errore, poi step 4)

2. L'analizzatore sta parlando col gateway?
   sudo journalctl -u jerumednexus-gateway -f | grep "parsed:"
   ├── vedi righe "parsed: sample=..." → step 3
   └── silenzio da > 5 minuti          → step 5 (analizzatore)

3. Il gateway sta cercando di consegnare?
   sudo journalctl -u jerumednexus-gateway -f | grep -E "Delivering|FAILED|OK"
   ├── vedi "Delivered OK"              → step 6 (lato PIS)
   ├── vedi "FAILED" con timeout        → step 7 (rete)
   ├── vedi "AR" o "AE" in ACK          → step 8 (formato messaggio)
   └── vedi "Circuit breaker OPEN"      → step 9 (breaker aperto)

4. Il gateway crasha all'avvio
   sudo journalctl -u jerumednexus-gateway --no-pager | tail -50
   Cerca "ERROR" o "Traceback". Le cause più comuni:
   - config/gateway.yaml YAML mal formato       → aprire Web UI, tab Config
   - config/secrets.env mancante                → creare (min: LOC200_HTTP_TOKEN)
   - porta 5003 già in uso                      → sudo ss -tlnp | grep 5003

5. L'analizzatore non parla
   RS-232:
     ls /dev/ttyUSB*                → devi vedere il tuo adapter
     ls /dev/jerumednexus/          → symlink stabili udev
     sudo journalctl | grep tty     → messaggi kernel su collegamento USB
   HTTP (LOC-200):
     nel LOC-200 verifica l'IP del gateway e la porta (5003 default)
     verifica il Bearer token: deve essere quello in config/secrets.env
   TCP LAN (Sysmex/Horiba/Seamaty):
     verifica che il device abbia l'IP del gateway come "host destinazione"
     verifica firewall del gateway: sudo ufw status | grep 5000

6. Il gateway consegna ma il gestionale non vede
   Sul lato PIS:
     - controllare la cartella di import (WinMed/Tomedo file-drop)
     - verificare l'encoding: se il PIS decodifica ISO-8859-1
       ma i messaggi sono UTF-8 (o viceversa) → cambia hl7.charset
     - verificare che il PIS non filtri per MSH-3 = codice specifico
   Web UI del gateway → Config → bottone "Test invio" sul target
     ├── OK → il gestionale ha un problema di import lato suo
     └── AR/AE → step 8

7. Timeout di rete verso il PIS
   Dal gateway:
     nc -zv <ip-pis> <porta>        → deve dire "succeeded"
     ping <ip-pis>                  → verifica raggiungibilità
   Se ping OK ma nc fallisce → firewall lato PIS o servizio non in ascolto

8. ACK AR/AE = il PIS rigetta il messaggio
   Il messaggio raggiunge il PIS ma è rifiutato. Cause:
   - MSH-18 charset non supportato → prova "8859/1" invece di "UNICODE UTF-8"
   - Nome paziente contiene caratteri speciali non attesi
   - LOINC code non in whitelist del PIS
   Contatta il vendor del PIS con:
     - il messaggio HL7 (Web UI → Dead-letter → Vedi)
     - il codice ACK ricevuto (visibile nei log gateway con LOG_LEVEL=DEBUG)

9. Circuit breaker aperto per un target
   Il gateway ha smesso di provare perché il PIS ha fallito troppe volte
   di fila. Aspetta 60 secondi (recovery timeout) e ritenta, oppure
   riavvia il gateway per resettare i breaker:
     sudo systemctl restart jerumednexus-gateway
   Prima di riavviare, correggi la causa (rete? PIS spento?).
```

---

## SINTOMO 2: "Non riesco più a fare login nella Web UI"

```
Sei sicuro della password? Il gateway blocca l'IP per 15 min dopo 5 tentativi.

Se hai perso la password admin:
  sudo -u jerumednexus /opt/jerumednexus/.venv/bin/python \
      /opt/jerumednexus/main.py --reset-password
Poi apri di nuovo la Web UI: partirà il wizard di setup.
```

## SINTOMO 3: "La Web UI non si apre"

```
sudo systemctl status jerumednexus-webui
sudo journalctl -u jerumednexus-webui -n 100

Se la porta 8080 è occupata da altro:
  sudo ss -tlnp | grep 8080

Se sei dietro Caddy (HTTPS):
  sudo systemctl status caddy
  sudo journalctl -u caddy -n 50
```

## SINTOMO 4: "Ho aggiunto un device nuovo ma non appare"

```
1. Il file YAML è in config/devices/<nome>.yaml ?
2. Ha "enabled: true"?
3. Il "type" è uno di: sysmex_astm | mllp_hl7 | uc1000_serial | cobas_poct ?
4. Restart: sudo systemctl restart jerumednexus-gateway
5. Verifica: sudo journalctl -u jerumednexus-gateway -n 50 | grep "active"
```

## SINTOMO 5: "Il messaggio HL7 arriva ma i valori sono sbagliati"

```
Prima cosa: verifica sul lato device che il valore mostrato in stampa
coincida con quello nei log del gateway:
  sudo journalctl -u jerumednexus-gateway | grep "parsed:" | tail -5

Se il gateway vede il valore giusto:
  Web UI → Dead-letter → Vedi l'HL7 raw
  Verifica OBX-5 (valore) e OBX-6 (unità)

Se il valore nel PIS è diverso:
  Verifica che il PIS non stia applicando conversioni di unità
  (mg/dL ↔ mmol/L)  --  il gateway NON converte, forwarda i valori come sono.
```

## SINTOMO 6: "L'SD card è piena"

```
du -sh /opt/jerumednexus/logs/*
Cosa cresce di solito:
  - logs/gateway.log       → rotato automaticamente da logrotate
  - logs/audit.jsonl       → rotato ogni 10 MiB, tiene 12 file
  - logs/dead_letter/      → NON si autoripulisce -- se hai vecchi errori
                              risolti fai replay o cancella manualmente
  - logs/history.db        → cresce senza limiti; se serve, esporta e taglia
```

## Cosa allegare a un ticket di supporto

```
1. Output di:
     sudo journalctl -u jerumednexus-gateway -n 500 --no-pager > /tmp/gw.log
     sudo journalctl -u jerumednexus-webui -n 200 --no-pager > /tmp/ui.log
     cat /opt/jerumednexus/logs/status.json
     cat /opt/jerumednexus/logs/health.json
2. La versione: mostrata nella sidebar della Web UI
3. Il file config/gateway.yaml (RIMUOVI passwords/token prima!)
```
