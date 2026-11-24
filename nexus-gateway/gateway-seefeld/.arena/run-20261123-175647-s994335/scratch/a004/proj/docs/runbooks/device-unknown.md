# Runbook: device non riconosciuto / non nel catalogo

## Symptom
- Cliente ha un analizzatore non in `config/devices/*.yaml`
- Discovery lo trova ma con confidence bassa
- Non esiste un adapter per il suo protocollo

## Impact
Nessun impatto se altri device funzionano; il nuovo device è offline.

## Diagnose

1. Il discovery ha trovato qualcosa?
   ```bash
   cat /opt/jerumednexus/logs/discovered.json | jq
   ```
2. Che protocollo parla il device? Leggi la doc del vendor.

## Mitigate

Se è HL7 v2 MLLP standard:
- Vai su Analizzatori → + Aggiungi device
- Passo 1: TCP
- Passo 3: protocollo "HL7 v2 MLLP"
- Assegna una porta libera (es. 5100)

Se è un protocollo standard non ancora nel catalogo (`sysmex_astm`,
`cobas_poct`, `uc1000_serial`):
- Stessa procedura ma scegli il type appropriato.

## Fix (per protocollo proprietario)

Serve scrivere un adapter. Vedi `CONTRIBUTING.md` § "Adding a new analyzer".
Nel wizard scegli protocollo **Custom** con l'ID che darai all'adapter.

Poi:
```bash
cp src/adapters/mllp_reader.py src/adapters/vendor_reader.py
# Modifica il parser
# Registra in src/devices/registry.py::_create_reader
sudo systemctl restart jerumednexus-gateway
```
