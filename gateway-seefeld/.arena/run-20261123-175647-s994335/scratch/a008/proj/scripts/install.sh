#!/bin/bash
# ============================================================
#  install.sh  --  JerumedNexus Gateway installer (Debian / Raspberry Pi OS)
#
#  Usage:
#    sudo ./scripts/install.sh                # interactive
#    sudo ./scripts/install.sh --unattended   # no prompts, uses defaults
#    sudo ./scripts/install.sh --upgrade      # in-place upgrade, preserve config
#
#  Environment overrides:
#    GATEWAY_USER   (default: loc200)
#    INSTALL_DIR    (default: /opt/jerumednexus)
#    WEBUI_PORT     (default: 8080)
#    HTTP_PORT      (default: 5003)
# ============================================================
set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────────
INSTALL_DIR="${INSTALL_DIR:-/opt/jerumednexus}"
GATEWAY_USER="${GATEWAY_USER:-loc200}"
GATEWAY_GROUP="${GATEWAY_USER}"
WEBUI_PORT="${WEBUI_PORT:-8080}"
HTTP_PORT="${HTTP_PORT:-5003}"
LOG_DIR="/var/log/jerumednexus"
STATE_DIR="/var/lib/jerumednexus"
UNATTENDED=0
UPGRADE=0

# ── Colors ──────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    C_RESET="\033[0m"; C_BOLD="\033[1m"
    C_GREEN="\033[32m"; C_YELLOW="\033[33m"; C_RED="\033[31m"; C_CYAN="\033[36m"
else
    C_RESET=""; C_BOLD=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_CYAN=""
fi

log()  { echo -e "${C_CYAN}[installer]${C_RESET} $*"; }
warn() { echo -e "${C_YELLOW}[warn]${C_RESET}    $*"; }
err()  { echo -e "${C_RED}[error]${C_RESET}   $*" >&2; }
ok()   { echo -e "${C_GREEN}[ok]${C_RESET}      $*"; }

# ── Argument parsing ────────────────────────────────────────────────────────
UNINSTALL=0
PURGE=0
for arg in "$@"; do
    case "$arg" in
        --unattended) UNATTENDED=1 ;;
        --upgrade)    UPGRADE=1 ;;
        --uninstall)  UNINSTALL=1 ;;
        --purge)      UNINSTALL=1; PURGE=1 ;;
        --help|-h)
            sed -n '2,15p' "$0"; exit 0 ;;
        *) err "Unknown flag: $arg"; exit 2 ;;
    esac
done

# ── Uninstall path ─────────────────────────────────────────────────────────
if [ "$UNINSTALL" -eq 1 ]; then
    if [ "$(id -u)" -ne 0 ]; then err "Must be run as root"; exit 1; fi
    log "Stopping and removing services..."
    # Current names
    systemctl stop jerumednexus-gateway jerumednexus-webui 2>/dev/null || true
    systemctl disable jerumednexus-gateway jerumednexus-webui 2>/dev/null || true
    # Legacy names from before the JerumedNexus rename (LOC-200 Gateway era) —
    # tolerated so an existing prod Pi can be reset before installing v1.1+.
    systemctl stop loc200-gateway loc200-webui 2>/dev/null || true
    systemctl disable loc200-gateway loc200-webui 2>/dev/null || true

    rm -f /etc/systemd/system/jerumednexus-gateway.service
    rm -f /etc/systemd/system/jerumednexus-webui.service
    rm -f /etc/systemd/system/jerumednexus-device-notify@.service
    rm -f /etc/systemd/system/loc200-gateway.service
    rm -f /etc/systemd/system/loc200-webui.service
    rm -f /lib/systemd/system/jerumednexus-gateway.service
    rm -f /lib/systemd/system/jerumednexus-webui.service
    rm -f /lib/systemd/system/jerumednexus-device-notify@.service
    rm -f /etc/sudoers.d/jerumednexus-gateway
    rm -f /etc/sudoers.d/loc200-gateway
    rm -f /etc/logrotate.d/jerumednexus-gateway
    rm -f /etc/logrotate.d/loc200-gateway
    rm -f /etc/udev/rules.d/99-jerumednexus-devices.rules
    rm -f /etc/udev/rules.d/99-loc200-devices.rules
    rm -f /usr/local/bin/jerumednexus
    rm -f /usr/local/bin/loc200
    systemctl daemon-reload || true
    udevadm control --reload-rules || true
    if command -v ufw >/dev/null 2>&1; then
        ufw delete allow 8080/tcp 2>/dev/null || true
        ufw delete allow 8443/tcp 2>/dev/null || true
        ufw delete allow 5003/tcp 2>/dev/null || true
        # Chiude anche le porte degli analizzatori aperte da firewall-sync.sh,
        # altrimenti restano esposte dopo la disinstallazione.
        for _p in $(grep -oE '^[[:space:]]*listen_port:[[:space:]]*[0-9]+'                     "$INSTALL_DIR/config/gateway.yaml" 2>/dev/null                     | grep -oE '[0-9]+$' | sort -un); do
            ufw delete allow "$_p/tcp" 2>/dev/null || true
        done
    fi
    if [ "$PURGE" -eq 1 ]; then
        warn "PURGE: removing all data (config, logs, DLQ, credentials)"
        # Wipe both the current and legacy install trees so a re-install
        # starts from a truly clean slate.
        rm -rf /opt/jerumednexus /opt/loc200 /opt/loc200-gateway /opt/loc200_gateway
        rm -rf /var/log/jerumednexus /var/log/loc200
        rm -rf /var/lib/jerumednexus /var/lib/loc200
        # Delete the system user that the installer created (whatever name
        # the operator picked — default is `loc200`). Tolerate legacy names.
        for u in "$GATEWAY_USER" loc200 jerumednexus loc200gw; do
            [ -n "$u" ] || continue
            if getent passwd "$u" >/dev/null; then
                userdel -r "$u" 2>/dev/null || userdel "$u" 2>/dev/null || true
            fi
        done
        ok "Purged."
    else
        log "Kept: /opt/jerumednexus (config, logs, credentials). Use --purge to remove."
    fi
    ok "Uninstall complete."
    exit 0
fi

# ── Preflight ───────────────────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    err "Must be run as root:  sudo $0"
    exit 1
fi

if ! [ -f /etc/os-release ]; then
    err "Cannot detect OS (missing /etc/os-release)"; exit 1
fi
. /etc/os-release
case "${ID:-}" in
    debian|raspbian|ubuntu) ok "OS: ${PRETTY_NAME}" ;;
    *) warn "Unsupported OS ${PRETTY_NAME:-unknown} — proceeding anyway." ;;
esac

PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=9
if ! command -v python3 >/dev/null 2>&1; then
    err "python3 not found in PATH"; exit 1
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
log "Python version: $PY_VER"

# ── Interactive wizard ──────────────────────────────────────────────────────
FACILITY_NAME=""
RECIPIENT_NAME=""
ADMIN_PW=""
LOC200_HTTP_TOKEN=""

if [ "$UNATTENDED" -eq 0 ] && [ "$UPGRADE" -eq 0 ]; then
    echo
    echo -e "${C_BOLD}${C_CYAN}================================================${C_RESET}"
    echo -e "${C_BOLD}   JerumedNexus Gateway  --  Installazione${C_RESET}"
    echo -e "${C_BOLD}${C_CYAN}================================================${C_RESET}"
    echo
    echo "MSH-4 e MSH-6 sono due cose diverse: da chi arriva il referto,"
    echo "e a chi e' indirizzato. Se coincidono, il gestionale riceve i file"
    echo "ma non li assegna ai pazienti."
    echo
    read -rp "Nome della clinica/studio        (MSH-4): " FACILITY_NAME
    read -rp "Destinatario, di solito il medico (MSH-6): " RECIPIENT_NAME
    while true; do
        read -rsp "Password amministratore Web UI (min 12 caratteri): " ADMIN_PW; echo
        if [ "${#ADMIN_PW}" -lt 12 ]; then
            warn "Troppo corta -- almeno 12 caratteri."
            continue
        fi
        read -rsp "Conferma password: " ADMIN_PW2; echo
        [ "$ADMIN_PW" = "$ADMIN_PW2" ] && break
        warn "Non coincidono. Riprova."
    done
    LOC200_HTTP_TOKEN=$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | cut -c1-32)
    log "Token API per HTTP LOC-200 generato automaticamente."
fi

# ── 1. System packages ──────────────────────────────────────────────────────
log "[1/8] System packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev \
    build-essential libffi-dev libssl-dev \
    ufw logrotate ca-certificates curl openssl

# ── 2. Create system user ───────────────────────────────────────────────────
log "[2/8] Ensuring system user '${GATEWAY_USER}'..."
if ! getent passwd "$GATEWAY_USER" >/dev/null; then
    useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin \
            --groups dialout "$GATEWAY_USER"
    ok "Created user ${GATEWAY_USER}"
else
    usermod -aG dialout "$GATEWAY_USER" || true
    ok "User ${GATEWAY_USER} exists"
fi

# ── 3. Copy source ──────────────────────────────────────────────────────────
log "[3/8] Copying source to ${INSTALL_DIR}..."
mkdir -p "$INSTALL_DIR"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Sotto config/ vive tutto lo stato di QUESTA installazione: la configurazione
# dello studio, le credenziali, gli utenti, le chiavi, i certificati TLS e i
# profili dei device aggiunti dalla Web UI. Niente di tutto questo esiste nel
# sorgente, quindi "rsync --delete" lo cancellerebbe.
#
# L'elenco per singolo file non reggeva: bastava aggiungere un file di stato
# (webui_users.json, known_hosts, dlq_key, i certificati...) e un aggiornamento
# lo spazzava via. Un upgrade arrivava a cancellare TUTTI gli utenti, e senza
# utenti la configurazione guidata torna aperta a chiunque.
#
# "P" (protect) impedisce la cancellazione sotto config/ ma lascia comunque
# arrivare i file nuovi e aggiornati del sorgente: il catalogo dei device
# continua ad aggiornarsi, lo stato dello studio non si tocca.
#
# Vale anche per l'installazione da capo, non solo per --upgrade: reinstallare
# sopra un impianto funzionante non deve azzerarlo.
RSYNC_OPTS=(
    -a --delete
    --filter='P /config/***'
    --exclude='logs/'
    --exclude='.venv/'
    --exclude='.git/'
    --exclude='__pycache__/'
)

if [ "$UPGRADE" -eq 1 ]; then
    log "Upgrade mode -- config/, logs/ e .venv/ restano intatti"
elif [ -f "$INSTALL_DIR/config/gateway.yaml" ]; then
    warn "Esiste gia' una configurazione in $INSTALL_DIR/config -- viene conservata."
    warn "Per ripartire davvero da zero: sudo rm -rf $INSTALL_DIR  (prima fai una copia!)"
fi

rsync "${RSYNC_OPTS[@]}" --exclude='config/devices/' "$SRC_DIR/" "$INSTALL_DIR/"

# Il catalogo analizzatori e' insieme libreria di profili (33 modelli, tutti
# spenti) e stato dell'operatore: la pagina Analizzatori scrive qui quando si
# accende un apparecchio. Sovrascriverlo a ogni aggiornamento azzerava quelle
# scelte, e l'analizzatore smetteva di partire senza che nessuno l'avesse
# toccato. --ignore-existing porta i profili NUOVI e non tocca gli altri.
mkdir -p "$INSTALL_DIR/config/devices"
rsync -a --ignore-existing \
      "$SRC_DIR/config/devices/" "$INSTALL_DIR/config/devices/"

# ── 4. Directories & permissions ────────────────────────────────────────────
log "[4/8] Creating state directories..."
mkdir -p "$LOG_DIR" "$STATE_DIR" "$INSTALL_DIR/logs"
# Symlink so app writes to /var/log/jerumednexus but code paths remain unchanged
if [ ! -L "$INSTALL_DIR/logs" ] || [ "$(readlink "$INSTALL_DIR/logs")" != "$LOG_DIR" ]; then
    :  # keep local logs dir -- some existing code writes JSON status here
fi
chown -R "${GATEWAY_USER}:${GATEWAY_GROUP}" "$INSTALL_DIR" "$LOG_DIR" "$STATE_DIR"
chmod 750 "$INSTALL_DIR/config" || true

# ── 5. Python virtual environment ───────────────────────────────────────────
log "[5/8] Creating Python venv & installing dependencies..."
sudo -u "$GATEWAY_USER" python3 -m venv "$INSTALL_DIR/.venv"
sudo -u "$GATEWAY_USER" "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip --quiet
sudo -u "$GATEWAY_USER" "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --quiet
ok "Dependencies installed."

# ── 6. First-time config ────────────────────────────────────────────────────
# Always write a MINIMAL, plug-and-play-safe default: LOC-200 in HTTP mode
# (no serial path), no plugin devices, no targets enabled. The operator will
# add devices from the Web UI (or the setup wizard) once they've physically
# plugged them in -- discovered ports appear in a dropdown.
log "[6/8] Configuration..."

# When this is a FRESH install (not --upgrade), scrub any leftover admin
# credentials from a previous, aborted install. Without this, the wizard
# would refuse to create the admin user ("already exists") because the
# legacy hash file gets auto-migrated to a phantom admin entry.
if [ "$UPGRADE" -eq 0 ] && [ ! -f "$INSTALL_DIR/config/gateway.yaml" ]; then
    rm -f "$INSTALL_DIR/config/webui_password.hash" \
          "$INSTALL_DIR/config/webui_users.json" \
          "$INSTALL_DIR/config/webui_users.json.tmp" 2>/dev/null || true
fi
if [ ! -f "$INSTALL_DIR/config/gateway.yaml" ]; then
    FACILITY="${FACILITY_NAME:-PRAXIS_NAME}"
    # Se non viene indicato, si lascia VUOTO invece di copiare il mittente:
    # un destinatario sbagliato e' peggio di uno mancante, perche' sembra
    # configurato. Verifica impianto lo segnala subito.
    RECIPIENT="${RECIPIENT_NAME:-}"
    cat > "$INSTALL_DIR/config/gateway.yaml" <<YAML
# ============================================================
#  JerumedNexus Gateway -- minimal plug-and-play default.
#  Written by install.sh at first boot. Edit via the Web UI
#  (Setup Wizard / Analizzatori page), not by hand unless
#  you know what you are doing.
# ============================================================
log_level: "INFO"
log_file:  "logs/gateway.log"

loc200:
  connection_type: "http"
  http_port: ${HTTP_PORT}
  debug_raw_frames: false

# 2.3 + 8859/1 (ISO-8859-1) is the exact format Tomedo successfully
# imports from this gateway (confirmed against an archived, imported file).
# Do NOT change to 2.5 / UTF-8 -- Tomedo then archives/rejects the file.
hl7:
  version: "2.3"
  sending_application: "JMNX_GW"
  sending_facility: "${FACILITY}"
  receiving_application: "LIS"
  # MSH-6 -- a chi e' indirizzato il referto, di solito il nome del medico.
  # NON deve coincidere con sending_facility: copiarvi il mittente e' il
  # guasto che ha fermato le consegne per due giorni. Il gestionale riceve i
  # file, li legge, e non li assegna piu' a nessun paziente.
  receiving_facility: "${RECIPIENT}"
  charset: "8859/1"
  # Aggiungerebbe +0200 ai timestamp. Tomedo con questo attivo smette di
  # riconoscere i referti. Si accende dalla pagina Configurazione se il
  # proprio gestionale lo richiede davvero.
  include_timezone: false

queue_maxsize: 500
retry_max_attempts: 5
retry_delay_seconds: 5.0

# Analizzatori: iniziamo VUOTO. Quando colleghi un USB il
# gateway lo rileva (scan ogni 10s) e la Dashboard mostra
# "Device rilevato: ... [Assegna]". Un click lo aggiunge qui.
devices: []

# Gestionale: attivane uno dalla pagina Configurazione.
targets: []
YAML
    ok "Scritta configurazione minima (studio='${FACILITY}', destinatario='${RECIPIENT:-non indicato}')"
    if [ -z "$RECIPIENT" ]; then
        warn "Destinatario (MSH-6) non indicato: il gestionale non sapra' a chi"
        warn "assegnare i referti. Impostalo in Configurazione prima del primo test."
    fi
fi
chown "${GATEWAY_USER}:${GATEWAY_GROUP}" "$INSTALL_DIR/config/gateway.yaml"
chmod 640 "$INSTALL_DIR/config/gateway.yaml"

# TLS: generate a self-signed cert so Chrome/Firefox/Edge accept HTTPS
# on port 8443 (accept the warning once, then it works). Cert lasts 10 years
# and includes the Pi's LAN IP + localhost as SANs so it validates for both.
CERT_FILE="$INSTALL_DIR/config/webui_cert.pem"
KEY_FILE="$INSTALL_DIR/config/webui_key.pem"
if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    if command -v openssl >/dev/null 2>&1; then
        PI_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
        PI_HOST=$(hostname 2>/dev/null || echo "jerumednexus")
        SAN_FILE=$(mktemp)
        cat > "$SAN_FILE" <<SANCFG
[req]
distinguished_name = dn
req_extensions = v3_req
prompt = no
[dn]
CN = ${PI_HOST}
[v3_req]
subjectAltName = @alt
[alt]
DNS.1 = ${PI_HOST}
DNS.2 = ${PI_HOST}.local
DNS.3 = localhost
IP.1  = ${PI_IP}
IP.2  = 127.0.0.1
SANCFG
        openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
            -keyout "$KEY_FILE" -out "$CERT_FILE" \
            -subj "/CN=${PI_HOST}" -config "$SAN_FILE" -extensions v3_req \
            2>/dev/null && ok "Certificato HTTPS self-signed generato (10 anni)." \
            || warn "openssl fallito, HTTPS disabilitato — solo HTTP:8080."
        rm -f "$SAN_FILE"
        [ -f "$CERT_FILE" ] && chown "${GATEWAY_USER}:${GATEWAY_GROUP}" "$CERT_FILE" "$KEY_FILE"
        [ -f "$KEY_FILE" ] && chmod 600 "$KEY_FILE"
        [ -f "$CERT_FILE" ] && chmod 644 "$CERT_FILE"
    else
        warn "openssl non trovato — HTTPS disabilitato, resta solo HTTP:8080."
    fi
fi

# Secrets file
SECRETS_FILE="$INSTALL_DIR/config/secrets.env"
if [ ! -f "$SECRETS_FILE" ]; then
    umask 077
    {
        echo "# JerumedNexus Gateway secrets -- keep this file mode 600."
        echo "# Managed by install.sh; edit values as needed."
        [ -n "$LOC200_HTTP_TOKEN" ] && echo "LOC200_HTTP_TOKEN=${LOC200_HTTP_TOKEN}"
        echo ""
        echo "# ── SFTP host-key policy ──────────────────────────────────────"
        echo "# The gateway ships to clinics on private LANs where the SFTP"
        echo "# target (Tomedo, LIS, PIS server) sits on the same LAN as"
        echo "# the Pi. In that environment MITM is practically impossible,"
        echo "# so we default to accepting the SFTP host key on first use."
        echo "# Set to 0 (and populate config/known_hosts) only if the"
        echo "# gateway is exposed on a public/untrusted network."
        echo "SFTP_INSECURE_HOSTKEY=1"
        echo ""
        echo "# Per-target SFTP credentials (optional; the WebUI stores"
        echo "# them inside gateway.yaml, but you can override here so they"
        echo "# never end up in the config file). Example:"
        echo "# TOMEDO_SFTP_PASS=xxxxxx"
    } > "$SECRETS_FILE"
    chown "${GATEWAY_USER}:${GATEWAY_GROUP}" "$SECRETS_FILE"
    chmod 600 "$SECRETS_FILE"
    ok "Wrote $SECRETS_FILE (SFTP_INSECURE_HOSTKEY=1 for private-LAN default)"
fi

# Password hash — belt-and-suspenders: set JMNX_INSTALL_ROOT (which src.common.paths
# reads) *and* cd into $INSTALL_DIR, so both anchoring paths agree even if
# somebody removes one later.
if [ -n "$ADMIN_PW" ]; then
    sudo -u "$GATEWAY_USER" env \
        INSTALL_DIR="$INSTALL_DIR" \
        JMNX_INSTALL_ROOT="$INSTALL_DIR" \
        PYTHONPATH="$INSTALL_DIR" \
        bash -c "cd '$INSTALL_DIR' && '$INSTALL_DIR/.venv/bin/python' -c \"
import sys, os
sys.path.insert(0, os.environ['INSTALL_DIR'])
os.chdir(os.environ['INSTALL_DIR'])
from src.security.auth import save_password
from src.security import roles as _roles
save_password('''${ADMIN_PW}''')
if _roles.user_exists('admin'):
    _roles.update_password('admin', '''${ADMIN_PW}''')
else:
    _roles.create_user('admin', '''${ADMIN_PW}''', 'admin')
print('Password hash written for user admin.')
\""
fi

# ── 7. Systemd services ─────────────────────────────────────────────────────
log "[7/8] Installing systemd services..."
install -m 644 "$INSTALL_DIR/scripts/jerumednexus-gateway.service" \
        /etc/systemd/system/jerumednexus-gateway.service
install -m 644 "$INSTALL_DIR/scripts/jerumednexus-webui.service" \
        /etc/systemd/system/jerumednexus-webui.service
# Substitute user/paths in unit files (idempotent)
sed -i "s|__USER__|${GATEWAY_USER}|g;s|__GROUP__|${GATEWAY_GROUP}|g;s|__INSTALL_DIR__|${INSTALL_DIR}|g" \
    /etc/systemd/system/jerumednexus-gateway.service \
    /etc/systemd/system/jerumednexus-webui.service

# Sudoers rule so webui can restart the gateway service without password.
# Both /usr/bin/systemctl and /bin/systemctl are listed: on merged-/usr
# systems `sudo` resolves `systemctl` to /usr/bin/systemctl, and sudoers
# matches the command path literally (symlinks are NOT resolved), so a rule
# that only lists /bin/systemctl would be silently denied.
cat > /etc/sudoers.d/jerumednexus-gateway <<EOF
${GATEWAY_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl start jerumednexus-gateway, /usr/bin/systemctl stop jerumednexus-gateway, /usr/bin/systemctl restart jerumednexus-gateway, /usr/bin/systemctl is-active jerumednexus-gateway, /usr/bin/systemctl kill --signal=SIGHUP jerumednexus-gateway, /bin/systemctl start jerumednexus-gateway, /bin/systemctl stop jerumednexus-gateway, /bin/systemctl restart jerumednexus-gateway, /bin/systemctl is-active jerumednexus-gateway, /bin/systemctl kill --signal=SIGHUP jerumednexus-gateway
EOF
chmod 440 /etc/sudoers.d/jerumednexus-gateway

# Logrotate
cat > /etc/logrotate.d/jerumednexus-gateway <<EOF
${INSTALL_DIR}/logs/*.log {
    weekly
    rotate 8
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    su ${GATEWAY_USER} ${GATEWAY_GROUP}
}
EOF

systemctl daemon-reload
systemctl enable jerumednexus-gateway jerumednexus-webui >/dev/null

# Install CLI wrapper -> /usr/local/bin/jerumednexus
if [ -f "$INSTALL_DIR/scripts/jerumednexus" ]; then
    install -m 755 "$INSTALL_DIR/scripts/jerumednexus" /usr/local/bin/jerumednexus
    ok "CLI installed: /usr/local/bin/jerumednexus"
fi

# ── 8. Firewall ─────────────────────────────────────────────────────────────
log "[8/8] Configuring UFW firewall..."
if command -v ufw >/dev/null 2>&1; then
    ufw --force enable >/dev/null || true
    ufw default deny incoming || true
    ufw default allow outgoing || true
    ufw allow OpenSSH || true
    ufw allow "$WEBUI_PORT/tcp" comment "JerumedNexus Web UI (HTTP)" || true
    ufw allow 8443/tcp          comment "JerumedNexus Web UI (HTTPS)" || true
    ufw allow "$HTTP_PORT/tcp"  comment "JerumedNexus HTTP ingestion" || true
    ok "UFW: SSH + $WEBUI_PORT (HTTP) + 8443 (HTTPS) + $HTTP_PORT (LOC-200 ingest) allowed."
    # Le porte su cui gli analizzatori in TCP vengono ascoltati (es. Sysmex
    # XQ-320 su 5006) non erano aperte da nessuno: il device inviava, il
    # kernel scartava, e nei log non compariva niente. Vedi firewall-sync.sh.
    if [ -x "$INSTALL_DIR/scripts/firewall-sync.sh" ]; then
        "$INSTALL_DIR/scripts/firewall-sync.sh" "$INSTALL_DIR/config/gateway.yaml" || true
    fi
else
    warn "ufw not installed -- skipping firewall setup."
fi

# ── udev rules for plug-and-play device detection ──────────────────────────
if [ -f "$INSTALL_DIR/scripts/99-jerumednexus-devices.rules" ]; then
    install -m 644 "$INSTALL_DIR/scripts/99-jerumednexus-devices.rules" \
            /etc/udev/rules.d/99-jerumednexus-devices.rules
    udevadm control --reload-rules && udevadm trigger || true
    ok "udev rules installed."
fi

# ── Start services ──────────────────────────────────────────────────────────
if [ "$UPGRADE" -eq 1 ]; then
    log "Restarting services..."
    systemctl restart jerumednexus-gateway jerumednexus-webui || true
else
    log "Starting services..."
    systemctl start jerumednexus-webui || warn "webui failed to start -- check journalctl -u jerumednexus-webui"
    # Gateway needs a valid gateway.yaml -- start only if config OK
    if sudo -u "$GATEWAY_USER" "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/main.py" --check 2>&1 | grep -q "OK"; then
        systemctl start jerumednexus-gateway
    else
        warn "gateway.yaml has warnings -- edit it and run: sudo systemctl start jerumednexus-gateway"
    fi
fi

# ── Summary ─────────────────────────────────────────────────────────────────
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo -e "${C_BOLD}${C_GREEN}================================================${C_RESET}"
echo -e "${C_BOLD}${C_GREEN}   Installation complete!${C_RESET}"
echo -e "${C_BOLD}${C_GREEN}================================================${C_RESET}"
echo
echo "  Web UI (HTTP,  compat.):  http://${IP:-localhost}:${WEBUI_PORT}"
echo "  Web UI (HTTPS, Chrome):   https://${IP:-localhost}:8443"
echo "                            (accetta il warning del certificato UNA VOLTA — cert self-signed, valido 10 anni)"
echo "  HTTP ingest LOC-200:      http://${IP:-localhost}:${HTTP_PORT}"
if [ -n "$LOC200_HTTP_TOKEN" ]; then
    echo "  HTTP token:  ${LOC200_HTTP_TOKEN}"
    echo "  ${C_YELLOW}Configure the LOC-200 to send POSTs with:"
    echo "     Header: Authorization: Bearer ${LOC200_HTTP_TOKEN}${C_RESET}"
fi
echo
echo "  Service management:"
echo "     sudo systemctl status  jerumednexus-gateway jerumednexus-webui"
echo "     sudo journalctl -u jerumednexus-gateway -f"
echo
echo "  Config file: ${INSTALL_DIR}/config/gateway.yaml"
echo "  Secrets:     ${INSTALL_DIR}/config/secrets.env"
echo
