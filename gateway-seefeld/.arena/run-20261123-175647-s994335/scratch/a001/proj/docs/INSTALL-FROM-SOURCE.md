# Installazione da sorgente su Raspberry Pi — passo-passo

Se non hai ancora il repo APT firmato (situazione al primo deploy),
copia questa cartella intera sul Pi e lancia lo script bootstrap.

## Prerequisiti

- **Hardware**: Raspberry Pi 4 (4 GB+) o Pi 5, SD card 32 GB+ classe A2
- **OS**: Raspberry Pi OS Lite (64-bit, Bookworm) — flash con Raspberry Pi Imager
- **Rete**: Ethernet cavo consigliato (Wi-Fi funziona ma meno stabile)
- **Sul PC portatile**: `scp` o `rsync` per copiare (macOS/Linux nativi;
  Windows: usa Git Bash, WSL, o WinSCP)

## Passo 1 — Flash e primo boot del Pi

1. **Flash SD card** con Raspberry Pi Imager (raspberrypi.com/software):
   - Sistema operativo: **Raspberry Pi OS Lite (64-bit)**
   - Nel menu ⚙ (impostazioni avanzate):
     - Attiva **SSH** (con password o chiave)
     - Imposta hostname: `jerumednexus-pi`
     - Utente: `pi` (o quello che vuoi)
     - Wi-Fi solo se non hai Ethernet
2. Inserisci SD nel Pi, collega cavo Ethernet e alimentazione
3. Attendi 1-2 min per il primo boot
4. Trova l'IP del Pi:
   ```bash
   # Sul tuo portatile:
   arp -a | grep -i "pi\|raspberry"
   # oppure controlla il router
   ```

## Passo 2 — Copia la cartella sul Pi

**Da Windows (Git Bash o WSL):**

```bash
# Dal tuo portatile:
cd /c/Users/abuaw/Desktop
scp -r gateway-seefeld pi@<ip-del-pi>:/tmp/
```

**Da macOS/Linux:**

```bash
rsync -avz --progress \
    /path/to/gateway-seefeld/ \
    pi@<ip-del-pi>:/tmp/gateway-seefeld/
```

Attendi che finisca (~2-5 min via cavo Ethernet).

## Passo 3 — Esegui lo script bootstrap sul Pi

```bash
# Sul tuo portatile:
ssh pi@<ip-del-pi>

# Ora sul Pi:
cd /tmp/gateway-seefeld
sudo ./scripts/bootstrap.sh
```

Lo script fa tutto in ~5 minuti:
1. Installa Python 3.11, venv, dipendenze OS
2. Crea utente di sistema `jerumednexus`
3. Copia i sorgenti in `/opt/jerumednexus`
4. Crea virtualenv Python + installa tutte le deps
5. Genera la chiave DLQ (Fernet AES-128)
6. Copia il template `gateway.yaml`
7. Installa il systemd unit
8. Configura firewall (ufw): 22 + 8088 + 5000-5099
9. Avvia il servizio
10. Stampa l'URL del pannello

Al termine vedrai:

```
============================================================
  🎉 JerumedNexus Gateway installato con successo!

  Apri il browser e vai a:

      http://192.168.1.42:8088
============================================================
```

## Passo 4 — Configurazione dal browser (Setup Wizard)

Apri **http://\<ip-del-pi\>:8088** dal tuo portatile.

Vieni reindirizzato automaticamente al **Setup Wizard** in 7 passi:

1. **Praxis / Studio** — nome studio + lingua + fuso orario
2. **Admin** — crea password (min 10 caratteri)
3. **Rete** — auto-rileva IP del Pi + test raggiungibilità LIS
4. **Primo analizzatore** — scegli modello dal dropdown (28 opzioni)
5. **Primo gestionale** — Tomedo / Vitomed / curaMED / etc.
6. **Backup** — NAS o skip
7. **Verifica finale** — riepilogo + "Salva e avvia"

Ad ogni passo il **pannello laterale destro** spiega cosa fare, cosa
serve, e cosa succede se sbagli.

## Passo 5 — Punta gli analizzatori al Pi

Sul menu di servizio di ogni analizzatore:

| Device | Cosa impostare |
|--------|---------------|
| Sysmex XQ-320 | Setup → Host → **ASTM E1381-02 + ACK/NAK**, IP = `<pi>`, Port 5006 |
| Sysmex XP-300 | Idem ma unidirectional |
| Cobas b101 | Collega cavo USB al Pi (auto-riconosciuto) |
| UC-1000 | Collega cavo USB seriale, porta 9600 8-N-1 |
| LOC-200 | Collega cavo seriale al Pi |
| Seamaty SD1/SD3 | Setup → LIS Interface → HL7 v2, IP = `<pi>`, Port 6001/6002 |

## Passo 6 — Fai un test e verifica

1. Sul device fai un test QC (controllo qualità)
2. Nel Web UI → Dashboard: la tessera del device diventa **verde**
3. Il risultato appare in "Risultati di oggi"
4. Il risultato appare anche nel gestionale del medico

## Debug se qualcosa non va

**Log in tempo reale:**
```bash
sudo journalctl -u jerumednexus-gateway -f
```

**Stato servizio:**
```bash
sudo systemctl status jerumednexus-gateway
```

**Riavvio pulito:**
```bash
sudo systemctl restart jerumednexus-gateway
```

**Verifica /readyz e /livez:**
```bash
curl http://127.0.0.1:8088/livez
curl http://127.0.0.1:8088/readyz
```

**Rilancia bootstrap** (idempotente):
```bash
cd /tmp/gateway-seefeld
sudo ./scripts/bootstrap.sh
```

## Backup nightly (opzionale ma consigliato)

Sul Pi:
```bash
sudo crontab -e
# Aggiungi:
15 2 * * *  /opt/jerumednexus/scripts/backup.sh /mnt/nas/jerumednexus \
              --gpg-recipient backup@clinica.example --keep 30
```

## Aggiornamento (quando esce v1.4.0)

Quando è pubblicato il repo APT firmato:
```bash
sudo apt update
sudo apt install --only-upgrade jerumednexus-gateway
```

Nel frattempo, per aggiornare da sorgente:
```bash
# Sul tuo portatile: aggiorna la cartella + copia
rsync -avz --progress gateway-seefeld/ pi@<pi>:/tmp/gateway-seefeld/

# Sul Pi:
cd /tmp/gateway-seefeld
sudo ./scripts/bootstrap.sh   # idempotente
```

## Disinstallazione completa

```bash
sudo systemctl disable --now jerumednexus-gateway
sudo rm -rf /opt/jerumednexus /etc/systemd/system/jerumednexus-gateway.service
sudo userdel jerumednexus
```

## Il tuo prossimo passo

1. ✅ Flash SD + boot Pi
2. ✅ Copia cartella + `sudo ./scripts/bootstrap.sh`
3. ✅ Apri http://\<pi\>:8088 → wizard 7 passi
4. ✅ Punta analizzatori al Pi
5. ✅ Fai un test → verifica arrivo in gestionale
6. ✅ Compila `docs/field/FIELD-VALIDATION-CHECKLIST.md` e salvalo

**Tempo totale realistico: 30-45 minuti** dal Pi vergine al primo
risultato che arriva nel gestionale medico.
