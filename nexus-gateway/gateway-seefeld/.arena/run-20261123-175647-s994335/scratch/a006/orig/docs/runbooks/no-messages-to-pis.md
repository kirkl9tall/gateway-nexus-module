# Runbook: nessun messaggio arriva al PIS

## Symptom
- Cliente lamenta: "I risultati non arrivano in Vitomed/Tomedo/…"
- Dashboard mostra `results_today` che aumenta ma il PIS non riceve

## Impact
Alto — il gestionale sanitario non ha i risultati.

## Diagnose

1. **Il gateway sta ricevendo?**
   ```bash
   curl -s http://127.0.0.1:8080/api/status | jq '.results_today, .last_result'
   ```
   Se `results_today == 0` → problema è a monte (analyzer), vai a
   [device-unknown](device-unknown.md).

2. **Il dispatcher sta provando?**
   ```bash
   sudo journalctl -u jerumednexus-gateway -f | grep -E "Delivering|OK|FAILED"
   ```
   - Se "Delivered OK" → il PIS ha ricevuto ma non lo mostra al cliente:
     verifica la config di import lato PIS.
   - Se "FAILED (Connection refused)" → PIS non in ascolto o porta sbagliata.
   - Se "AR" (Application Reject) o "AE" (Application Error) → il PIS
     rifiuta il messaggio: vai a [ack-rejected](ack-rejected.md).

3. **Il circuit breaker è aperto?**
   ```bash
   cat /opt/jerumednexus/logs/breakers.json | jq
   ```
   Se stato `open` → vai a [breaker-open](breaker-open.md).

4. **Ci sono messaggi in DLQ?**
   ```bash
   ls -la /opt/jerumednexus/logs/dead_letter/
   ```

## Mitigate

- Test connettività:
  ```bash
  nc -zv <ip-pis> <porta>
  ```
- Test dispatch dalla Web UI: Config → target → "Test invio"
- Replay dalla DLQ dopo aver risolto il problema:
  ```bash
  sudo -u jerumednexus /usr/local/bin/jerumednexus dlq replay <control-id>
  ```

## Fix

Dipende dalla causa. Documenta in un post-mortem.
