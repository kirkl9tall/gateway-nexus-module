#!/bin/bash
# Chaos: flood the LOC-200 HTTP endpoint to fill the queue and trigger backpressure.
set -euo pipefail

TOKEN="${LOC200_HTTP_TOKEN:?set LOC200_HTTP_TOKEN}"
URL="${1:-http://127.0.0.1:5003/}"
RATE="${2:-200}"     # requests per second
DURATION="${3:-30}"  # seconds

echo "[chaos] Flooding $URL at ${RATE} req/s for ${DURATION}s..."
DELAY=$(python3 -c "print(1.0/$RATE)")
END=$(( $(date +%s) + DURATION ))

BODY='MSH|^~\&|FLOOD|SIM|LIS|PRAXIS|20250101120000||ORU^R01|C1|P|2.5\rPID||P1|P1||X^X||||M\rOBR|1|||S1||20250101120000|20250101120000|||||||||||||F\rOBX|1|NM|1920-8^AST^LN|1|10|U/L|15^40|||||F\r'

while [ $(date +%s) -lt $END ]; do
    curl -s -o /dev/null -X POST "$URL" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: text/plain" \
        --data-binary "$BODY" &
    sleep "$DELAY"
done
wait
echo "[chaos] Watch: curl -s http://127.0.0.1:8080/metrics | grep queue"
