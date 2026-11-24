# Runbook: Gateway service down

## Symptom
- Alert `JerumedNexusServiceDown` (Prometheus)
- Web UI mostra "servizio: fermo"
- Nessun risultato ricevuto negli ultimi N min

## Impact
- **CRITICAL**: nessun risultato di laboratorio raggiunge il PIS
- Ogni minuto down = ~10-50 risultati persi (dipende dal volume clinica)

## Diagnose (in ordine)

```bash
sudo systemctl status jerumednexus-gateway
sudo journalctl -u jerumednexus-gateway -n 200 --no-pager | tail -50
```

Cerca:
- **`ModuleNotFoundError`** → dep mancante (bcrypt, aiohttp, asyncssh)
- **`YAML parse error`** → config/gateway.yaml malformato
- **`Address already in use`** → porta 5003 occupata da altro processo
- **`Permission denied`** → user `jerumednexus` senza accesso a `/dev/ttyUSB*`
- **`OSError: [Errno 28] No space left`** → SD piena (vedi [disk-full](disk-full.md))
- **`sqlite3.OperationalError: database is locked`** → SD lenta / due processi

## Mitigate (per fermare l'impatto ADESSO)

```bash
sudo systemctl restart jerumednexus-gateway
sleep 5
sudo systemctl status jerumednexus-gateway
```

Se non riparte:
```bash
# Prova senza device fisici (skip open)
sudo systemctl stop jerumednexus-gateway
sudo -u jerumednexus /opt/jerumednexus/.venv/bin/python /opt/jerumednexus/main.py --check
```

Se il check è OK ma il servizio non parte:
```bash
# Boot in foreground per vedere l'errore live
sudo -u jerumednexus /opt/jerumednexus/.venv/bin/python /opt/jerumednexus/main.py --debug 2>&1 | head -50
```

## Fix

- Se YAML rotto: `sudo vim /opt/jerumednexus/config/gateway.yaml` → salva → restart
- Se dep mancante: `sudo -u jerumednexus /opt/jerumednexus/.venv/bin/pip install -r /opt/jerumednexus/requirements.txt`
- Se porta occupata: `sudo lsof -i :5003` → kill il processo interferente
- Se ttyUSB perms: `sudo usermod -aG dialout jerumednexus` (relogout)

## Post-mortem

Salva in `docs/incidents/YYYY-MM-DD-gateway-down.md`:
- Durata:
- Trigger identificato:
- Root cause:
- Test aggiunto per prevenirlo:
- Runbook aggiornato: sì/no
