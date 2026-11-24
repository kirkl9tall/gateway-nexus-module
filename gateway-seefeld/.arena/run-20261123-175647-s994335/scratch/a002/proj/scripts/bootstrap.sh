#!/bin/bash
# ============================================================
#  bootstrap.sh — Installazione JerumedNexus Gateway da sorgente
#                 su un Raspberry Pi vergine (Debian/RPi OS).
#
#  Usa questo script quando NON hai ancora un repo APT firmato
#  (situazione tipica al primo deploy). Copia questa cartella
#  intera sul Pi con scp/rsync, poi:
#
#      sudo ./scripts/bootstrap.sh
#
#  Cosa fa:
#    1. Installa pacchetti di sistema (python 3.11, venv, git, gpg)
#    2. Crea utente jerumednexus (senza shell login)
#    3. Copia sorgenti in /opt/jerumednexus
#    4. Crea virtualenv + installa dipendenze
#    5. Genera la chiave DLQ (Fernet) se manca
#    6. Copia gateway.yaml.example → gateway.yaml se manca
#    7. Installa systemd unit e socket
#    8. Apre firewall (ufw) sulle porte necessarie
#    9. Avvia il servizio
#   10. Stampa l'URL del Web UI + credenziali del wizard
#
#  Idempotente: puoi rieseguirlo senza rompere nulla.
# ============================================================
set -euo pipefail

log()  { echo -e "\033[1;34m[bootstrap]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*" >&2; }
die()  { echo -e "\033[1;31m[FAIL]\033[0m $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Esegui come root:  sudo $0"

INSTALL_DIR="/opt/jerumednexus"
SERVICE_USER="jerumednexus"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

log "1/10 Aggiorno pacchetti di sistema"
apt-get update -q
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    git gnupg curl ca-certificates \
    build-essential libssl-dev libffi-dev \
    ufw logrotate

log "2/10 Creo utente di servizio '$SERVICE_USER'"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi
usermod -a -G dialout "$SERVICE_USER"    # accesso alle porte seriali USB

log "3/10 Copio sorgenti in $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
rsync -a --delete \
    --exclude=".venv" --exclude="__pycache__" --exclude=".git" \
    --exclude="node_modules" --exclude="logs" \
    "$SRC_DIR/" "$INSTALL_DIR/"
mkdir -p "$INSTALL_DIR/logs" "$INSTALL_DIR/logs/dead_letter" \
         "$INSTALL_DIR/logs/orders" "$INSTALL_DIR/logs/trace"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

log "4/10 Creo virtualenv Python + installo dipendenze"
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/.venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$INSTALL_DIR/.venv/bin/pip" install \
    -r "$INSTALL_DIR/requirements.txt"

log "5/10 Genero chiave DLQ (Fernet AES-128) se manca"
DLQ_KEY="$INSTALL_DIR/config/dlq_key"
if [ ! -f "$DLQ_KEY" ]; then
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/.venv/bin/python" -c \
        "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" \
        > "$DLQ_KEY"
fi
chown "$SERVICE_USER:$SERVICE_USER" "$DLQ_KEY"
chmod 600 "$DLQ_KEY"

log "6/10 Copio gateway.yaml.example → gateway.yaml se manca"
if [ ! -f "$INSTALL_DIR/config/gateway.yaml" ]; then
    cp "$INSTALL_DIR/config/gateway.yaml.example" \
       "$INSTALL_DIR/config/gateway.yaml"
    chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/config/gateway.yaml"
fi

log "7/10 Installo systemd unit + socket"
cat > /etc/systemd/system/jerumednexus-gateway.service <<UNIT
[Unit]
Description=JerumedNexus Gateway
Documentation=https://docs.jerumednexus.example
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment="LOG_FORMAT=json" "PYTHONUNBUFFERED=1"
ExecStart=$INSTALL_DIR/.venv/bin/python -m flask --app webui.app run \
    --host=0.0.0.0 --port=8088 --no-debug
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=$INSTALL_DIR/logs $INSTALL_DIR/config

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload

log "8/10 Configuro firewall (ufw)"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 8088/tcp comment 'JerumedNexus WebUI'
ufw allow 5000:5099/tcp comment 'device listen ports'
ufw --force enable

log "9/10 Avvio servizio"
systemctl enable --now jerumednexus-gateway

sleep 3
if systemctl is-active --quiet jerumednexus-gateway; then
    log "✓ Servizio attivo"
else
    warn "Il servizio non è ancora attivo — controlla:"
    warn "    sudo journalctl -u jerumednexus-gateway -n 40"
fi

log "10/10 Installazione completata"

PI_IP=$(hostname -I | awk '{print $1}')
cat <<END

============================================================
  🎉 JerumedNexus Gateway installato con successo!

  Apri il browser e vai a:

      http://$PI_IP:8088

  Sarai reindirizzato al SETUP WIZARD in 7 passi guidati.
  Non serve toccare nessun file di configurazione.

  Log in tempo reale:
      sudo journalctl -u jerumednexus-gateway -f

  Documentazione locale:
      $INSTALL_DIR/docs/getting-started.md

  Riavvio manuale:
      sudo systemctl restart jerumednexus-gateway

  Disinstallazione:
      sudo systemctl disable --now jerumednexus-gateway
      sudo rm -rf $INSTALL_DIR /etc/systemd/system/jerumednexus-gateway.service
      sudo userdel $SERVICE_USER
============================================================
END
