#!/bin/bash
# ============================================================
#  enable-tls.sh -- add HTTPS in front of the JerumedNexus Gateway.
#
#  Two modes:
#     ./enable-tls.sh <fqdn>          -- Let's Encrypt (needs public DNS + port 80/443)
#     ./enable-tls.sh --self-signed   -- local self-signed via Caddy "tls internal"
# ============================================================
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: must run as root: sudo $0 ..."
    exit 1
fi

MODE="${1:-}"
if [ -z "$MODE" ]; then
    echo "Usage: sudo $0 <fqdn>|--self-signed"
    exit 1
fi

# Install Caddy if not present
if ! command -v caddy >/dev/null 2>&1; then
    echo "[tls] Installing Caddy..."
    apt-get update -q
    apt-get install -y --no-install-recommends debian-keyring debian-archive-keyring apt-transport-https curl gnupg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -q
    apt-get install -y caddy
fi

CADDYFILE=/etc/caddy/Caddyfile
cp /opt/jerumednexus/scripts/Caddyfile.example "$CADDYFILE"

if [ "$MODE" = "--self-signed" ]; then
    HOSTNAME=$(hostname -I | awk '{print $1}')
    sed -i "s|gateway.example.ch|${HOSTNAME}|;s|# tls internal|tls internal|" "$CADDYFILE"
    echo "[tls] Configured self-signed HTTPS for ${HOSTNAME}"
else
    sed -i "s|gateway.example.ch|${MODE}|" "$CADDYFILE"
    echo "[tls] Configured Let's Encrypt HTTPS for ${MODE}"
fi

# Open 80/443, close direct 8080 access
ufw allow 80/tcp || true
ufw allow 443/tcp || true
ufw delete allow 8080/tcp || true

# Ensure the app knows it's behind TLS (session cookie Secure flag)
SECRETS=/opt/jerumednexus/config/secrets.env
if ! grep -q "^WEBUI_HTTPS" "$SECRETS" 2>/dev/null; then
    echo "WEBUI_HTTPS=1" >> "$SECRETS"
fi

systemctl restart caddy
systemctl restart jerumednexus-webui

echo "[tls] Done."
if [ "$MODE" = "--self-signed" ]; then
    echo "  Open: https://${HOSTNAME}"
else
    echo "  Open: https://${MODE}"
fi
