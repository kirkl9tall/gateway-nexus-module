#!/bin/bash
# ============================================================
#  harden_pi.sh — CIS-Benchmark-aligned hardening for Raspberry Pi
#  running JerumedNexus Gateway.
#
#  What it does (idempotent):
#    * Disable unused services (bluetooth, avahi, cups)
#    * Enforce SSH: no root login, key-only, protocol 2
#    * Configure ufw: allow 22, 8088, 5000-5099 (device ports); deny rest
#    * Install & enable unattended-upgrades (security only)
#    * Kernel hardening sysctl (source route, ICMP redirect, ASLR)
#    * File integrity baseline with AIDE
#    * Install and run lynis for scoring
#
#  Usage:  sudo ./scripts/harden_pi.sh [--report-only]
# ============================================================
set -euo pipefail

REPORT_ONLY=0
for a in "$@"; do
    [ "$a" = "--report-only" ] && REPORT_ONLY=1
done

log() { echo "[harden] $*"; }

if [ "$REPORT_ONLY" -eq 0 ]; then
    log "Disabling unused services"
    for s in bluetooth avahi-daemon cups; do
        systemctl disable --now "$s" 2>/dev/null || true
    done

    log "Hardening SSH"
    sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
    sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
    sed -i 's/^#\?Protocol.*/Protocol 2/' /etc/ssh/sshd_config
    systemctl reload sshd

    log "Configuring firewall (ufw)"
    apt-get install -y ufw
    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp comment 'SSH'
    ufw allow 8088/tcp comment 'JerumedNexus Web UI'
    ufw allow 5000:5099/tcp comment 'device listen ports'
    ufw --force enable

    log "Unattended security upgrades"
    apt-get install -y unattended-upgrades
    dpkg-reconfigure -f noninteractive unattended-upgrades

    log "Kernel hardening sysctl"
    cat > /etc/sysctl.d/99-jerumednexus.conf <<'EOF'
kernel.randomize_va_space = 2
kernel.dmesg_restrict = 1
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.tcp_syncookies = 1
net.ipv6.conf.all.accept_redirects = 0
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
EOF
    sysctl --system

    log "File integrity baseline (AIDE)"
    apt-get install -y aide
    if [ ! -f /var/lib/aide/aide.db ]; then
        aideinit -y -f || true
        mv /var/lib/aide/aide.db.new /var/lib/aide/aide.db 2>/dev/null || true
    fi

    log "Installing lynis"
    apt-get install -y lynis
fi

log "Running lynis audit"
lynis audit system --quiet --no-colors > /var/log/lynis-jerumednexus.log 2>&1 || true
SCORE=$(grep -oP 'Hardening index\s*:\s*\K[0-9]+' /var/log/lynis-jerumednexus.log | tail -1)
log "Lynis hardening index: ${SCORE:-N/A}"
if [ -n "${SCORE:-}" ] && [ "$SCORE" -lt 75 ]; then
    log "WARNING: hardening index below target 75 — review /var/log/lynis-jerumednexus.log"
fi
