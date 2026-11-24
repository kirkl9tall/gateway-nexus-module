# Installazione

## Opzioni

### 1. Bootstrap remoto (nuovo Raspberry Pi)

```bash
curl -fsSL https://install.jerumed-nexus.ch/gateway | sudo bash
```

Wizard interattivo: nome clinica → password admin → token API generato.

### 2. Pacchetto Debian

```bash
sudo apt install ./jerumednexus-gateway_1.2.0_all.deb
```

Upgrade con: `sudo apt install --only-upgrade jerumednexus-gateway`.

### 3. Docker

```bash
docker compose up -d       # usa docker-compose.yml
```

### 4. Immagine pre-flashata Raspberry Pi OS

Scarica `.img.xz`, flash con Raspberry Pi Imager, boot, apri la Web UI.

## Post-installazione

1. **Setup wizard**: apri `http://<IP-del-Pi>:8080` → crea password admin
2. **Configura clinica**: Config → Passo 2 → nome studio
3. **Attiva analizzatori**: Analizzatori → Aggiungi device oppure
   Configurazione → Passo 4 (toggle sui device del catalogo)
4. **Configura PIS**: Configurazione → Passo 3 → abilita Vitomed/Tomedo/etc
5. **Test end-to-end**: Test invio su ogni target → deve tornare ACK AA
6. **Attiva HTTPS** (raccomandato):
   ```bash
   sudo /opt/jerumednexus/scripts/enable-tls.sh <fqdn>
   ```

## Requisiti hardware

- Raspberry Pi 4 o 5 (raccomandato) — Pi 3B+ minimo
- 4GB RAM (2GB minimo)
- 32GB microSD (64GB raccomandata per audit log estesi)
- Rete Ethernet cablata (WiFi solo per amministrazione, non per traffico HL7)
