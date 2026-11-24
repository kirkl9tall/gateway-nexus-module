#!/bin/bash
# ============================================================
#  backup.sh -- backup JerumedNexus Gateway state, optionally GPG-encrypted.
#
#  Backs up:
#    * config/       (gateway.yaml, secrets.env, webui_*, license.json, users, dlq_key)
#    * logs/audit.jsonl* + logs/dead_letter/  (audit trail + DLQ)
#    * logs/history.db  (dispatch history SQLite)
#    * logs/orders/     (bidirectional orders)
#
#  Usage:
#     sudo ./scripts/backup.sh /mnt/nas/jerumednexus
#     sudo ./scripts/backup.sh /mnt/nas/jerumednexus --keep 30
#     sudo ./scripts/backup.sh /mnt/nas/jerumednexus --gpg-recipient backup@clinic.example
#
#  Cron example (daily at 02:15, encrypted, rotate 30 days):
#     15 2 * * *  /opt/jerumednexus/scripts/backup.sh /mnt/nas/jerumednexus \
#                    --gpg-recipient backup@clinic.example --keep 30
# ============================================================
set -euo pipefail

DEST=""
KEEP=14
GPG_RECIPIENT=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --keep)          KEEP="${2:?}"; shift 2;;
        --gpg-recipient) GPG_RECIPIENT="${2:?}"; shift 2;;
        --help|-h)
            sed -n '2,20p' "$0"; exit 0;;
        --*)
            echo "Unknown flag: $1"; exit 2;;
        *)
            if [ -z "$DEST" ]; then DEST="$1"; shift; else
                echo "Extra positional arg: $1"; exit 2
            fi;;
    esac
done

if [ -z "$DEST" ]; then
    echo "Usage: sudo $0 <destination-dir> [--keep N] [--gpg-recipient KEY_ID]" >&2
    exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: must run as root" >&2
    exit 1
fi

INSTALL_DIR="/opt/jerumednexus"
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DEST"

TAR="$DEST/jerumednexus-$STAMP.tar.gz"
FINAL="$TAR"

echo "[backup] Creating $TAR ..."
tar -czf "$TAR" \
    -C "$INSTALL_DIR" \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='logs/gateway.log*' \
    config \
    logs/audit.jsonl \
    logs/audit.jsonl.* \
    logs/dead_letter \
    logs/history.db \
    logs/orders \
    logs/status.json \
    logs/health.json \
    logs/discovered.json \
    logs/breakers.json \
    2>/dev/null || true

if [ -n "$GPG_RECIPIENT" ]; then
    if ! command -v gpg >/dev/null 2>&1; then
        echo "ERROR: gpg not installed. apt install gnupg" >&2
        exit 1
    fi
    echo "[backup] Encrypting for recipient $GPG_RECIPIENT ..."
    gpg --batch --yes --trust-model always \
        --output "${TAR}.gpg" \
        --encrypt --recipient "$GPG_RECIPIENT" \
        "$TAR"
    shred -u "$TAR" 2>/dev/null || rm -f "$TAR"
    FINAL="${TAR}.gpg"
    ok "Encrypted backup: $FINAL"
else
    echo "[backup] WARNING: backup NOT encrypted. Consider --gpg-recipient <keyid>." >&2
fi

ls -lh "$FINAL"

# Rotate: keep N most recent (matches both .tar.gz and .tar.gz.gpg)
if [ "$KEEP" -gt 0 ]; then
    cd "$DEST"
    ls -1t jerumednexus-*.tar.gz* 2>/dev/null | tail -n +"$((KEEP+1))" | xargs -r rm -v --
fi

echo "[backup] Done."

ok() { echo "[backup] $*"; }
