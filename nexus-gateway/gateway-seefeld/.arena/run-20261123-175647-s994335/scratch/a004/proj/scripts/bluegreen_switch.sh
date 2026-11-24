#!/bin/bash
# Zero-downtime slot swap between blue and green.
# Usage: sudo ./scripts/bluegreen_switch.sh <target-slot>  (blue|green)
set -euo pipefail

NEW="${1:?usage: $0 blue|green}"
[[ "$NEW" == "blue" || "$NEW" == "green" ]] || { echo "invalid slot"; exit 2; }
OLD=$([[ "$NEW" == "blue" ]] && echo green || echo blue)

log() { echo "[bg-switch] $*"; }

log "Starting new slot: $NEW"
systemctl start "jerumednexus-gateway-${NEW}.service"

log "Waiting for /readyz on new slot"
for i in {1..30}; do
    if curl -fsS http://127.0.0.1:8088/readyz >/dev/null; then
        log "New slot ready after ${i}s"
        break
    fi
    sleep 1
    [ "$i" -eq 30 ] && { log "TIMEOUT — rolling back"; systemctl stop "jerumednexus-gateway-${NEW}.service"; exit 1; }
done

log "Stopping old slot: $OLD"
systemctl stop "jerumednexus-gateway-${OLD}.service" || true

log "Switch complete: active=$NEW"
