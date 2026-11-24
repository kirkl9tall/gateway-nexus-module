# Runbooks

Operational procedure per incident type. Ogni runbook segue lo stesso schema:

1. **Symptom** — cosa vede il cliente / l'alert
2. **Impact** — chi è colpito e quanto
3. **Diagnose** — comandi da eseguire in ordine
4. **Mitigate** — cosa fare per fermare l'impatto ADESSO
5. **Fix** — cosa fare per la vera risoluzione
6. **Post-mortem** — cosa loggare per non ripetere

## Indice

- [Gateway service down](gateway-down.md)
- [Nessun messaggio arriva al PIS](no-messages-to-pis.md)
- [Circuit breaker aperto per un target](breaker-open.md)
- [Coda piena / drop di messaggi](queue-full.md)
- [Reader silente > 1 ora](reader-silent.md)
- [Device non riconosciuto](device-unknown.md)
- [ACK AR/AE dal PIS](ack-rejected.md)
- [Certificato TLS scaduto](tls-expired.md)
- [SD card piena](disk-full.md)
- [Password admin dimenticata](password-reset.md)
