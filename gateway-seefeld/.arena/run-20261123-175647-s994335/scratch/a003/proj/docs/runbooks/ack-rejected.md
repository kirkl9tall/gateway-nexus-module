# Runbook: ACK AR / AE dal PIS

## Symptom
- Log: `ACK AR — Application Reject` o `ACK AE — Application Error`
- Messaggio va in DLQ dopo tutti i retry

## Impact
Basso-medio a seconda del volume rifiutato.

## Diagnose

1. Prendi il messaggio dalla DLQ:
   ```bash
   sudo -u jerumednexus jerumednexus dlq list --limit 20
   sudo -u jerumednexus jerumednexus dlq show <control-id>
   ```

2. Valida contro lo schema:
   ```bash
   sudo -u jerumednexus jerumednexus validate /tmp/message.hl7
   ```

3. Chiedi al vendor del PIS il testo esatto dell'errore:
   - Log del PIS
   - Response ACK completo (già in `dead_letter/*.meta.json`)

## Cause comuni

| Sintomo | Fix |
|---------|-----|
| `MSH-3 too long` | Riduci `sending_application` a <20 chars |
| `Invalid character encoding` | Cambia `hl7.charset` a `8859/1` |
| `Missing PID-5` | Aggiungi patient name obbligatorio |
| `Unknown OBX-3 code` | Aggiorna `loinc_map.yaml` |
| `Timestamp format` | Verifica `include_timezone` |

## Mitigate

Usa le **rewriting rules** per aggiustare il messaggio prima dell'invio:
```yaml
# config/rewrites/<target>.yaml
- name: strip Dr. prefix
  apply_to: [PID]
  field: 5
  match: "^Dr\\. "
  replace: ""
```

Poi:
```bash
sudo -u jerumednexus jerumednexus dlq replay <control-id> --targets <target>
```

## Fix

Documenta la quirk nel README del target (config/rewrites/README).
