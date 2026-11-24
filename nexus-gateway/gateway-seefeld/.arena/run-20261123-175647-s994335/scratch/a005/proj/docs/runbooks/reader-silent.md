# Runbook: reader silente > 1 ora

## Symptom
- Alert `JerumedNexusDeviceSilentTooLong`
- Log warning: `WATCHDOG: reader X silent for Ns`
- Watchdog auto-restart tentato ma il reader resta zombie

## Impact
Medio — nessun nuovo risultato da quel device. Gli altri device funzionano.

## Diagnose

1. **Il device è fisicamente collegato?**
   ```bash
   # USB
   ls -la /dev/ttyUSB* /dev/ttyACM*
   ls -la /dev/jerumednexus/
   # TCP
   nc -zv <ip-device> <porta>
   ```

2. **Il device sta mandando qualcosa?**
   ```bash
   # RS-232
   sudo cat /dev/ttyUSB0 | xxd | head
   # TCP
   sudo tcpdump -i eth0 port 5000 -A
   ```

3. **Il reader nel gateway è vivo?**
   ```bash
   curl -s http://127.0.0.1:8080/api/trace | jq
   curl -s http://127.0.0.1:8080/api/trace/<device-name>?limit=10
   ```

## Mitigate

Se il device sta emettendo ma il reader no:
```bash
# Force reopen del reader
sudo systemctl restart jerumednexus-gateway
```

Se il device non emette:
- Verifica alimentazione fisica
- Verifica la config sul device (destination IP + port)
- Se USB: prova un'altra porta / cavo

## Fix

Se il problema è ricorrente:
- USB: sostituisci cavo o adattatore
- TCP: verifica switch/router (le porte "storiche" a volte cambiano)
- Se il device è vecchio (>10 anni): considera EOL
