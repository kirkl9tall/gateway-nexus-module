#!/bin/bash
# Chaos: simulate network drop between gateway and a PIS target.
# Uses iptables (requires root). Restore rule automatically after N seconds.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "must be root"; exit 1
fi

TARGET_IP="${1:?dest ip required}"
DURATION="${2:-60}"

echo "[chaos] Dropping packets to $TARGET_IP for ${DURATION}s..."
iptables -I OUTPUT -d "$TARGET_IP" -j DROP
trap "iptables -D OUTPUT -d $TARGET_IP -j DROP 2>/dev/null || true" EXIT
sleep "$DURATION"
iptables -D OUTPUT -d "$TARGET_IP" -j DROP
echo "[chaos] Restored. Check /api/status for circuit breaker state."
