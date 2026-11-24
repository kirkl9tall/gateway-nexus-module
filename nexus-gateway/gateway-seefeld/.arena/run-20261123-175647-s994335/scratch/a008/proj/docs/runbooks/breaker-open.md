# Runbook: Circuit breaker OPEN per un target

## Symptom
- Alert `JerumedNexusTargetBreakerOpen`
- Log: `Circuit breaker OPEN -- skipping delivery`
- `/api/status` mostra `state: "open"` per un target

## Impact
Alto — quel target non riceverà messaggi finché il breaker non si chiude.

## Diagnose

```bash
# Vedi da quanto è aperto e quanti fallimenti consecutivi
cat /opt/jerumednexus/logs/breakers.json | jq
```

Cerca la vera causa dei fallimenti:
```bash
sudo journalctl -u jerumednexus-gateway | grep -A2 "\\[<target-name>\\].*FAILED" | tail -30
```

## Mitigate

Breaker si prova a chiudere ogni 60s (`recovery_timeout`). Aspetta.

Se non si chiude dopo 5 tentativi, il target è davvero giù:
- Contatta il vendor del PIS
- I messaggi vanno in DLQ dopo il timeout → replay dopo il fix

## Fix

Se dopo il fix del target il breaker non si sblocca:
```bash
# Reset manuale
sudo rm /opt/jerumednexus/logs/breakers.json
sudo systemctl kill --signal=SIGHUP jerumednexus-gateway
```
