#!/bin/bash
# ============================================================
#  verify_backup.sh — restore-test the latest backup into a tmp
#  dir and verify checksums. Runs monthly via cron.
#
#  Alerts on any failure (exit non-zero, logs to syslog with
#  JerumedNexus-BackupCheck facility so Grafana/Loki can pick it up).
#
#  Usage:
#     sudo ./scripts/verify_backup.sh /mnt/nas/jerumednexus [gpg_keyid]
# ============================================================
set -euo pipefail

DEST="${1:?usage: $0 <backup-dir> [gpg-keyid]}"
KEYID="${2:-}"
TMP="$(mktemp -d /tmp/jnxbkp.XXXXXX)"
LATEST="$(ls -1t "$DEST"/jerumednexus-*.tar.gz* 2>/dev/null | head -1 || true)"

log() { logger -t JerumedNexus-BackupCheck "$@"; echo "[verify] $*"; }
fail() { log "FAIL: $*"; rm -rf "$TMP"; exit 1; }

[ -n "$LATEST" ] || fail "no backup archive found in $DEST"
log "checking $LATEST"

if [[ "$LATEST" == *.gpg ]]; then
    [ -n "$KEYID" ] || fail "backup encrypted but no gpg keyid given"
    gpg --batch --yes --decrypt --output "$TMP/restore.tar.gz" "$LATEST" \
        || fail "gpg decrypt failed"
else
    cp "$LATEST" "$TMP/restore.tar.gz"
fi

tar -xzf "$TMP/restore.tar.gz" -C "$TMP" \
    || fail "tar extract failed"

# Assert key files present
for f in config/gateway.yaml logs/audit.jsonl logs/history.db; do
    [ -e "$TMP/$f" ] || fail "missing after restore: $f"
done

# Verify SQLite integrity
sqlite3 "$TMP/logs/history.db" "PRAGMA integrity_check;" | grep -q "^ok$" \
    || fail "history.db integrity_check FAILED"

# Verify audit.jsonl is valid JSON per line
head -100 "$TMP/logs/audit.jsonl" | while IFS= read -r line; do
    python3 -c "import json,sys; json.loads(sys.argv[1])" "$line" \
        || fail "audit.jsonl contains invalid JSON line"
done

log "OK: backup $(basename "$LATEST") restore-tested successfully"
rm -rf "$TMP"
exit 0
