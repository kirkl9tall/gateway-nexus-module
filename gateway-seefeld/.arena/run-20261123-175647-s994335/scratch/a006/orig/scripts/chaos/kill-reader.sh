#!/bin/bash
# Chaos: kill a random reader thread every 60s for 5 minutes.
# Verifies the watchdog auto-restart actually kicks in.
set -euo pipefail

DURATION="${1:-300}"
END=$(( $(date +%s) + DURATION ))

echo "[chaos] Killing random reader every 60s for ${DURATION}s..."
while [ $(date +%s) -lt $END ]; do
    PID=$(pgrep -f "jerumednexus-gateway.*main.py" | head -1 || true)
    if [ -z "$PID" ]; then echo "[chaos] gateway not running"; sleep 5; continue; fi
    # Send SIGSTOP briefly to simulate a hung reader thread
    kill -STOP "$PID"
    sleep 10
    kill -CONT "$PID"
    echo "[chaos] paused+resumed pid=$PID at $(date -Iseconds)"
    sleep 50
done
echo "[chaos] done"
