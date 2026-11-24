# Runbook: SD card / disco pieno

## Symptom
- Alert / cliente segnala "gateway lento"
- Log: `[Errno 28] No space left on device`
- Servizio potrebbe crashare o non salvare risultati

## Impact
CRITICAL — perdita di risultati imminente.

## Diagnose

```bash
df -h
du -sh /opt/jerumednexus/logs/* | sort -h | tail
du -sh /var/log/*.log 2>/dev/null | sort -h | tail
```

Cause tipiche:
- `logs/gateway.log` non ruotato (dovrebbe: verifica `/etc/logrotate.d/jerumednexus-gateway`)
- `logs/audit.jsonl*` accumulato (rotazione automatica ogni 10 MiB, 12 file)
- `logs/dead_letter/` cresce indefinitamente se molti messaggi falliti
- `logs/history.db` cresce con il volume

## Mitigate (recupero spazio veloce)

```bash
# Rotate log ora
sudo logrotate -f /etc/logrotate.d/jerumednexus-gateway

# Comprimi DLQ vecchi (>30 giorni)
find /opt/jerumednexus/logs/dead_letter -name "*.hl7" -mtime +30 \
  -exec gzip {} \;

# Purga audit ruotati vecchi
sudo find /opt/jerumednexus/logs/ -name "audit.jsonl.*" -mtime +90 -delete

# Cache pip
sudo rm -rf /root/.cache /home/*/.cache
```

## Fix

- Aggiungi backup verso NAS (`scripts/backup.sh` in cron)
- Considera storage esterno USB per `/opt/jerumednexus/logs`
- Se ricorre: SD card più grande (64→128GB)
