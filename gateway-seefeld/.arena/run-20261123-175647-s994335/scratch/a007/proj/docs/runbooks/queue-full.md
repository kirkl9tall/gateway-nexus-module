# Runbook: coda piena / drop di messaggi

## Symptom
- Alert `JerumedNexusQueueFull` o `JerumedNexusQueueBacklog`
- Metrica `jerumednexus_queue_size` vicina a `queue_maxsize`
- Nuovi messaggi finiscono in DLQ con reason `queue full timeout`

## Impact
Alto — messaggi persi se la coda resta piena.

## Diagnose

```bash
curl -s http://127.0.0.1:8080/metrics | grep -E "queue|error"
```

Se `queue_size / queue_maxsize > 0.7` per > 5min → il consumer (worker)
non riesce a stare al passo.

Cause probabili:
1. Un target è lento (retry infinito prima di dare up)
2. Molti target abilitati e sono tutti lenti
3. Overload: analyzer manda più di quanto il Pi può gestire

## Mitigate

Aumenta la coda subito:
```bash
sudo vim /opt/jerumednexus/config/gateway.yaml
# queue_maxsize: 2000    (era 500)
sudo systemctl kill --signal=SIGHUP jerumednexus-gateway
```

## Fix

Individua il target lento con:
```bash
grep "Delivered OK" /opt/jerumednexus/logs/gateway.log | tail -100 | awk '{print $NF, $(NF-2)}'
```

- Se un target ha latenze >2s consistenti → riduce `retry_max_attempts`
- Se molti target: valuta `queue_maxsize` più alto e SD più veloce
- Se overload: valuta upgrade a Raspberry Pi 5 o server dedicato
