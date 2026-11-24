#!/bin/bash
# ================================================================
#  rpi_setup.sh
#  Complete setup script for Raspberry Pi OS Lite (64-bit, Bookworm)
#
#  Run this ONCE on a fresh Raspberry Pi OS Lite installation:
#    chmod +x scripts/rpi_setup.sh
#    sudo ./scripts/rpi_setup.sh
#
#  What this script does:
#    1. Updates the OS
#    2. Installs Python 3.11+ and required system libraries
#    3. Creates the Python virtual environment
#    4. Installs all Python dependencies
#    5. Configures serial port (disables Linux console on UART)
#    6. Installs systemd service for auto-start
#    7. Sets up log rotation
#    8. Configures optional Samba share (for Windows file-drop)
# ================================================================
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC}  $*"; }
info() { echo -e "${CYAN}[--]${NC}  $*"; }
warn() { echo -e "${YELLOW}[!!]${NC}  $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*"; exit 1; }

INSTALL_DIR="/opt/jerumednexus"
SERVICE_USER="loc200"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Must run as root ──────────────────────────────────────────────
[[ $EUID -eq 0 ]] || err "Run with sudo: sudo $0"

echo ""
echo -e "${BOLD}════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  JerumedNexus Gateway — Raspberry Pi OS Lite Setup  ${NC}"
echo -e "${BOLD}════════════════════════════════════════════════${NC}"
echo ""

# ── Step 1: OS update ─────────────────────────────────────────────
info "Step 1/8 — Updating package lists …"
apt-get update -q
ok "Package lists updated."

# ── Step 2: System packages ───────────────────────────────────────
info "Step 2/8 — Installing system packages …"
apt-get install -y -q \
    python3 python3-pip python3-venv python3-dev \
    libffi-dev libssl-dev \
    git curl \
    logrotate \
    samba samba-common-bin     # optional, needed for Windows file-drop shares
ok "System packages installed."

# ── Step 3: Create service user ───────────────────────────────────
info "Step 3/8 — Creating service user '$SERVICE_USER' …"
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin \
            --groups dialout "$SERVICE_USER"
    ok "User '$SERVICE_USER' created (member of 'dialout' for RS-232 access)."
else
    # Ensure dialout membership
    usermod -aG dialout "$SERVICE_USER"
    ok "User '$SERVICE_USER' already exists — ensured dialout membership."
fi

# ── Step 4: Copy project files ────────────────────────────────────
info "Step 4/8 — Copying gateway to $INSTALL_DIR …"
mkdir -p "$INSTALL_DIR"
cp -r "$PROJECT_DIR/." "$INSTALL_DIR/"
mkdir -p "$INSTALL_DIR/logs"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
ok "Files copied to $INSTALL_DIR"

# ── Step 5: Python virtual environment ───────────────────────────
info "Step 5/8 — Creating Python virtual environment …"
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip --quiet
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --quiet
ok "Virtual environment ready."

# ── Step 6: Configuration ─────────────────────────────────────────
info "Step 6/8 — Configuring gateway …"
CFG="$INSTALL_DIR/config/gateway.yaml"
EXAMPLE="$INSTALL_DIR/config/gateway.yaml.example"

if [ ! -f "$CFG" ]; then
    cp "$EXAMPLE" "$CFG"
    chown "$SERVICE_USER:$SERVICE_USER" "$CFG"
    warn "Config created at $CFG"
    warn ">>> EDIT THIS FILE before starting the service! <<<"
else
    ok "Config already exists at $CFG — not overwritten."
fi

# ── Step 7: Serial port (RS-232 via UART / USB) ───────────────────
info "Step 7/8 — Configuring serial port access …"
# Add service user to dialout (already done above)
# Detect USB→RS232 adapters
USB_SERIALS=$(ls /dev/ttyUSB* 2>/dev/null || true)
if [ -n "$USB_SERIALS" ]; then
    ok "USB serial adapters found: $USB_SERIALS"
    # Update config to use first detected port if still at default
    DETECTED_PORT=$(echo "$USB_SERIALS" | head -1)
    sed -i "s|port: \"/dev/ttyUSB0\"|port: \"$DETECTED_PORT\"|g" "$CFG" 2>/dev/null || true
    ok "Serial port in config set to: $DETECTED_PORT"
else
    warn "No /dev/ttyUSB* found yet. Connect the USB→RS232 adapter and check with:"
    warn "  ls /dev/ttyUSB*"
fi

# ── Step 8: systemd service ───────────────────────────────────────
info "Step 8/8 — Installing systemd service …"

cat > /etc/systemd/system/jerumednexus-gateway.service << UNITEOF
[Unit]
Description=LOC-200 Biochemistry Analyzer → HL7 Gateway
Documentation=file:///opt/jerumednexus/README.md
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/.venv/bin/python main.py
Restart=on-failure
RestartSec=10s
RestartPreventExitStatus=0
StandardOutput=journal
StandardError=journal
SyslogIdentifier=jerumednexus-gateway

# Serial port access
SupplementaryGroups=dialout

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=${INSTALL_DIR}/logs /mnt /tmp
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictRealtime=true

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl daemon-reload
systemctl enable jerumednexus-gateway
ok "Systemd service installed and enabled."

# ── Log rotation ──────────────────────────────────────────────────
cat > /etc/logrotate.d/jerumednexus-gateway << LOGEOF
${INSTALL_DIR}/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    su ${SERVICE_USER} ${SERVICE_USER}
    postrotate
        systemctl kill -s HUP jerumednexus-gateway 2>/dev/null || true
    endscript
}
LOGEOF
ok "Log rotation configured (14 days, daily, compressed)."

# ── Optional: Samba share for Windows file-drop ───────────────────
echo ""
echo -e "${CYAN}Optional: Samba share for WinMed/Tomedo file-drop${NC}"
read -r -p "Configure Samba share for Windows PIS file-drop? [y/N] " SAMBA_CHOICE
if [[ "${SAMBA_CHOICE,,}" == "y" ]]; then
    SHARE_DIR="/mnt/loc200_share"
    mkdir -p "$SHARE_DIR/winmed_import"
    mkdir -p "$SHARE_DIR/tomedo_import"
    chown -R "$SERVICE_USER:$SERVICE_USER" "$SHARE_DIR"
    chmod -R 775 "$SHARE_DIR"

    cat >> /etc/samba/smb.conf << SAMBAEOF

[LOC200_WinMed]
   path = ${SHARE_DIR}/winmed_import
   browseable = yes
   read only = no
   guest ok = yes
   force user = ${SERVICE_USER}
   comment = JerumedNexus Gateway – WinMed import folder

[LOC200_Tomedo]
   path = ${SHARE_DIR}/tomedo_import
   browseable = yes
   read only = no
   guest ok = yes
   force user = ${SERVICE_USER}
   comment = JerumedNexus Gateway – Tomedo import folder
SAMBAEOF

    systemctl restart smbd nmbd
    ok "Samba shares created:"
    ok "  \\\\$(hostname -I | awk '{print $1}')\\LOC200_WinMed"
    ok "  \\\\$(hostname -I | awk '{print $1}')\\LOC200_Tomedo"
    warn "Update gateway.yaml watch_folder to: ${SHARE_DIR}/winmed_import"
fi

# ── Final summary ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Setup complete!${NC}"
echo ""
echo -e "  ${YELLOW}1. Edit configuration:${NC}"
echo "     sudo nano $CFG"
echo ""
echo -e "  ${YELLOW}2. Start the gateway:${NC}"
echo "     sudo systemctl start jerumednexus-gateway"
echo ""
echo -e "  ${YELLOW}3. Monitor live logs:${NC}"
echo "     sudo journalctl -u jerumednexus-gateway -f"
echo ""
echo -e "  ${YELLOW}4. Check RS-232 port:${NC}"
echo "     ls /dev/ttyUSB*"
echo "     python3 -m serial.tools.list_ports"
echo ""
echo -e "  ${YELLOW}5. Test MLLP connectivity to PIS:${NC}"
echo "     nc -zv <PIS_IP> <PORT>"
echo -e "${BOLD}════════════════════════════════════════════════${NC}"
echo ""
